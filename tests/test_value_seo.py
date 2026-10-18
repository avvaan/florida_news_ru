"""Ценность заметок и SEO: «что это значит для вас», лимит публикаций, склейка, гайды, E-E-A-T, sitemap."""

import json
import re
import xml.etree.ElementTree as ET
from datetime import timedelta
from unittest import mock

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from core.models import Author, Page, SiteSettings
from guides import drafting
from guides.models import Guide
from guides.schemas import GuideCheck, GuideDraft
from news.models import Article, ArticleSource, Story
from pipeline import ai, services
from pipeline.schemas import Classification, Draft, DuplicateCheck, Verification
from pipeline.services import RunLog, classify_story, write_pending
from pipeline.telegram import post_article
from sources.models import FeedItem

from .helpers import make_source
from .test_social import FakeDeepSeek

pytestmark = pytest.mark.django_db

BODY = " ".join(["слово"] * 100)
SM = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
NEWS = "{http://www.google.com/schemas/sitemap-news/0.9}"


def answers(*, draft=None, classification=None):
    return {
        Classification: classification or Classification(score=8, topic="laws", region="orlando", is_urgent=False,
                                                         is_sensitive=False, reason="закон"),
        Draft: draft or Draft(title="Новый закон о правах", teaser="Что меняется", body=BODY, tags=["законы"],
                              insufficient_facts=False, cover="covers/laws-2"),
        Verification: Verification(ok=True, confidence=0.95, issues=[]),
        DuplicateCheck: DuplicateCheck(same_story=False, article_id=None, reason="Другое событие"),
    }


def make_story(title, score=7, urgent=False, status=Story.Status.CLASSIFIED, source=None):
    source = source or make_source(name=f"S {title[:20]}", url=f"https://{abs(hash(title))}.test/rss")
    story = Story.objects.create(title=title, score=score, is_urgent=urgent, status=status)
    FeedItem.objects.create(source=source, guid=title, url=f"https://news.test/{abs(hash(title))}", title=title,
                            story=story, published_at=timezone.now())
    return story


def published(title="Ураган «Милтон» идёт на Тампу", **kw):
    return Article.objects.create(title=title, teaser="Анонс", body=BODY, status=Article.Status.PUBLISHED,
                                  published_at=timezone.now(), **kw)


# --- «Что это значит для вас» -------------------------------------------------------

@override_settings(AI_PROVIDER="deepseek")
def test_for_you_is_saved_checked_and_shown(client):
    story = make_story("Florida changes driver license rules for new residents")
    draft = Draft(title="Новые правила обмена прав", teaser="Что меняется для приезжих", body=BODY, tags=["права"],
                  insufficient_facts=False, cover="covers/laws-2",
                  for_you=["Если вы переехали недавно — проверьте срок обмена прав.", "Возьмите паспорт и I-94."])
    fake = FakeDeepSeek(answers(draft=draft))
    with mock.patch.object(ai, "get_client", return_value=fake):
        write_pending(RunLog())
    article = Article.objects.get(story=story)
    assert article.for_you_points == ["Если вы переехали недавно — проверьте срок обмена прав.", "Возьмите паспорт и I-94."]
    verify = next(c for c in fake.calls if c["schema"] is Verification)
    assert "Что это значит для вас:\n- Если вы переехали недавно" in verify["user"]
    html = client.get(article.get_absolute_url()).content.decode()
    assert "Что это значит для вас" in html and "Возьмите паспорт и I-94." in html


@override_settings(AI_PROVIDER="deepseek")
def test_for_you_may_be_empty_and_block_is_hidden(client):
    make_story("Car crash on I-4 cleared")
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek(answers())):
        write_pending(RunLog())
    article = Article.objects.get()
    assert article.for_you == "" and article.for_you_points == []
    assert "Что это значит для вас" not in client.get(article.get_absolute_url()).content.decode()


# --- Лимит публикаций -------------------------------------------------------------------

@override_settings(AI_PROVIDER="deepseek")
def test_daily_limit_takes_the_most_important_and_rejects_the_rest(monkeypatch):
    monkeypatch.setattr(services, "MORNING_UNTIL_HOUR", 0)  # вечерний проход: доступен весь лимит
    SiteSettings.objects.update(max_articles_per_day=2, min_score_to_write=1)
    stories = {score: make_story(f"Story with score {score}", score=score) for score in (6, 9, 7, 8)}
    hurricane = make_story("Hurricane warning for Tampa Bay", score=5, urgent=True)
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek(answers())):
        written = write_pending(RunLog())
    assert written == 3  # 2 по лимиту + срочное сверх лимита
    assert set(Article.objects.values_list("story_id", flat=True)) == {stories[9].pk, stories[8].pk, hurricane.pk}
    for score in (7, 6):
        stories[score].refresh_from_db()
        assert stories[score].status == Story.Status.SKIPPED and "Лимит публикаций" in stories[score].note


@override_settings(AI_PROVIDER="deepseek")
def test_morning_run_uses_only_half_of_the_limit(monkeypatch):
    monkeypatch.setattr(services, "MORNING_UNTIL_HOUR", 24)  # утренний проход
    SiteSettings.objects.update(max_articles_per_day=4, min_score_to_write=1)
    for score in (9, 8, 7):
        make_story(f"Morning story {score}", score=score)
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek(answers())):
        assert write_pending(RunLog()) == 2
    monkeypatch.setattr(services, "MORNING_UNTIL_HOUR", 0)
    assert services.publication_quota(SiteSettings.load()) == 2  # вечером — остаток


# --- Склейка по смыслу ------------------------------------------------------------------

@override_settings(AI_PROVIDER="deepseek")
def test_same_event_is_merged_into_existing_article():
    article = published()
    ArticleSource.objects.create(article=article, name="NHC", url="https://nhc.test/1")
    story = make_story("Milton forecast to hit Tampa Bay as major hurricane", status=Story.Status.NEW)
    classification = Classification(score=9, topic="weather", region="tampa", is_urgent=True, is_sensitive=False,
                                    reason="ураган", same_as_article_id=article.pk)
    fake = FakeDeepSeek({Classification: classification})
    with mock.patch.object(ai, "get_client", return_value=fake):
        classify_story(story)
    story.refresh_from_db()
    article.refresh_from_db()
    assert story.status == Story.Status.MERGED and f"#{article.pk}" in story.note
    assert article.sources.count() == 2 and article.revised_at is not None
    assert f"[{article.pk}] Ураган «Милтон» идёт на Тампу" in fake.calls[0]["user"]


# --- Гайды ------------------------------------------------------------------------------

def test_starter_guides_exist_as_empty_drafts(client):
    assert Guide.objects.count() == 9 and not Guide.objects.published().exists()
    guide = Guide.objects.get(slug="homestead-exemption")
    assert guide.body == "" and "floridarevenue.com" in guide.domains
    assert client.get("/guides/").status_code == 200
    assert client.get(guide.get_absolute_url()).status_code == 404  # черновик читателям не виден


@override_settings(AI_PROVIDER="deepseek", PERPLEXITY_API_KEY="pk")
def test_draft_guide_writes_draft_from_official_sources_only(client, admin_client):
    guide = Guide.objects.get(slug="sunpass-i-platnye-dorogi")
    facts = {"facts": [
        {"fact": "SunPass работает на всех платных дорогах Флориды", "url": "https://www.sunpass.com/en/about", "page_title": "About"},
        {"fact": "Без транспондера счёт приходит по почте (Toll-By-Plate)", "url": "https://www.fdot.gov/tolls", "page_title": "Tolls"},
        {"fact": "Тарифы зависят от дороги", "url": "https://www.floridasturnpike.com/tolls"},
        {"fact": "Блог советует…", "url": "https://someblog.test/sunpass"},  # не официальный — отбрасываем
    ]}
    data = {"status": "completed", "output_text": json.dumps(facts, ensure_ascii=False), "usage": {}}
    draft = GuideDraft(title="SunPass и платные дороги Флориды", teaser="Как платить за проезд",
                       body="Вступление.\n\n## Как работает SunPass\n\nТекст.",
                       used_urls=["https://www.sunpass.com/en/about", "https://someblog.test/sunpass"])
    fake = FakeDeepSeek({GuideDraft: draft, GuideCheck: GuideCheck(ok=True, issues=[])})
    with mock.patch("social.collectors.post_json", return_value=data) as post, \
            mock.patch.object(ai, "get_client", return_value=fake):
        from django.core.management import call_command
        call_command("draft_guide", "sunpass-i-platnye-dorogi", stdout=open("/dev/null", "w"))
    guide.refresh_from_db()
    assert guide.status == Guide.Status.DRAFT and not guide.is_published  # никогда не публикуется сам
    assert list(guide.sources.values_list("url", flat=True)) == ["https://www.sunpass.com/en/about"]
    assert "someblog" not in next(c for c in fake.calls if c["schema"] is GuideDraft)["user"]
    assert "sunpass.com" in post.call_args.args[2]["input"][0]["content"]
    assert "замечаний нет" in guide.review_notes
    assert client.get(guide.get_absolute_url()).status_code == 404
    assert "Черновик" in admin_client.get(guide.get_absolute_url()).content.decode()  # предпросмотр редакции

    guide.status, guide.published_at = Guide.Status.PUBLISHED, timezone.now()
    guide.save()
    with pytest.raises(drafting.DraftError, match="уже опубликован"):
        drafting.draft_guide(guide)


def test_guide_is_published_only_by_editor_and_posted_to_telegram(admin_client, client):
    guide = Guide.objects.get(slug="podgotovka-k-uraganu")
    guide.body = "Текст гайда.\n\n## Набор на случай ЧС\n\nВода и фонарик."
    guide.teaser = "Что сделать до сезона ураганов"
    guide.save()
    # Без отметки «проверено человеком» гайд не публикуется
    with mock.patch("guides.services.post_guide", return_value="dry-run") as post:
        admin_client.post("/admin/guides/guide/", {"action": "action_publish", "_selected_action": [guide.pk]},
                          follow=True)
    guide.refresh_from_db()
    assert not guide.is_published and not post.called
    guide.human_reviewed = True
    guide.save()
    with mock.patch("guides.services.post_guide", return_value="dry-run") as post:
        resp = admin_client.post("/admin/guides/guide/", {"action": "action_publish", "_selected_action": [guide.pk]},
                                 follow=True)
    guide.refresh_from_db()
    assert resp.status_code == 200 and guide.is_published and post.call_args.args[0] == guide
    html = client.get(guide.get_absolute_url()).content.decode()
    assert '<h2 id="nabor-na-sluchay-chs">Набор на случай ЧС</h2>' in html and '"@type": "Article"' in html
    assert guide.title in client.get("/").content.decode()  # блок «Полезное» на главной


@override_settings(AI_PROVIDER="deepseek")
def test_writer_links_related_guide():
    guide = Guide.objects.get(slug="sunpass-i-platnye-dorogi")
    Guide.objects.filter(pk=guide.pk).update(status=Guide.Status.PUBLISHED, published_at=timezone.now(), body="Текст")
    make_story("SunPass rates go up in January")
    draft = Draft(title="SunPass дорожает", teaser="С января", body=BODY, tags=["SunPass"], insufficient_facts=False,
                  cover="covers/roads", guide="sunpass-i-platnye-dorogi")
    fake = FakeDeepSeek(answers(draft=draft))
    with mock.patch.object(ai, "get_client", return_value=fake):
        write_pending(RunLog())
    article = Article.objects.get()
    assert article.guide == guide
    assert "- sunpass-i-platnye-dorogi — SunPass и платные дороги Флориды" in fake.calls[0]["user"]


# --- Кто стоит за сайтом -----------------------------------------------------------------

def test_about_page_redirect_publisher_and_ai_disclosure(client):
    assert client.get("/p/about/").status_code == 301
    html = client.get("/about/").content.decode()
    assert "CITRUSTACK LLC" in html and "с помощью искусственного интеллекта" in html
    assert '"@type": "NewsMediaOrganization"' in html and 'href="/corrections/"' in html


def test_author_pages_show_only_active_authors(client):
    placeholder = Author.objects.get(slug="redaktor")
    assert not placeholder.is_active and client.get("/author/redaktor/").status_code == 404
    assert "Имя редактора" not in client.get("/about/").content.decode()
    Author.objects.filter(pk=placeholder.pk).update(is_active=True, name="Анна Петрова", role="Редактор")
    html = client.get("/author/redaktor/").content.decode()
    assert "Анна Петрова" in html and '"@type": "Person"' in html


def test_article_byline_dates_sources_and_jsonld(client):
    article = published(revised_at=timezone.now())
    ArticleSource.objects.create(article=article, name="NHC", url="https://nhc.test/a")
    html = client.get(article.get_absolute_url()).content.decode()
    assert "Редакция Florida RU" in html and "Обновлено" in html and "https://nhc.test/a" in html
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
    assert ld["@type"] == "NewsArticle" and ld["author"]["name"] == "Редакция Florida RU"
    assert ld["publisher"]["parentOrganization"]["name"] == "CITRUSTACK LLC"
    assert ld["dateModified"] != ld["datePublished"]


def test_admin_text_edit_marks_article_revised(admin_client):
    article = published()
    resp = admin_client.post(f"/admin/news/article/{article.pk}/change/", {
        "title": article.title, "teaser": article.teaser, "body": BODY + " правка", "for_you": "",
        "status": "published", "slug": article.slug, "published_at_0": "17.10.2026", "published_at_1": "10:00:00",
        "cover_image": "", "score": "", "review_reason": "",
        "sources-TOTAL_FORMS": "0", "sources-INITIAL_FORMS": "0", "sources-MIN_NUM_FORMS": "0",
        "sources-MAX_NUM_FORMS": "1000",
    })
    assert resp.status_code == 302, resp.content.decode()[:2000]
    article.refresh_from_db()
    assert article.revised_at is not None


# --- Техническое SEO ---------------------------------------------------------------------

def test_sitemaps_are_valid_and_complete(client):
    cache.clear()
    fresh = published("Свежая новость")
    old = published("Старая новость")
    Article.objects.filter(pk=old.pk).update(published_at=timezone.now() - timedelta(days=3))
    guide = Guide.objects.get(slug="nalogi-shtata")
    Guide.objects.filter(pk=guide.pk).update(status=Guide.Status.PUBLISHED, published_at=timezone.now(), body="Текст")

    root = ET.fromstring(client.get("/sitemap.xml").content)
    locs = [el.text for el in root.iter(f"{SM}loc")]
    assert root.tag == f"{SM}urlset" and all(loc.startswith("http") for loc in locs)
    for path in (fresh.get_absolute_url(), guide.get_absolute_url(), "/guides/", "/about/", "/dmca/", "/corrections/"):
        assert any(loc.endswith(path) for loc in locs), path
    assert not any(loc.endswith("/guides/registraciya-mashiny/") for loc in locs)  # черновик
    assert not any(loc.endswith("/p/about/") for loc in locs)  # без дублей

    news = ET.fromstring(client.get("/news-sitemap.xml").content)
    urls = news.findall(f"{SM}url")
    assert [u.find(f"{SM}loc").text.endswith(fresh.get_absolute_url()) for u in urls] == [True]
    pub = urls[0].find(f"{NEWS}news/{NEWS}publication")
    assert pub.find(f"{NEWS}name").text == "Florida RU" and pub.find(f"{NEWS}language").text == "ru"
    assert urls[0].find(f"{NEWS}news/{NEWS}publication_date").text
    cache.clear()

    robots = client.get("/robots.txt").content.decode()
    assert "/sitemap.xml" in robots and "/news-sitemap.xml" in robots


def test_verification_meta_only_when_env_is_set(client):
    assert "google-site-verification" not in client.get("/").content.decode()
    with override_settings(GOOGLE_SITE_VERIFICATION="abc123"):
        assert '<meta name="google-site-verification" content="abc123">' in client.get("/").content.decode()


def test_telegram_posts_only_published_articles():
    draft = Article.objects.create(title="Черновик", teaser="t", body="b", status=Article.Status.REVIEW)
    assert post_article(draft) == "не опубликовано — не отправляем"
    assert post_article(published()) == "dry-run"


def test_brand_and_about_migration():
    from django.apps import apps

    from core import seed
    page = Page.objects.get(slug="about")
    page.body = seed.ABOUT_V2
    page.save()
    privacy = Page.objects.get(slug="privacy")
    privacy.body = "Сайт «Флорида Сегодня» принадлежит компании CITRUSTACK LLC."
    privacy.save()
    seed.update_about_and_brand(apps, None)
    page.refresh_from_db()
    privacy.refresh_from_db()
    assert "Издатель сайта — компания CITRUSTACK LLC" in page.body
    assert privacy.body == "Сайт «Florida RU» принадлежит компании CITRUSTACK LLC."

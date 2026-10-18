"""Исправления по аудиту: канонический домен, дубли, противоречия источников, срок «Срочно», топонимы."""

import re
from datetime import timedelta
from unittest import mock

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from news.models import Article, ArticleSource, Region, Story
from pipeline import ai, toponyms
from pipeline.decisions import decide
from pipeline.schemas import DuplicateCheck, Verification
from sources.models import WeatherAlert

from .test_pipeline import FakeAI, run_with, stories  # noqa: F401 — фикстура stories

pytestmark = pytest.mark.django_db

CANON = {"SITE_URL": "https://florida-ru.com", "CANONICAL_HOST": "florida-ru.com"}


def published(title="Аллигатор напал на рыбака", **kw):
    a = Article.objects.create(title=title, teaser="t", body="Первый абзац.", region=Region.objects.get(slug="tampa"),
                               status=Article.Status.PUBLISHED, published_at=timezone.now(), **kw)
    ArticleSource.objects.create(article=a, name="WFLA", url="https://wfla.com/a")
    return a


def hosts_in(text: str) -> set[str]:
    return set(re.findall(r"https?://([a-z0-9.-]+)", text)) - {"www.sitemaps.org", "www.google.com", "schema.org",
                                                              "www.w3.org", "purl.org", "wfla.com", "t.me"}


# 1. Канонический домен

@override_settings(**CANON, ALLOWED_HOSTS=["florida-ru.com", "florida-news-ru.onrender.com", "testserver"])
def test_canonical_sitemaps_rss_robots_use_only_site_url(client):
    article = published()
    cache.clear()
    page = client.get(article.get_absolute_url(), HTTP_HOST="florida-ru.com").content.decode()
    canonical = re.search(r'<link rel="canonical" href="([^"]+)"', page).group(1)
    og_url = re.search(r'property="og:url" content="([^"]+)"', page).group(1)
    assert canonical == og_url == f"https://florida-ru.com{article.get_absolute_url()}"
    for url in ("/sitemap.xml", "/news-sitemap.xml", "/robots.txt", "/rss/"):
        body = client.get(url, HTTP_HOST="florida-ru.com").content.decode()
        assert hosts_in(body) == {"florida-ru.com"}, (url, hosts_in(body))
    for script in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        assert hosts_in(script) <= {"florida-ru.com"}


@override_settings(**CANON, ALLOWED_HOSTS=["florida-ru.com", "florida-news-ru.onrender.com", "testserver"])
def test_onrender_host_redirects_301_keeping_path(client):
    resp = client.get("/region/tampa/?page=2", HTTP_HOST="florida-news-ru.onrender.com")
    assert resp.status_code == 301 and resp["Location"] == "https://florida-ru.com/region/tampa/?page=2"
    assert client.get("/healthz", HTTP_HOST="florida-news-ru.onrender.com").status_code == 200  # проверка Render
    assert client.get("/region/tampa/", HTTP_HOST="florida-ru.com").status_code == 200


# 2. Дубли

@override_settings(AI_PROVIDER="deepseek", AI_DEDUP_PROVIDER="deepseek", AI_DEDUP_MODEL="deepseek-flash")
def test_same_story_updates_existing_instead_of_new_article(stories):  # noqa: F811
    existing = published("В Орландо кипятите воду")
    fake = FakeAI(duplicate=DuplicateCheck(same_story=True, article_id=existing.pk, reason="Тот же сюжет",
                                           new_facts=["Предписание продлено до пятницы."]))
    run_with(fake)
    assert Article.objects.count() == 1  # новой заметки нет
    existing.refresh_from_db()
    assert existing.sources.count() > 1 and existing.revised_at is not None
    assert "Обновлено: Предписание продлено до пятницы." in existing.body
    assert Story.objects.filter(status=Story.Status.MERGED).count() == 2


@override_settings(AI_PROVIDER="deepseek", AI_DEDUP_PROVIDER="deepseek", AI_DEDUP_MODEL="deepseek-flash")
def test_unverified_duplicate_adds_source_but_not_facts(stories):  # noqa: F811
    existing = published("В Орландо кипятите воду")
    fake = FakeAI(
        verification=Verification(ok=True, confidence=0.95, issues=[], source_conflicts=["разное число жертв"]),
        duplicate=DuplicateCheck(same_story=True, article_id=existing.pk, reason="Тот же сюжет",
                                 new_facts=["Погибли трое."]))
    run_with(fake)
    existing.refresh_from_db()
    assert Article.objects.count() == 1 and "Погибли трое" not in existing.body
    assert "Новые факты не добавлены" in Story.objects.filter(status=Story.Status.MERGED).first().note


def test_merged_duplicate_redirects_301_to_original(client):
    original = published()
    dup = published("Во Флориде аллигатор убил мужчину")
    dup.status, dup.merged_into = Article.Status.MERGED, original
    dup.save()
    resp = client.get(dup.get_absolute_url())
    assert resp.status_code == 301 and resp["Location"] == original.get_absolute_url()
    cache.clear()
    assert dup.get_absolute_url() not in client.get("/sitemap.xml").content.decode()


# 3. Противоречия источников

def test_source_conflicts_go_to_review_even_without_review_mode():
    decision = decide(score=10, is_urgent=True, is_sensitive=False, has_official_source=True, verified_ok=True,
                      verifier_confidence=0.99, issues=[], insufficient_facts=False, auto_publish_enabled=True,
                      auto_publish_min_score=5, min_confidence=0.7, publish_without_review=True,
                      source_conflicts=["WFLA: 2 погибших, FHP: 3 погибших"])
    assert not decision.publish and "противоречат" in decision.reason and "FHP" in decision.reason


@override_settings(AI_PROVIDER="deepseek")
def test_conflicting_sources_article_waits_in_review_queue(stories):  # noqa: F811
    run_with(FakeAI(verification=Verification(ok=True, confidence=0.99, issues=[],
                                              source_conflicts=["место: Орландо или Киссимми"])))
    assert not Article.objects.filter(status=Article.Status.PUBLISHED).exists()
    assert all("противоречат" in a.review_reason for a in Article.objects.all())


# 4. «Срочно» снимается автоматически

def test_urgent_badge_expires(client):
    fresh = published("Торнадо в Тампе", is_urgent=True, expires_at=timezone.now() + timedelta(hours=1))
    stale = published("Наводнение в Броварде", is_urgent=True, expires_at=timezone.now() - timedelta(minutes=1))
    assert fresh.urgent_now and not stale.urgent_now
    html = client.get("/").content.decode()
    strip = html.split('class="urgent', 1)[1] if 'class="urgent' in html else ""
    assert "Торнадо в Тампе" in strip and "Наводнение в Броварде" not in strip[:strip.find("</section>")]


@override_settings(AI_PROVIDER="deepseek")
def test_urgent_expiry_follows_nws_alert_or_six_hours(stories):  # noqa: F811
    from pipeline.services import urgent_expiry

    run_with(FakeAI())
    article = Article.objects.first()
    article.is_urgent = True
    assert abs(urgent_expiry(article) - (article.published_at + timedelta(hours=6))) < timedelta(seconds=1)
    guid = article.story.items.first().guid
    ends = timezone.now() + timedelta(hours=3)
    WeatherAlert.objects.create(external_id=guid, event="Flood Warning", headline="h", expires=ends)
    assert urgent_expiry(article) == ends


# 5. Топонимы

def test_toponyms_in_prompt_and_fixed_in_text():
    block = toponyms.prompt_block()
    assert "Broward — Бровард" in block and "Brevard — Бревард" in block and "Palm Beach — Палм-Бич" in block
    assert toponyms.fix_text("Ливни в Брауарде и Голливуде, округ Палм Бич") == \
        "Ливни в Броварде и Холливуде, округ Палм-Бич"
    assert toponyms.fix_text("из Брауарда") == "из Броварда"  # окончание сохраняется
    assert toponyms.fix_text("Голливудские звёзды") == "Голливудские звёзды"  # прилагательное — про Калифорнию
    assert toponyms.fix_text("Подброард") == "Подброард"  # внутри слова не трогаем


@override_settings(AI_PROVIDER="deepseek")
def test_writer_prompt_contains_toponyms(stories):  # noqa: F811
    fake = FakeAI()
    with mock.patch.object(ai, "get_client", return_value=fake):
        from pipeline.services import RunLog, classify_new, write_pending
        classify_new(RunLog())
        write_pending(RunLog())
    write_call = next(c for c in fake.calls if "Топонимы Флориды" in c["messages"][0]["content"])
    assert "Бровард" in write_call["messages"][0]["content"]

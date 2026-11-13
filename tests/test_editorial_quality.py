"""Меньше и длиннее: 3–5 развёрнутых заметок в день, короткие закрыты от поисковиков, живой автор."""

import json
import re

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from core.models import Author, SiteSettings
from news.models import MIN_INDEX_WORDS, Article
from pipeline import prompts
from pipeline.decisions import decide
from pipeline.schemas import Draft
from sources import article_text
from sources.models import FeedItem

from .helpers import FakeResponse, FakeSession, make_source
from .test_pipeline import FakeAI, run_with, stories  # noqa: F401 — фикстура stories

pytestmark = pytest.mark.django_db

LONG = " ".join(["слово"] * 450)


def article(title="Новость", body=LONG, **kw):
    return Article.objects.create(title=title, teaser="Анонс", body=body, status=Article.Status.PUBLISHED,
                                  published_at=timezone.now(), **kw)


def ld_of(html: str, kind: str) -> dict:
    for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        data = json.loads(raw)
        if data.get("@type") == kind:
            return data
    raise AssertionError(f"нет разметки {kind}")


def activate_editor(**kw) -> Author:
    editor = Author.objects.get(slug="redaktor")
    for key, value in {"name": "Анна Петрова", "role": "Главный редактор", "is_active": True, **kw}.items():
        setattr(editor, key, value)
    editor.save()
    return editor


# --- Лимиты и настройки -------------------------------------------------------------------

def test_defaults_are_few_long_articles_with_editor():
    conf = SiteSettings.load()
    assert conf.max_articles_per_day == 4 and conf.max_business_per_day == 1 and conf.min_article_words == 400
    assert conf.default_author.slug == "redaktor"


def common(**kw):
    base = dict(score=8, is_urgent=False, is_sensitive=False, has_official_source=False, verified_ok=True,
                verifier_confidence=0.95, issues=[], insufficient_facts=False, auto_publish_enabled=True,
                auto_publish_min_score=7, min_confidence=0.8, publish_without_review=True, min_words=400)
    return {**base, **kw}


def test_short_article_goes_to_review_even_when_publishing_everything():
    decision = decide(**common(word_count=120))
    assert not decision.publish and "120 слов" in decision.reason
    assert decide(**common(word_count=450)).publish
    assert decide(**common(word_count=90, is_urgent=True)).publish  # ураган не ждёт редактора


# --- Индексация -----------------------------------------------------------------------------

def test_short_articles_are_noindex_and_out_of_sitemaps(client):
    cache.clear()
    short, long_, kept = article("Короткая", body="Пара фраз."), article("Длинная"), article("Сильная", body="Коротко.",
                                                                                         keep_indexed=True)
    assert not short.is_indexable and long_.is_indexable and kept.is_indexable
    assert 'content="noindex, follow"' in client.get(short.get_absolute_url()).content.decode()
    for a in (long_, kept):
        assert "noindex" not in client.get(a.get_absolute_url()).content.decode()
    sitemap = client.get("/sitemap.xml").content.decode()
    news = client.get("/news-sitemap.xml").content.decode()
    for xml in (sitemap, news):
        assert short.get_absolute_url() not in xml
        assert long_.get_absolute_url() in xml and kept.get_absolute_url() in xml
    assert short.title in client.get("/").content.decode()  # читатели короткие заметки видят
    cache.clear()


def test_admin_shows_index_state(admin_client):
    short = article("Короткая", body="Пара фраз.")
    html = admin_client.get(f"/admin/news/article/{short.pk}/change/").content.decode()
    assert f"при минимуме {MIN_INDEX_WORDS}" in html and "Оставить в индексе" in html


# --- Структура текста ------------------------------------------------------------------------

def test_subheadings_render_as_h2(client):
    a = article(body="Суть новости.\n\n## Что это значит для русскоязычных во Флориде\n\nОбъяснение.")
    html = client.get(a.get_absolute_url()).content.decode()
    assert "<h2>Что это значит для русскоязычных во Флориде</h2>" in html and "## " not in html


def test_writer_prompt_asks_for_400_600_words_and_reader_section():
    assert "400–600 слов" in prompts.WRITE_SYSTEM
    assert "Что это значит для русскоязычных во Флориде" in prompts.WRITE_SYSTEM
    assert "80–150" not in prompts.WRITE_SYSTEM


# --- Конвейер -----------------------------------------------------------------------------------

@override_settings(AI_PROVIDER="deepseek")
def test_short_draft_is_not_published(stories):  # noqa: F811
    short = Draft(title="Коротко", teaser="t", body="Всего несколько слов.", tags=["т"], insufficient_facts=False,
                  cover="covers/safety-3")
    run_with(FakeAI(draft=short))
    written = Article.objects.filter(title="Коротко")
    assert written.exists() and not written.filter(status=Article.Status.PUBLISHED).exists()
    assert "Короткая заметка" in written.first().review_reason


@override_settings(AI_PROVIDER="deepseek")
def test_new_articles_get_the_active_default_editor(stories):  # noqa: F811
    editor = activate_editor()
    run_with(FakeAI())
    assert Article.objects.exists() and set(Article.objects.values_list("author", flat=True)) == {editor.pk}


@override_settings(AI_PROVIDER="deepseek")
def test_inactive_default_editor_is_not_signed(stories):  # noqa: F811
    run_with(FakeAI())  # заготовка «redaktor» выключена — подписи человеком нет
    assert Article.objects.exists() and not Article.objects.filter(author__isnull=False).exists()


@override_settings(AI_PROVIDER="deepseek")
def test_writer_and_checker_see_full_article_text(stories, monkeypatch):  # noqa: F811
    item = FeedItem.objects.first()
    monkeypatch.setattr("pipeline.services.full_texts", lambda items, **kw: {item.pk: "Full text: 42 shelters open."})
    fake = FakeAI()
    run_with(fake)
    users = [c["messages"][-1]["content"] for c in fake.calls]
    assert sum("Full text: 42 shelters open." in u for u in users) >= 2  # автор и фактчекер


# --- Полный текст статьи ------------------------------------------------------------------------

PAGE = """<html><head><script>var x = "<p>скрипт, а не текст статьи</p>";</script></head><body>
<nav><p>Menu: Home · News · Sports · Weather · Contact us today</p></nav>
<article><p>Miami-Dade County opened 42 hurricane shelters on Tuesday, officials said.</p>
<p>Short</p><p>Residents of evacuation zones A and B must leave by 6 p.m. Wednesday.</p></article>
<footer><p>Copyright 2026 Example Media. All rights reserved worldwide.</p></footer></body></html>"""


def test_extract_text_keeps_article_paragraphs_only():
    text = article_text.extract_text(PAGE)
    assert text.split("\n\n") == ["Miami-Dade County opened 42 hurricane shelters on Tuesday, officials said.",
                                  "Residents of evacuation zones A and B must leave by 6 p.m. Wednesday."]
    assert len(article_text.extract_text(PAGE, limit=40)) <= 41


def test_full_texts_reads_rss_articles_and_skips_others(monkeypatch):
    rss, tg = make_source(), make_source(name="TG", url="https://t.me/s/x", kind="telegram")
    a = FeedItem.objects.create(source=rss, guid="1", url="https://news.test/a", title="A")
    b = FeedItem.objects.create(source=tg, guid="2", url="https://t.me/x/2", title="B")
    session = FakeSession({"https://news.test/a": FakeResponse(PAGE.encode(), headers={"Content-Type": "text/html"})})
    monkeypatch.setattr(article_text, "make_session", lambda: session)
    assert article_text.full_texts([a, b]) == {a.pk: article_text.extract_text(PAGE)}
    assert [url for url, _ in session.calls if "robots" not in url] == ["https://news.test/a"]


def test_fetch_article_text_failure_is_empty():
    session = FakeSession({"https://news.test/x": ConnectionError("нет сети")})
    assert article_text.fetch_article_text("https://news.test/x", session) == ""


# --- Живой автор --------------------------------------------------------------------------------

def test_article_byline_and_newsarticle_author_is_the_editor(client):
    editor = activate_editor(links="https://www.linkedin.com/in/anna\nне ссылка", email="anna@florida-ru.com")
    a = article(author=editor)
    html = client.get(a.get_absolute_url()).content.decode()
    assert f'href="{editor.get_absolute_url()}">Анна Петрова</a>' in html
    ld = ld_of(html, "NewsArticle")
    assert ld["author"]["@type"] == "Person" and ld["author"]["name"] == "Анна Петрова"
    assert ld["author"]["jobTitle"] == "Главный редактор" and ld["author"]["sameAs"] == ["https://www.linkedin.com/in/anna"]
    assert ld["wordCount"] == 450


def test_inactive_author_falls_back_to_editorial_byline(client):
    a = article(author=Author.objects.get(slug="redaktor"))  # заготовка выключена
    html = client.get(a.get_absolute_url()).content.decode()
    assert "Редакция Florida RU" in html and ld_of(html, "NewsArticle")["author"]["@type"] == "Organization"


def test_author_and_about_pages_show_people_and_contacts(client):
    editor = activate_editor(email="anna@florida-ru.com", links="https://t.me/anna", bio="15 лет в журналистике.")
    a = article("Заметка Анны", author=editor)
    page = client.get(editor.get_absolute_url()).content.decode()
    assert "mailto:anna@florida-ru.com" in page and 'href="https://t.me/anna"' in page and a.title in page
    person = ld_of(page, "Person")
    assert person["email"] == "anna@florida-ru.com" and person["sameAs"] == ["https://t.me/anna"]
    about = client.get("/about/").content.decode()
    assert "Анна Петрова" in about and "15 лет в журналистике." in about and "mailto:info@florida-ru.com" in about


def test_guide_names_the_editor(client):
    from guides.models import Guide

    editor = activate_editor()
    guide = Guide.objects.get(slug="nalogi-shtata")
    Guide.objects.filter(pk=guide.pk).update(status=Guide.Status.PUBLISHED, published_at=timezone.now(), body="Текст")
    html = client.get(guide.get_absolute_url()).content.decode()
    assert "Анна Петрова" in html and ld_of(html, "Article")["editor"]["name"] == "Анна Петрова"
    Author.objects.filter(pk=editor.pk).update(is_active=False)  # редактор выключен — гайд как раньше
    assert "editor" not in ld_of(client.get(guide.get_absolute_url()).content.decode(), "Article")


# --- Теги -----------------------------------------------------------------------------------------

@override_settings(AI_PROVIDER="deepseek")
def test_writer_reuses_popular_tags_and_adds_at_most_three(stories):  # noqa: F811
    from news.models import Tag

    SiteSettings.objects.update(max_articles_per_day=20)  # статьи ниже созданы сегодня и съели бы лимит
    for i in range(2):
        article(f"Про ураган {i}").tags.add(Tag.objects.get_or_create(name="ураган")[0])
    article("Разовое").tags.add(Tag.objects.create(name="Палм-Харбор"))
    draft = Draft(title="Новая", teaser="t", body=LONG, tags=["ураган", "a", "b", "c", "d"], insufficient_facts=False,
                  cover="covers/safety-3")
    fake = FakeAI(draft=draft)
    run_with(fake)
    write = next(c for c in fake.calls if "Теги, которые уже есть на сайте" in c["messages"][-1]["content"])
    listed = write["messages"][-1]["content"].split("Теги, которые уже есть на сайте:\n")[1]
    assert listed.startswith("ураган") and "Палм-Харбор" not in listed  # тег с одной заметкой не предлагаем
    for new in Article.objects.filter(title="Новая"):  # в фикстуре два сюжета
        assert sorted(new.tags.values_list("name", flat=True)) == ["a", "b", "ураган"]

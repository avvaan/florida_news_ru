"""Украинская версия: адреса /uk/…, переключатель языка, перевод контента (поля *_uk) и его SEO."""

from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone, translation

from core import translation as tr
from core.i18n import is_uk
from guides.models import Guide
from news.models import Article, Region, Topic

pytestmark = pytest.mark.django_db


@pytest.fixture
def article():
    return Article.objects.create(
        title="Налоговые каникулы на товары к урагану", teaser="Что входит в список",
        body="Первый абзац.\n\nВторой абзац.", region=Region.objects.get(slug="miami"),
        topic=Topic.objects.get(slug="money"), status=Article.Status.PUBLISHED, published_at=timezone.now(),
        keep_indexed=True,
    )


def test_russian_stays_at_root_and_ukrainian_under_prefix(client):
    ru = client.get("/").content.decode()
    uk = client.get("/uk/").content.decode()
    assert '<html lang="ru">' in ru and '<html lang="uk">' in uk


def test_ukrainian_browser_lands_on_uk_version(client):
    """Язык браузера решает, какая версия откроется; выбор в переключателе (cookie lang) важнее браузера."""
    to_uk = client.get("/guides/?page=2", HTTP_ACCEPT_LANGUAGE="uk-UA,uk;q=0.9,en;q=0.8")
    assert to_uk.status_code == 302 and to_uk["Location"] == "/uk/guides/?page=2"
    assert "Accept-Language" in to_uk["Vary"]
    for header in ("ru-RU,ru;q=0.9,uk;q=0.8", "en-US,en;q=0.9", ""):
        assert client.get("/guides/", HTTP_ACCEPT_LANGUAGE=header).status_code == 200
    assert client.get("/", HTTP_ACCEPT_LANGUAGE="en-US,uk;q=0.5").status_code == 302  # из ru/uk выше украинский
    client.cookies["lang"] = "ru"
    assert client.get("/", HTTP_ACCEPT_LANGUAGE="uk").status_code == 200
    client.cookies["lang"] = "uk"
    assert client.get("/", HTTP_ACCEPT_LANGUAGE="ru").status_code == 302


def test_bots_and_non_pages_are_not_redirected(client):
    assert client.get("/", HTTP_ACCEPT_LANGUAGE="uk", HTTP_USER_AGENT="Googlebot/2.1").status_code == 200
    for path in ("/sitemap.xml", "/robots.txt", "/healthz"):
        assert client.get(path, HTTP_ACCEPT_LANGUAGE="uk").status_code == 200, path
    assert client.get("/uk/", HTTP_ACCEPT_LANGUAGE="uk").status_code == 200


def test_old_domain_redirects_to_tutflorida(client, settings):
    settings.ALLOWED_HOSTS = ["*"]
    for host in ("florida-ru.com", "www.florida-ru.com"):
        resp = client.get("/guides/?page=2", HTTP_HOST=host)
        assert resp.status_code == 301 and resp["Location"] == f"{settings.SITE_URL}/guides/?page=2"
    assert client.get("/healthz", HTTP_HOST="florida-ru.com").status_code == 200


def test_switcher_points_to_same_page_in_other_language(client):
    html = client.get("/guides/").content.decode()
    assert 'href="/uk/guides/" hreflang="uk"' in html
    assert 'hreflang="uk" href="http' in html  # <link rel="alternate" hreflang="uk">
    html = client.get("/uk/guides/").content.decode()
    assert 'href="/guides/" hreflang="ru"' in html and 'aria-current="true">UA' in html


def test_reverse_adds_prefix_only_in_ukrainian():
    assert reverse("guides:list") == "/guides/"
    with translation.override("uk"):
        assert reverse("guides:list") == "/uk/guides/"
        assert is_uk()
    assert reverse("core-about") == "/about/"


def test_admin_and_api_stay_unprefixed(client):
    assert client.get("/uk/admin/").status_code == 404
    assert client.get("/admin/login/").status_code == 200


def test_navigation_uses_ukrainian_taxonomy(client):
    html = client.get("/uk/").content.decode()
    assert "Маямі" in html and "Увесь штат" in html
    assert "Майами" in client.get("/").content.decode()


def test_article_falls_back_to_russian_and_is_noindex_until_translated(client, article):
    url = f"/uk{article.get_absolute_url()}"
    html = client.get(url).content.decode()
    assert article.title in html
    assert 'content="noindex, follow"' in html
    assert 'hreflang="uk"' not in html.split("</head>")[0].split('rel="alternate" hreflang="ru"')[1].split("x-default")[0]
    ru = client.get(article.get_absolute_url()).content.decode()
    assert 'rel="alternate" hreflang="uk"' not in ru

    article.title_uk, article.teaser_uk = "Податкові канікули на товари до урагану", "Що входить до списку"
    article.body_uk = "Перший абзац.\n\nДругий абзац."
    article.save()
    html = client.get(url).content.decode()
    assert "Податкові канікули" in html and "Другий абзац." in html
    assert 'content="noindex, follow"' not in html
    assert 'rel="alternate" hreflang="uk"' in client.get(article.get_absolute_url()).content.decode()


def test_localized_properties(article):
    article.body_uk = "Перший.\n\n## Підзаголовок\n\nДругий."
    with translation.override("uk"):
        assert article.tr.title == article.title  # перевода заголовка нет — русский
        assert article.blocks == [("p", "Перший."), ("h", "Підзаголовок"), ("p", "Другий.")]
    assert article.blocks[0] == ("p", "Первый абзац.")


def test_uk_hash_marks_outdated_translation(article):
    assert article.uk_outdated
    article.title_uk = "Заголовок"
    article.uk_hash = article.source_hash()
    assert not article.uk_outdated
    article.body += "\n\nДобавили абзац."
    assert article.uk_outdated


def test_chunks_keep_text_intact():
    text = "\n\n".join(f"## Раздел {i}\n\n" + "Абзац текста. " * 120 for i in range(8))
    parts = tr._chunks(text, size=3000)
    assert len(parts) > 2 and all(len(p) < 6000 for p in parts)
    assert "\n\n".join(parts) == text


class FakeTranslator:
    """Вместо ИИ: «переводит», добавляя приставку UK: к каждому полю."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *, output, user, **kw):
        import json

        self.calls += 1
        payload = json.loads(user.rsplit("\n\n", 1)[1])  # JSON записей — после пустой строки

        def item(d):
            return {k: (v if k == "id" else (f"UK:{v}" if v else "")) for k, v in d.items()}
        data = {"items": [item(d) for d in payload]} if isinstance(payload, list) else item(payload)
        return output.model_validate(data)


@pytest.mark.translation
def test_translate_pending_fills_fields_and_respects_hash(monkeypatch, article):
    fake = FakeTranslator()
    monkeypatch.setattr("pipeline.ai.ask", fake)
    done = tr.translate_pending(lambda *a: None, models_=["article"], budget=Decimal("5"))
    article.refresh_from_db()
    assert done == 1 and article.title_uk == f"UK:{article.title}" and article.for_you_uk == ""
    assert not article.uk_outdated
    # повторный проход ничего не переводит
    assert tr.translate_pending(lambda *a: None, models_=["article"], budget=Decimal("5")) == 0
    assert fake.calls == 1


@pytest.mark.translation
def test_long_guide_is_translated_in_chunks(monkeypatch):
    fake = FakeTranslator()
    monkeypatch.setattr("pipeline.ai.ask", fake)
    body = "\n\n".join(f"## Раздел {i}\n\n" + "Текст гайда. " * 200 for i in range(6))
    guide = Guide.objects.create(title="Гайд", slug="test-guide", teaser="Анонс", body=body,
                                 status=Guide.Status.PUBLISHED, published_at=timezone.now(), human_reviewed=True)
    tr.translate_objects(tr.Target(Guide, Guide.objects.all), [guide])
    guide.refresh_from_db()
    assert fake.calls > 2
    assert guide.title_uk == "UK:Гайд" and guide.body_uk.startswith("UK:## Раздел 0")
    assert guide.body_uk.count("UK:") == fake.calls - 1  # каждый кусок тела — отдельный запрос


@pytest.mark.translation
def test_translation_stops_at_budget(monkeypatch, article):
    fake = FakeTranslator()
    monkeypatch.setattr("pipeline.ai.ask", fake)
    assert tr.translate_pending(lambda *a: None, models_=["article"], budget=Decimal("0")) == 0
    assert fake.calls == 0


@pytest.mark.translation
def test_manual_publish_translates_in_background(monkeypatch, admin_client, article):
    """Опубликованное руками (админка, API) переводится сразу, а не к следующему проходу конвейера."""
    import sys
    from unittest import mock

    with mock.patch("core.translation.subprocess.Popen") as popen:
        assert tr.spawn_translation(limit=5)
    cmd = popen.call_args.args[0]
    assert cmd[:3] == [sys.executable, "manage.py", "translate_content"]
    assert cmd[3:] == ["--limit", "5", "--model", "article"]

    calls = []
    monkeypatch.setattr("core.translation.spawn_translation", lambda **kw: calls.append(kw) or True)
    article.status = Article.Status.REVIEW
    article.save()
    admin_client.post("/admin/news/article/", {"action": "action_publish", "_selected_action": [article.pk]})
    article.refresh_from_db()
    assert article.status == Article.Status.PUBLISHED and calls == [{"limit": 20}]

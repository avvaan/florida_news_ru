"""Реклама и афиша только для одной версии сайта (поле language): показ, 404, hreflang, перевод, API."""

import io
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone, translation
from PIL import Image
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from ads.models import AdBanner
from core import translation as tr
from events.models import Event
from news.models import Article, Region, Topic

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_seeded_events():
    """Миграции добавляют события от редакции — начинаем с пустой афиши."""
    Event.objects.all().delete()


@pytest.fixture(autouse=True)
def media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def api():
    staff = User.objects.create_user("editor", password="x", is_staff=True)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=staff).key}")
    return client


def make_event(title, language="", **kw) -> Event:
    data = {"title": title, "description": f"Описание: {title}", "starts_on": timezone.localdate() + timedelta(days=5),
            "venue": "Зал", "address": "1 Main St", "city": "Орландо", "organizer": "Организатор",
            "contact_name": "Иван", "contact_email": "i@example.com", "status": Event.Status.APPROVED,
            "language": language}
    data.update(kw)
    event = Event(**data)
    event.slug = event.make_unique_slug()
    event.save()
    return event


@pytest.fixture
def events():
    return {
        "all": make_event("Концерт для всех", title_uk="Концерт для всіх"),
        "ru": make_event("Только по-русски", "ru"),
        "uk": make_event("Різдвяний ярмарок", "uk", description="Українська громада запрошує на ярмарок.",
                         price="Вхід вільний"),
    }


# --- реклама -------------------------------------------------------------------------------------

def test_banner_shows_only_on_its_language(client):
    Article.objects.create(title="Заметка", teaser="Анонс", body="Текст", region=Region.objects.get(slug="miami"),
                           topic=Topic.objects.get(slug="money"), status=Article.Status.PUBLISHED,
                           published_at=timezone.now())
    AdBanner.objects.create(advertiser="Все", slot="top", headline="Реклама для всех", url="https://example.com")
    AdBanner.objects.create(advertiser="RU", slot="sidebar", headline="Только русская реклама",
                            url="https://example.com", language="ru")
    AdBanner.objects.create(advertiser="UK", slot="sidebar", headline="Лише українська реклама",
                            url="https://example.com", language="uk")

    ru = client.get("/").content.decode()
    assert "Реклама для всех" in ru and "Только русская реклама" in ru and "Лише українська реклама" not in ru
    uk = client.get("/uk/").content.decode()
    assert "Реклама для всех" in uk and "Лише українська реклама" in uk and "Только русская реклама" not in uk

    for code, advertiser in (("uk", "UK"), ("ru", "RU")):
        with translation.override(code):
            assert {b.advertiser for b in AdBanner.objects.running("sidebar")} == {advertiser}


# --- афиша: списки и страница события ------------------------------------------------------------

def test_event_list_shows_only_events_of_the_language(client, events):
    ru = client.get("/afisha/").content.decode()
    assert "Концерт для всех" in ru and "Только по-русски" in ru and "Різдвяний ярмарок" not in ru
    uk = client.get("/uk/afisha/").content.decode()
    assert "Концерт для всіх" in uk and "Різдвяний ярмарок" in uk and "Только по-русски" not in uk


def test_event_detail_is_404_on_the_other_language(client, events):
    uk_event, ru_event = events["uk"], events["ru"]
    assert client.get(f"/afisha/{uk_event.slug}/").status_code == 404
    assert client.get(f"/uk/afisha/{ru_event.slug}/").status_code == 404
    assert client.get(f"/afisha/{ru_event.slug}/").status_code == 200

    # «Ещё события» на общей странице — только своего языка
    ru = client.get(f"/afisha/{events['all'].slug}/").content.decode()
    assert "Только по-русски" in ru and "Різдвяний ярмарок" not in ru
    uk = client.get(f"/uk/afisha/{events['all'].slug}/").content.decode()
    assert "Різдвяний ярмарок" in uk and "Только по-русски" not in uk


def test_ukrainian_only_event_page_has_no_links_to_missing_version(client, events):
    event = events["uk"]
    html = client.get(f"/uk/afisha/{event.slug}/").content.decode()
    head = html.split("</head>")[0]
    assert "Різдвяний ярмарок" in html and "Вхід вільний" in html
    assert 'content="noindex, follow"' not in head  # текст уже украинский — страница полноценная
    assert 'hreflang="ru"' not in head and 'hreflang="x-default"' not in head
    assert 'rel="alternate" hreflang="uk" href="' in head and f'/uk/afisha/{event.slug}/">' in head
    assert f'/afisha/{event.slug}/" hreflang="ru"' not in html
    assert 'href="/afisha/" hreflang="ru"' in html  # переключатель RU ведёт в русскую афишу

    html = client.get(f"/afisha/{events['ru'].slug}/").content.decode()
    head = html.split("</head>")[0]
    assert 'hreflang="uk"' not in head and 'hreflang="x-default"' in head
    assert 'href="/uk/afisha/" hreflang="uk"' in html


def test_ukrainian_only_event_reads_base_fields(events):
    event = events["uk"]
    with translation.override("uk"):
        assert event.tr.title == "Різдвяний ярмарок" and event.loc("price") == "Вхід вільний"
        assert event.shown_translated and event.has_uk
    assert not events["ru"].has_uk


def test_ukrainian_reader_is_not_sent_to_missing_uk_page(client, events):
    assert client.get(f"/afisha/{events['ru'].slug}/", HTTP_ACCEPT_LANGUAGE="uk").status_code == 200
    resp = client.get(f"/afisha/{events['all'].slug}/", HTTP_ACCEPT_LANGUAGE="uk")
    assert resp.status_code == 302 and resp["Location"] == f"/uk/afisha/{events['all'].slug}/"
    resp = client.get(f"/afisha/{events['uk'].slug}/", HTTP_ACCEPT_LANGUAGE="uk")
    assert resp.status_code == 302 and resp["Location"] == f"/uk/afisha/{events['uk'].slug}/"


def test_sitemap_lists_single_language_events_once(client, settings, events):
    cache.clear()  # sitemap.xml кешируется на 10 минут
    xml = client.get("/sitemap.xml").content.decode()

    def listed(path):
        return f"{settings.SITE_URL}{path}" in xml

    uk, ru, both = (f"/afisha/{events[key].slug}/" for key in ("uk", "ru", "all"))
    assert listed(f"/uk{uk}") and not listed(uk)
    assert listed(ru) and not listed(f"/uk{ru}")
    assert listed(both) and listed(f"/uk{both}")


# --- ИИ-перевод ----------------------------------------------------------------------------------

def test_translation_skips_single_language_events(events):
    todo = {obj.pk for target, objs in tr.pending(["event"]) for obj in objs}
    assert todo == {events["all"].pk}  # перевод общего ещё не сверен (uk_hash пуст) — в очереди


# --- API -----------------------------------------------------------------------------------------

def test_api_event_language_round_trip(api, client):
    day = (timezone.localdate() + timedelta(days=10)).isoformat()
    resp = api.post("/api/v1/events/", {"title": "Різдвяний ярмарок", "description": "Запрошуємо на ярмарок.",
                                        "starts_on": day, "venue": "Зала", "city": "Орландо", "region": "orlando",
                                        "price": "Вхід вільний", "language": "uk"}, format="json")
    assert resp.status_code == 201, resp.json()
    data = resp.json()
    assert data["language"] == "uk"
    assert client.get(f"/uk/afisha/{data['slug']}/").status_code == 200
    assert client.get(f"/afisha/{data['slug']}/").status_code == 404

    assert [e["id"] for e in api.get("/api/v1/events/?language=uk").json()["results"]] == [data["id"]]
    assert api.get("/api/v1/events/?language=all").json()["results"] == []

    resp = api.patch(f"/api/v1/events/{data['id']}/", {"language": ""}, format="json")
    assert resp.json()["language"] == ""
    assert client.get(f"/afisha/{data['slug']}/").status_code == 200

    resp = api.patch(f"/api/v1/events/{data['id']}/", {"language": "en"}, format="json")
    assert resp.status_code == 400 and "language" in resp.json()


def test_api_banner_language_with_multipart_upload(api, client):
    out = io.BytesIO()
    Image.new("RGB", (300, 250), "teal").save(out, "PNG")
    out.name = "banner.png"
    out.seek(0)
    resp = api.post("/api/v1/ads/", {"advertiser": "Ярмарок", "slot": "top", "url": "https://example.com",
                                     "headline": "Різдвяний ярмарок", "language": "uk", "image": out,
                                     "is_active": "true"},  # в multipart не переданный флаг — false
                    format="multipart")
    assert resp.status_code == 201, resp.json()
    data = resp.json()
    assert data["language"] == "uk" and data["image"]
    assert [b["id"] for b in api.get("/api/v1/ads/?language=uk").json()["results"]] == [data["id"]]
    assert api.get("/api/v1/ads/?language=ru").json()["results"] == []
    assert 'alt="Різдвяний ярмарок"' in client.get("/uk/").content.decode()
    assert 'alt="Різдвяний ярмарок"' not in client.get("/").content.decode()

    assert api.post("/api/v1/ads/", {"advertiser": "X", "slot": "top", "url": "https://example.com",
                                     "language": "de"}, format="json").status_code == 400
    resp = api.patch(f"/api/v1/ads/{data['id']}/", {"language": ""}, format="json")
    assert resp.json()["language"] == ""

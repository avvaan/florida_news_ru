"""Справочник: полезные официальные ссылки и рекомендации бизнесов по категориям."""

import json
import re

import pytest

from directory.models import Category, Listing

pytestmark = pytest.mark.django_db


def ld(html: str) -> dict:
    return {d["@type"]: d for d in (json.loads(b) for b in
            re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S))}


def test_seeded_categories_and_st_nina_church():
    assert Category.objects.filter(kind="links").count() == 9
    assert Category.objects.filter(kind="business").count() == 16
    church = Listing.objects.get(category__slug="cerkvi")
    assert church.url == "https://www.stninaorlando.org/" and church.is_recommended
    assert church.region.slug == "orlando" and "Hanging Moss" in church.address


def test_index_lists_official_links_and_business_categories(client):
    html = client.get("/links/").content.decode()
    assert "Официальные ссылки" in html and "https://www.flhsmv.gov/" in html
    assert 'href="/links/cerkvi/"' in html and "1 место" in html and "Пока пусто — предложите" in html
    assert "Ссылки и бизнесы" in client.get("/").content.decode()  # пункт меню


def test_church_page_has_local_business_markup(client):
    html = client.get("/links/cerkvi/").content.decode()
    assert "stninaorlando.org" in html and "Рекомендуем" in html
    item = ld(html)["ItemList"]["itemListElement"][0]["item"]
    assert item["@type"] == "Church" and item["address"]["streetAddress"].startswith("6832 Hanging Moss")
    assert 'content="index, follow' in html


def test_empty_category_is_noindex_and_partner_is_labelled_first(client):
    assert 'content="noindex, follow"' in client.get("/links/vrachi/").content.decode()
    vrachi = Category.objects.get(slug="vrachi")
    Listing.objects.create(category=vrachi, name="Клиника А", url="https://a.example/")
    Listing.objects.create(category=vrachi, name="Клиника Б", url="https://b.example/", is_partner=True)
    html = client.get("/links/vrachi/").content.decode()
    assert html.index("Клиника Б") < html.index("Клиника А") and "Партнёр" in html
    assert 'content="index, follow' in html


def test_guide_link_shown_only_for_published_guide(client):
    listing = Listing.objects.get(url="https://www.flhsmv.gov/")
    assert listing.guide_slug == "prava-vo-floride-dlya-priezzhih"
    html = client.get("/links/dokumenty-i-immigraciya/").content.decode()
    assert "Подробнее в гайде" not in html  # стартовый гайд — черновик, ссылку не показываем


def test_sitemap_includes_only_filled_categories(client):
    from django.core.cache import cache

    cache.clear()  # sitemap кэшируется на 10 минут
    sitemap = client.get("/sitemap.xml").content.decode()
    assert "/links/</loc>" in sitemap and "/links/cerkvi/</loc>" in sitemap
    assert "/links/vrachi/</loc>" not in sitemap

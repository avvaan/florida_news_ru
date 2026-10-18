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
    assert Category.objects.filter(kind="business").count() == 21
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
    assert 'content="noindex, follow"' in client.get("/links/remont/").content.decode()
    avto = Category.objects.get(slug="remont")
    Listing.objects.create(category=avto, name="Клиника А", url="https://a.example/")
    Listing.objects.create(category=avto, name="Клиника Б", url="https://b.example/", is_partner=True)
    html = client.get("/links/remont/").content.decode()
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
    assert "/links/vrachi/</loc>" in sitemap and "/links/remont/</loc>" not in sitemap
    assert "/links/produkty/</loc>" in sitemap  # «Лакомка» и Green Hills включены


def test_businesses_from_editor_table():
    from directory.models import Listing

    business = Listing.objects.filter(category__kind="business")
    assert business.filter(name__startswith="Wayside").exists() and business.filter(category__slug="cerkvi").exists()
    hidden = set(business.filter(is_active=False).values_list("name", flat=True))
    assert {"Romashka Euro Deli", "Klondike"} <= hidden or "Romashka Euro Deli" in hidden
    assert not any(name.startswith("Lacomka") for name in hidden)  # «Лакомку» проверили и включили
    assert all(Listing.objects.filter(name__in=hidden).values_list("editor_note", flat=True))
    gesheva = business.get(name__startswith="Irena Gesheva")
    assert gesheva.phone == "(941) 629-2900" and "/doctor/irena-gesheva-md/" in gesheva.url


def test_category_region_filter(client):
    html = client.get("/links/vrachi/").content.decode()
    assert "Все (10)" in html and "Другие города" in html  # +хиропрактик и подиатр из таблицы
    assert html.index("Джексонвилл") < html.index("Палметто")  # регионы раньше «других городов»
    tampa = client.get("/links/vrachi/?region=tampa").content.decode()
    assert tampa.count('class="dir__card"') == 1 and 'content="noindex, follow"' in tampa
    produkty = client.get("/links/produkty/").content.decode()
    assert "Romashka" not in produkty and "Kalinka" in produkty  # Ромашка ждёт проверки, Калинку проверили


def test_wayside_family_dental(client):
    from directory.models import Listing

    item = Listing.objects.get(name__startswith="Wayside Family Dental")
    assert item.category.slug == "stomatologi" and item.is_recommended and item.is_active
    assert item.phone == "(407) 732-4570" and item.region.slug == "orlando"
    html = client.get("/links/stomatologi/").content.decode()
    assert html.index("Wayside Family Dental") < html.index("Tetri") and "Рекомендуем" in html


def test_batch2_additions(client):
    from directory.models import Listing

    lacomka = Listing.objects.get(name__startswith="Lacomka")
    assert lacomka.is_active and lacomka.phone == "(407) 677-1101" and "Winter Park" in lacomka.address
    for name, slug in (("Green Hills", "produkty"), ("Мария — логопед", "deti"), ("Circus Dog Show", "prazdniki"),
                       ("Argo Restaurant", "restorany"), ("Zefir Milenia", "podarki"), ("Revivery", "krasota"),
                       ("Golden Age", "pozhilye"), ("Sofia Art Academy", "deti"), ("Alexander Miloserdov", "krasota"),
                       ("GroomBoom", "zhivotnye"), ("EuroHome", "produkty"), ("Funky Fresh", "podarki"),
                       ("All Green Project", "deti"), ("Mariia Delibaltova", "krasota")):
        item = Listing.objects.get(name__startswith=name)
        assert item.category.slug == slug and item.is_active, name
    html = client.get("/links/produkty/").content.decode()
    assert "Green Hills" in html and "Лакомка" in html


def test_batch3_verified_table():
    from directory.models import Listing

    assert Listing.objects.get(name__startswith="Kalinka").is_active
    citrin = Listing.objects.get(name__startswith="Mark Citrin")
    assert citrin.phone == "(305) 899-9919" and citrin.description  # дополнили, описание не затёрли
    assert Listing.objects.get(name__startswith="Alenka").phone == "(407) 910-7351"
    for name in ("Law Offices of George Lambert", "Toyota of Hollywood", "Valeria Studio — брови и ресницы"):
        assert not Listing.objects.get(name=name).is_active, name


def test_category_icons(client):
    for cat in Category.objects.all():
        assert cat.icon == f"directory/{cat.slug}.webp", cat.slug  # у каждой стартовой категории есть иконка
    html = client.get("/links/").content.decode()
    assert html.count('class="dir__icon') == Category.objects.count()
    assert "directory/cerkvi" in client.get("/links/cerkvi/").content.decode()


def test_orthodox_parishes_batch(client):
    from directory.models import Listing

    churches = Listing.objects.filter(category__slug="cerkvi")
    assert churches.filter(is_active=True).count() == 11  # Святая Нина + 10 приходов
    assert not churches.get(name__contains="Григория Богослова").is_active  # без адреса — скрыт
    html = client.get("/links/cerkvi/").content.decode()
    assert "Почаевской" in html and "Все (11)" in html and "stnicholasftl.org" in html

"""Координаты городов Флориды и сортировка «ближе к главному городу» в справочнике бизнесов."""

import pytest

from core import geo
from directory.models import Category, Listing
from news.models import Region


@pytest.mark.parametrize("text, city", [
    ("Санни-Айлс-Бич", "Sunny Isles Beach"), ("Халландейл-Бич", "Hallandale Beach"),
    ("Норт-Майами-Бич", "North Miami Beach"), ("Норт-Майами и Орландо", "North Miami"),
    ("Дирфилд-Бич / Холливуд", "Deerfield Beach"), ("Лонгвуд (Орландо)", "Longwood"),
    ("St. Petersburg", "St. Petersburg"), ("Сент-Питерсберг", "St. Petersburg"), ("Fort Lauderdale", "Fort Lauderdale"),
])
def test_locate_city(text, city):
    expected = next((lat, lon) for lat, lon, *names in geo.CITIES if names[0] == city)
    assert geo.locate(text) == expected


def test_locate_address_uses_city_not_street():
    assert geo.locate_address("9795 Old St Augustine Rd, Jacksonville, FL 32257") == geo.locate("Jacksonville")
    assert geo.locate_address("123 Palm Dr, Florida City, FL 33034") == geo.locate("Florida City")
    assert geo.locate("Онлайн, по всей Флориде") is None and geo.locate_address("") is None


def test_distance_text():
    assert geo.distance_text(geo.locate("Orlando"), "miami") == "≈ 204 мили от Майами"
    assert geo.distance_text(geo.locate("Aventura"), "miami") == "≈ 13 миль от Майами"
    assert geo.distance_text(geo.locate("Tampa"), "tampa") == ""  # сам главный город
    assert geo.distance_text(None, "miami") == ""
    assert geo.miles(geo.hub_point("miami"), geo.hub_point("jacksonville")) == pytest.approx(327, abs=3)


@pytest.mark.django_db
def test_directory_sorted_by_distance(client):
    cat = Category.objects.create(slug="test-biz", name="Тест", kind=Category.Kind.BUSINESS)
    miami = Region.objects.get(slug="miami")
    rows = [("Партнёр в Тампе", "", "Тампа", True), ("Онлайн-сервис", "", "Онлайн, по всей Флориде", False),
            ("Кафе в Холливуде", "2000 Hollywood Blvd, Hollywood, FL 33020", "Холливуд", False),
            ("Кафе в Орландо", "", "Орландо", False)]
    for name, address, city, partner in rows:
        Listing.objects.create(category=cat, name=name, address=address, city=city, is_partner=partner, region=miami)
    page = client.get("/links/test-biz/?near=miami")
    assert [item.name for item in page.context["listings"]] == [
        "Кафе в Холливуде", "Кафе в Орландо", "Партнёр в Тампе", "Онлайн-сервис"]
    html = page.content.decode()
    assert "≈ 17 миль от Майами" in html and 'content="noindex, follow"' in html and "Ближе к Джексонвиллу" in html
    default = client.get("/links/test-biz/")
    assert default.context["listings"][0].name == "Партнёр в Тампе" and "миль от" not in default.content.decode()


@pytest.mark.django_db
def test_directory_index_business_first(client):
    html = client.get("/links/").content.decode()
    assert html.index('id="business"') < html.index('id="links"')
    assert html.index('href="#business"') < html.index('href="#links"')

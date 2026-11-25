"""Центр ураганов (/uragany/) и «Иммиграция: что изменилось» (/immigraciya/)."""

from datetime import date

import pytest

from hubs.models import Program
from hubs.views import hurricane_resources, season

pytestmark = pytest.mark.django_db


def test_season_dates():
    assert season(date(2026, 9, 10))["active"] and season(date(2026, 9, 10))["days_left"] == 81
    off = season(date(2026, 12, 5))
    assert not off["active"] and off["starts"] == date(2027, 6, 1)
    assert season(date(2027, 3, 1))["starts"] == date(2027, 6, 1)


def test_hurricane_page_lists_counties(client):
    html = client.get("/uragany/").content.decode()
    assert "<h1 class=\"story__title\">Центр ураганов</h1>" in html and 'content="index, follow' in html
    counties = hurricane_resources()["counties"]
    if counties:  # справочник округов из hubs/data/hurricane.json
        assert counties[0]["county_ru"] in html
    assert "/uragany/" in client.get("/").content.decode()  # ссылка в подвале
    assert client.get("/uk/uragany/").status_code == 200


def test_immigration_page_shows_published_programs(client):
    Program.objects.all().delete()
    Program.objects.create(slug="tps-test", title="TPS для Украины (тест)", status=Program.Status.CHANGED,
                           summary="Положение на дату проверки.", what_to_do="Проверьте сроки.",
                           sources="USCIS — TPS Ukraine | https://www.uscis.gov/tps\nбез ссылки")
    Program.objects.create(slug="hidden", title="Скрытая программа", summary="—", is_published=False)
    html = client.get("/immigraciya/").content.decode()
    assert "TPS для Украины (тест)" in html and "Скрытая программа" not in html
    assert 'href="https://www.uscis.gov/tps"' in html and "изменено" in html
    assert "не юридическая консультация" in html
    assert Program.objects.get(slug="tps-test").source_links == [
        {"title": "USCIS — TPS Ukraine", "url": "https://www.uscis.gov/tps"}]

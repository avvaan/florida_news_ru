"""Блок «Куда сходить»: фестивали на главной и в рубрике «Афиша и события»."""

import json
import re
from datetime import date
from unittest import mock

import pytest

from news import featured

pytestmark = pytest.mark.django_db


def test_festivals_on_home_and_events_topic(client):
    with mock.patch("news.featured.timezone.localdate", return_value=date(2026, 10, 18)):
        home = client.get("/").content.decode()
        events = client.get("/topic/events/").content.decode()
    for html in (home, events):
        assert "Фестиваль славянской еды" in html and "Фестиваль грузинской культуры" in html
        assert "https://slavicfoodfestival.com/ru/tickets/" in html and "https://georgianfestival.com/ru/tickets/" in html
        assert "events/slavic-food-fest-480.webp" in html
    assert events.count('<section class="fests') == 1 and "fests--wide" in events  # в «Афише» — крупно, без дубля в колонке
    ld = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', events, re.S)]
    fest = next(d for d in ld if d.get("@type") == "Event" and "славянской" in d["name"])
    assert fest["startDate"].startswith("2027-02-27T10:00") and fest["location"]["address"]["addressLocality"] == "Casselberry"


def test_past_festival_hidden():
    assert [e.key for e in featured.upcoming(date(2027, 3, 1))] == ["georgian-festival-2027"]
    assert featured.upcoming(date(2027, 5, 9)) == []

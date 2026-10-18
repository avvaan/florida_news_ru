"""Блок «Куда сходить» и фестивали в афише: главная, рубрика «Афиша и события», /afisha/."""

import json
import re
from datetime import date
from unittest import mock

import pytest

from events.models import Event
from news import featured

pytestmark = pytest.mark.django_db

SLAVIC = "/afisha/festival-slavyanskoy-edy-2027-02-27/"
GEORGIAN = "/afisha/festival-gruzinskoy-kultury-2027-05-08/"
TODAY = date(2026, 10, 18)


def get(client, url):
    with mock.patch("news.featured.timezone.localdate", return_value=TODAY), \
         mock.patch("events.models.timezone.localdate", return_value=TODAY):
        return client.get(url).content.decode()


def test_festivals_on_home_and_events_topic(client):
    home, topic = get(client, "/"), get(client, "/topic/events/")
    for html in (home, topic):
        assert "Фестиваль славянской еды" in html and "Фестиваль грузинской культуры" in html
        assert f'href="{SLAVIC}"' in html and f'href="{GEORGIAN}"' in html  # карточки ведут в афишу
        assert "https://slavicfoodfestival.com/ru/tickets/" in html and "events/slavic-food-fest-480.webp" in html
    assert topic.count('<section class="fests') == 1 and "fests--wide" in topic  # в рубрике — крупно, без дубля


def test_festivals_in_afisha_with_event_markup(client):
    assert Event.objects.published().filter(slug__in=featured.slugs()).count() == 2
    listing = get(client, "/afisha/")
    assert "fests--wide" in listing and 'content="noindex' not in listing
    assert listing.count(f'href="{SLAVIC}"') == 2  # крупная карточка (фото и заголовок), в сетке «Все события» — нет
    page = get(client, SLAVIC)
    ld = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)]
    event = next(d for d in ld if d.get("@type") == "Event")
    assert event["startDate"] == "2027-02-27T10:00" and event["location"]["address"]["addressLocality"] == "Касселберри"
    assert event["image"][0].endswith("/static/events/slavic-food-fest.jpg")
    assert "Миссия Святой Нины" in page and "https://slavicfoodfestival.com/ru/tickets/" in page


def test_past_festival_hidden():
    assert [e.key for e in featured.upcoming(date(2027, 3, 1))] == ["georgian-festival-2027"]
    assert featured.upcoming(date(2027, 5, 9)) == []

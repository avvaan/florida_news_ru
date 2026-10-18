"""Избранные события для блока «Куда сходить» на главной и в рубрике «Афиша и события».

Список ведётся вручную: новое событие — новая запись, картинки — в static/events/
({image}-960.webp, {image}-480.webp и {image}.jpg 1200×630 для страницы события и соцсетей).
Само событие с разметкой Event — в афише (приложение events), карточки ведут на его страницу.
Событие показывается до конца дня окончания, потом скрывается само.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from django.urls import reverse
from django.utils import timezone


@dataclass(frozen=True)
class FeaturedEvent:
    key: str
    title: str
    teaser: str
    day: date
    starts: time
    ends: time
    venue: str
    address: str
    city: str
    price: str
    url: str
    tickets_url: str
    image: str
    image_alt: str
    tag: str
    slug: str  # событие в афише /afisha/<slug>/ (events/migrations/0003_festivals_2027.py)

    @property
    def page_url(self) -> str:
        return reverse("events:detail", args=[self.slug])

    @property
    def start_dt(self) -> datetime:
        return timezone.make_aware(datetime.combine(self.day, self.starts))

    @property
    def end_dt(self) -> datetime:
        return timezone.make_aware(datetime.combine(self.day, self.ends))

    @property
    def image_static(self) -> str:
        return f"events/{self.image}"


EVENTS = [
    FeaturedEvent(
        key="slavic-food-fest-2027",
        title="Фестиваль славянской еды",
        teaser="Борщ, блины, шашлык, квас и медовуха, живая народная музыка и танцы — "
               "семейный праздник на целый день.",
        day=date(2027, 2, 27), starts=time(10), ends=time(20),
        venue="German American Society", address="381 Orange Lane", city="Касселберри",
        price="Вход $10, дети до 12 лет — $5",
        url="https://slavicfoodfestival.com/ru/", tickets_url="https://slavicfoodfestival.com/ru/tickets/",
        image="slavic-food-fest", image_alt="Танцоры в народных костюмах на Slavic Food Festival",
        tag="Еда и музыка", slug="festival-slavyanskoy-edy-2027-02-27",
    ),
    FeaturedEvent(
        key="georgian-festival-2027",
        title="Фестиваль грузинской культуры",
        teaser="Хачапури, хинкали, мцвади и грузинское вино, многоголосие и народные танцы, "
               "концерт Trio Mandili.",
        day=date(2027, 5, 8), starts=time(10), ends=time(20),
        venue="German American Society", address="381 Orange Lane", city="Касселберри",
        price="Вход $20, дети 5–12 лет — $10, до 5 лет — бесплатно",
        url="https://georgianfestival.com/ru/", tickets_url="https://georgianfestival.com/ru/tickets/",
        image="georgian-festival", image_alt="Trio Mandili в грузинских костюмах",
        tag="Концерт Trio Mandili", slug="festival-gruzinskoy-kultury-2027-05-08",
    ),
]


def slugs() -> set[str]:
    return {e.slug for e in EVENTS}


def upcoming(today: date | None = None) -> list[FeaturedEvent]:
    today = today or timezone.localdate()
    return sorted((e for e in EVENTS if e.day >= today), key=lambda e: e.day)

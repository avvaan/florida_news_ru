"""Избранные события для блока «Куда сходить» на главной и в рубрике «Афиша и события».

Список ведётся вручную: новое событие — новая запись, картинки — в static/events/
({image}-960.webp, {image}-480.webp и {image}.jpg 1200×630 для страницы события и соцсетей).
Само событие с разметкой Event — в афише (приложение events), карточки ведут на его страницу.
Событие показывается до конца дня окончания, потом скрывается само.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from django.urls import reverse
from django.utils import timezone


@dataclass(frozen=True)
class FeaturedEvent:
    key: str
    title: str
    teaser: str
    day: date
    starts: time | None  # None — время не объявлено
    ends: time | None
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
    FeaturedEvent(
        key="po-shchuchemu-veleniyu-2026",
        title="«По щучьему велению» — новогодний спектакль для всей семьи",
        teaser="Музыкальная сказка от Musical Traditions: Емеля, волшебная щука, живая музыка и костюмы "
               "ручной работы, а после спектакля — Дед Мороз, Снегурочка, игры и подарки для детей.",
        day=date(2026, 12, 19), starts=None, ends=None,
        venue="William Beardall Senior Center", address="800 S Delaney Ave", city="Орландо",
        price="Детский билет $35, взрослый $25, подарок $20; есть семейные пакеты",
        url="https://www.canva.com/design/DAHXLSxyx8U/uendstZqgOEvkhzameiYdg/view",
        tickets_url="https://www.canva.com/design/DAHXLSxyx8U/uendstZqgOEvkhzameiYdg/view",
        image="po-shchuchemu-veleniyu", image_alt="Актёры в костюмах героев сказки «По щучьему велению»",
        tag="Детям и семьям", slug="po-shchuchemu-veleniyu-muzykalnyy-novogodniy-spektakl-dlya-vsey-semi-2026-12-19",
    ),
]

# Порядок в блоке: сначала фестивали (по дате), потом остальное (по дате).
FESTIVAL_KEYS = {"slavic-food-fest-2027", "georgian-festival-2027"}


def slugs() -> set[str]:
    return {e.slug for e in EVENTS}


def upcoming(today: date | None = None) -> list[FeaturedEvent]:
    today = today or timezone.localdate()
    return sorted((e for e in EVENTS if e.day >= today), key=lambda e: (e.key not in FESTIVAL_KEYS, e.day))

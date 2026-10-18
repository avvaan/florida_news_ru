"""Афиша: фестивали славянской еды (27.02.2027) и грузинской культуры (08.05.2027) от редакции.

Картинки — с сайтов фестивалей, лежат в static/events/ (тот же набор показывает блок «Куда сходить»,
news/featured.py). Слаги фиксированные: на них ссылаются карточки на главной.
"""

from datetime import date, time

from django.db import migrations
from django.utils import timezone

FESTIVALS = [
    {
        "slug": "festival-slavyanskoy-edy-2027-02-27",
        "title": "Фестиваль славянской еды",
        "description": "Семейный праздник на целый день в Касселберри: борщ, блины, болгарские фаршированные "
                       "перцы, булочки и шашлык на углях, домашний квас, компот и медовуха. В программе — "
                       "живая народная музыка, украинские песни, сербские и другие народные танцы, выступления "
                       "детей и концерт Musical Traditions. Входной билет — $10, для детей до 12 лет — $5, "
                       "семейный пакет на двух взрослых и двоих детей — $25.",
        "starts_on": date(2027, 2, 27),
        "price": "$10, дети до 12 лет — $5",
        "url": "https://slavicfoodfestival.com/ru/tickets/",
        "image": "slavic-food-fest.jpg",
    },
    {
        "slug": "festival-gruzinskoy-kultury-2027-05-08",
        "title": "Фестиваль грузинской культуры и концерт Trio Mandili",
        "description": "Грузинский праздник в Касселберри: хачапури, хинкали, мцвади на углях, бадриджани, "
                       "лобио, пхали и чурчхела, грузинское вино (21+). Живое многоголосие, народные танцы "
                       "Аджарии, Картли и Сванетии и концерт Trio Mandili. Вход — $20, для детей 5–12 лет — "
                       "$10, до 5 лет — бесплатно; ближе к фестивалю цены могут вырасти.",
        "starts_on": date(2027, 5, 8),
        "price": "$20, дети 5–12 лет — $10, до 5 лет бесплатно",
        "url": "https://georgianfestival.com/ru/tickets/",
        "image": "georgian-festival.jpg",
    },
]


def add_festivals(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    Region = apps.get_model("news", "Region")
    now = timezone.now()
    for f in FESTIVALS:
        Event.objects.update_or_create(slug=f["slug"], defaults={
            "status": "approved", "title": f["title"], "description": f["description"],
            "starts_on": f["starts_on"], "starts_at": time(10), "ends_on": None,
            "venue": "German American Society", "address": "381 Orange Lane", "city": "Касселберри",
            "region": Region.objects.filter(slug="orlando").first(), "price": f["price"], "url": f["url"],
            "organizer": "Миссия Святой Нины",
            # Полный адрес на основном домене: поле URLField, а sitemap и разметка Event требуют абсолютных ссылок.
            "image_url": f"https://florida-ru.com/static/events/{f['image']}", "image_status": "published",
            "image_note": "Фото с сайта фестиваля, добавила редакция",
            "contact_name": "Редакция Florida RU", "contact_email": "info@citrustack.com",
            "violation": "none", "reason": "Добавлено редакцией", "moderated_at": now,
        })


def remove_festivals(apps, schema_editor):
    apps.get_model("events", "Event").objects.filter(slug__in=[f["slug"] for f in FESTIVALS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0002_privacy_events"),
        ("news", "0008_merge_duplicates_urgent_toponyms"),
    ]

    operations = [migrations.RunPython(add_festivals, remove_festivals)]

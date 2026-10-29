"""«Ёлка-2027» в Винтер-Парке, 12.12.2026 (пост организаторов в группах Орландо, таблица редакции от 28.10.2026).

Организаторы — Musical Traditions; они уже присылали события через форму. Если «Ёлка» на эту дату уже есть
в афише, второй раз не добавляем.
"""

from datetime import date, time

from django.db import migrations
from django.utils import timezone

from core.text import make_slug

DAY = date(2026, 12, 12)
TITLE = "Ёлка-2027: интерактивное шоу для детей"
CITY = "Винтер-Парк"
SLUG = make_slug(f"{TITLE} {CITY} {DAY:%Y-%m-%d}", max_length=110)


def add_event(apps, schema_editor):
    Event = apps.get_model("events", "Event")
    if Event.objects.filter(starts_on=DAY, title__icontains="ёлк").exclude(slug=SLUG).exists():
        return
    Event.objects.update_or_create(slug=SLUG, defaults={
        "status": "approved", "title": TITLE,
        "description": "Новогоднее интерактивное шоу для детей на русском языке. Winter Park Community Center, "
                       "начало в 12:00. Подробности и билеты — на странице организаторов.",
        "starts_on": DAY, "starts_at": time(12), "ends_on": None,
        "venue": "Winter Park Community Center", "address": "721 W New England Ave", "city": CITY,
        "region": apps.get_model("news", "Region").objects.filter(slug="orlando").first(),
        "url": "https://musicaltraditions.my.canva.site/elka-orlando-2027", "organizer": "Musical Traditions",
        "contact_name": "Musical Traditions", "contact_email": "russianflorida@yahoo.com",
        "violation": "none", "reason": "Добавлено редакцией по таблице от 28.10.2026", "moderated_at": timezone.now(),
    })


def remove_event(apps, schema_editor):
    apps.get_model("events", "Event").objects.filter(slug=SLUG).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0005_po_shchuchemu_veleniyu_image"),
        ("news", "0012_article_cover_manual"),
    ]

    operations = [migrations.RunPython(add_event, remove_event)]

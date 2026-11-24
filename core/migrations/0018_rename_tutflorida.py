"""Сайт переименован: «Florida RU» (florida-ru.com) → «TutFlorida» (tutflorida.com), ноябрь 2026.

Меняем название и адрес в текстах из базы: страницы «О проекте» и «Конфиденциальность» (обе версии),
описание бизнеса-издателя в справочнике, картинки и подписи событий из афиши, которые добавляла редакция.
Почтовый адрес редакции (info@florida-ru.com) не трогаем — его меняют в настройках сайта, когда заработает
почта на новом домене.
"""
from django.db import migrations
from django.db.models import Value
from django.db.models.functions import Replace

PAIRS = [("Florida RU", "TutFlorida"), ("https://florida-ru.com", "https://tutflorida.com"),
         ("(florida-ru.com)", "(tutflorida.com)")]
FIELDS = [("core", "Page", ["body", "body_uk"]),
          ("directory", "Listing", ["description", "editor_note"]),
          ("events", "Event", ["image_url", "contact_name"])]


def rename(apps, schema_editor):
    for app, model, fields in FIELDS:
        Model = apps.get_model(app, model)
        for field in fields:
            for old, new in PAIRS:
                Model.objects.filter(**{f"{field}__contains": old}).update(
                    **{field: Replace(field, Value(old), Value(new))})


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0017_uk_pages"),
        ("directory", "0015_ukrainian"),
        ("events", "0008_ukrainian"),
    ]

    operations = [migrations.RunPython(rename, migrations.RunPython.noop)]

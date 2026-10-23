"""Публичные Telegram-каналы как полноценные источники новостей (решение редакции, октябрь 2026).

Каналы проверены 23.10.2026 по их публичным страницам t.me/s/…: открытые каналы, посты в тот же день
(у @icemlaw1 — 14 октября). Посты идут в ленту так же, как записи RSS: склейка, отбор, заметка своими
словами, проверка. Читаются через Telethon (TG_API_ID, TG_API_HASH, TG_SESSION).
"""

from django.db import migrations, models

# name, @username, вес доверия, заметка
CHANNELS = [
    ("Голос Америки (Telegram)", "GolosAmeriki", 7, "Госвещатель США на русском: выборы, законы, мировые новости"),
    ("Новости США | Америки (Telegram)", "news_about_USA", 5,
     "Агрегатор новостей США, много постов в день; владелец не указан — бывают политические цитаты"),
    ("Континент (Telegram)", "kontinentusa", 6, "Русскоязычное интернет-издание в США"),
    ("Иммиграционный адвокат Екатерина Муратова (Telegram)", "icemlaw1", 6,
     "Решения судов и USCIS по убежищу и визам; канал юридической фирмы"),
    ("ЭкспатFM (Telegram)", "expatfm", 5, "Новостной портал для релокантов, не только США"),
    ("USA.ONE: Новости США (Telegram)", "usaonenews", 5, "Новости США от USA.ONE, у издания есть раздел по Флориде"),
]


def add_channels(apps, schema_editor):
    Source = apps.get_model("sources", "Source")
    for name, username, trust, notes in CHANNELS:
        url = f"https://t.me/{username}"
        Source.objects.get_or_create(url=url, defaults={
            "name": name, "homepage": url, "kind": "telegram", "source_type": "media", "trust_weight": trust,
            "is_active": True, "is_verified": True, "notes": f"Telegram-канал @{username}. {notes}",
        })


class Migration(migrations.Migration):

    dependencies = [
        ("sources", "0004_business_sources"),
    ]

    operations = [
        migrations.AlterField(
            model_name="source",
            name="kind",
            field=models.CharField(
                choices=[("rss", "RSS / Atom"), ("nws_alerts", "NWS alerts API (GeoJSON)"),
                         ("telegram", "Telegram-канал (публичный)")],
                default="rss", max_length=20, verbose_name="формат",
            ),
        ),
        migrations.RunPython(add_channels, migrations.RunPython.noop),
    ]

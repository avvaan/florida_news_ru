"""Официальный источник по налогам: пресс-релизы IRS.

Своего RSS у IRS нет — берём ленту Bing News с поиском по irs.gov/newsroom (robots.txt разрешает);
ссылки-переходники Bing сборщик раскрывает в прямые адреса irs.gov.
"""

from django.db import migrations

URL = "https://www.bing.com/news/search?q=site%3airs.gov%2fnewsroom&format=rss"


def add_irs(apps, schema_editor):
    Source = apps.get_model("sources", "Source")
    Source.objects.get_or_create(url=URL, defaults={
        "name": "IRS (налоговая служба США)", "homepage": "https://www.irs.gov/newsroom", "kind": "rss",
        "source_type": "official", "region": apps.get_model("news", "Region").objects.filter(slug="florida").first(),
        "trust_weight": 9, "is_active": True, "is_verified": True,
        "notes": "Пресс-релизы IRS через Bing News (своего RSS нет). Федеральные новости — отбор решает, "
                 "важно ли это для Флориды (например, налоговые льготы после ураганов)",
    })


class Migration(migrations.Migration):

    dependencies = [
        ("sources", "0002_seed_data"),
        ("news", "0008_merge_duplicates_urgent_toponyms"),
    ]

    operations = [migrations.RunPython(add_irs, migrations.RunPython.noop)]

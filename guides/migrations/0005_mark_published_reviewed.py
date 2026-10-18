"""Аудит 10.2026: опубликованные гайды редактор проверил и оставляет на сайте — отмечаем «проверено человеком»."""

from django.db import migrations
from django.utils import timezone


def mark_published_reviewed(apps, schema_editor):
    Guide = apps.get_model("guides", "Guide")
    Guide.objects.filter(status="published").update(human_reviewed=True, reviewed_at=timezone.now())


class Migration(migrations.Migration):

    dependencies = [
        ("guides", "0004_human_review"),
    ]

    operations = [migrations.RunPython(mark_published_reviewed, migrations.RunPython.noop)]

import json
from pathlib import Path

from django.db import migrations


def load(apps, schema_editor):
    """Стартовые карточки «Иммиграция: что изменилось» (ресёрч 25.11.2026). Дальше правит редактор в админке."""
    Program = apps.get_model("hubs", "Program")
    rows = json.loads((Path(__file__).resolve().parents[1] / "data" / "immigration.json").read_text(encoding="utf-8"))
    for row in rows:
        Program.objects.get_or_create(slug=row["slug"], defaults={k: v for k, v in row.items() if k != "slug"})


class Migration(migrations.Migration):

    dependencies = [("hubs", "0001_initial")]

    operations = [migrations.RunPython(load, migrations.RunPython.noop)]

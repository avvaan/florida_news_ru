from django.db import migrations

from core import seed


def drop_visitor_keys(apps, schema_editor):
    """Дневные коды старого счётчика: политика обещала удалять их через два дня, а чистил их сам счётчик."""
    apps.get_model("stats", "VisitorKey").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("stats", "0003_hit"),
        ("core", "0013_contact_email"),
    ]

    operations = [
        migrations.RunPython(seed.update_privacy_beacon, migrations.RunPython.noop),
        migrations.RunPython(drop_visitor_keys, migrations.RunPython.noop),
    ]

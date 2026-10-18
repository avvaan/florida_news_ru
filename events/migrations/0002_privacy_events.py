from django.db import migrations

from core import seed


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0001_initial"),
        ("core", "0010_write_threshold_4"),
        ("directory", "0010_privacy_submissions"),
    ]

    operations = [migrations.RunPython(seed.update_privacy_events, migrations.RunPython.noop)]

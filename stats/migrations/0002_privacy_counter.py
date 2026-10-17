from django.db import migrations

from core import seed


class Migration(migrations.Migration):

    dependencies = [
        ("stats", "0001_initial"),
        ("core", "0009_value_seo_data"),
    ]

    operations = [migrations.RunPython(seed.update_privacy_counter, migrations.RunPython.noop)]

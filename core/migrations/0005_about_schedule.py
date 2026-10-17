from django.db import migrations

from core import seed


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_privacy_owner"),
    ]

    operations = [migrations.RunPython(seed.update_about_schedule, migrations.RunPython.noop)]

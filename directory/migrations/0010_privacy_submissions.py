from django.db import migrations

from core import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0009_business_submissions"),
        ("stats", "0002_privacy_counter"),
    ]

    operations = [migrations.RunPython(seed.update_privacy_submissions, migrations.RunPython.noop)]

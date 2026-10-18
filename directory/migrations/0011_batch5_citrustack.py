from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0010_privacy_submissions"),
    ]

    operations = [migrations.RunPython(seed.import_batch5, migrations.RunPython.noop)]

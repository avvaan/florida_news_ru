from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0015_ukrainian"),
    ]

    operations = [migrations.RunPython(seed.import_batch9_doctors, migrations.RunPython.noop)]

from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0007_batch3_verified_table"),
    ]

    operations = [migrations.RunPython(seed.import_batch4, migrations.RunPython.noop)]

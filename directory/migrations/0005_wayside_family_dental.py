from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0004_import_businesses"),
    ]

    operations = [migrations.RunPython(seed.import_wayside, migrations.RunPython.noop)]

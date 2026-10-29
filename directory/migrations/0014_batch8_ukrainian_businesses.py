from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0013_batch7_osetinskie_pirogi"),
    ]

    operations = [migrations.RunPython(seed.import_batch8, migrations.RunPython.noop)]

from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0011_batch5_citrustack"),
    ]

    operations = [migrations.RunPython(seed.import_batch6, migrations.RunPython.noop)]

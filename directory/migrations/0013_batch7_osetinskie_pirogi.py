from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0012_batch6_churches"),
    ]

    operations = [migrations.RunPython(seed.import_batch7, migrations.RunPython.noop)]

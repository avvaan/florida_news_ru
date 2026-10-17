from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0005_wayside_family_dental"),
    ]

    operations = [migrations.RunPython(seed.import_batch2, migrations.RunPython.noop)]

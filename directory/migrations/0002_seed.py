from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0001_initial"),
        ("news", "0003_seed_data"),
    ]

    operations = [migrations.RunPython(seed.seed_directory, migrations.RunPython.noop)]

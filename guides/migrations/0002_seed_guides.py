from django.db import migrations

from guides import seed


class Migration(migrations.Migration):

    dependencies = [
        ("guides", "0001_initial"),
        ("news", "0003_seed_data"),
    ]

    operations = [migrations.RunPython(seed.seed_guides, migrations.RunPython.noop)]

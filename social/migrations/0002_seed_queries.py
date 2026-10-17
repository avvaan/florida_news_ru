from django.db import migrations

from social import seed


class Migration(migrations.Migration):

    dependencies = [
        ("social", "0001_initial"),
        ("news", "0003_seed_data"),
    ]

    operations = [migrations.RunPython(seed.seed_signal_sources, migrations.RunPython.noop)]

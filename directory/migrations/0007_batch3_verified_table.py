from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0006_batch2_lacomka_greenhills"),
    ]

    operations = [migrations.RunPython(seed.import_batch3, migrations.RunPython.noop)]

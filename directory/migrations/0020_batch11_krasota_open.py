from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0019_batch10_krasota"),
    ]

    operations = [migrations.RunPython(seed.import_batch11_krasota_open, migrations.RunPython.noop)]

from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0018_listing_photo"),
    ]

    operations = [migrations.RunPython(seed.import_batch10_krasota, migrations.RunPython.noop)]

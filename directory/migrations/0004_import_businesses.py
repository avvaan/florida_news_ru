from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0003_listing_editor_note"),
    ]

    operations = [migrations.RunPython(seed.import_businesses, migrations.RunPython.noop)]

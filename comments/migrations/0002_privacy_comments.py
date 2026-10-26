from django.db import migrations

from core import seed


class Migration(migrations.Migration):

    dependencies = [
        ("comments", "0001_initial"),
        ("classifieds", "0002_categories_and_privacy"),
    ]

    operations = [migrations.RunPython(seed.update_privacy_comments, migrations.RunPython.noop)]

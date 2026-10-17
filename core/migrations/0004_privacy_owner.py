from django.db import migrations

from core import seed


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_publish_without_review"),
    ]

    operations = [migrations.RunPython(seed.update_privacy_owner, migrations.RunPython.noop)]

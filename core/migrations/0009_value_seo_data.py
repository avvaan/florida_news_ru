from django.db import migrations

from core import seed


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_author_publication_limit"),
    ]

    operations = [
        migrations.RunPython(seed.publication_limit_and_author, migrations.RunPython.noop),
        migrations.RunPython(seed.update_about_and_brand, migrations.RunPython.noop),
    ]

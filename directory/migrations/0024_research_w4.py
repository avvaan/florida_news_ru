from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0023_research_w3"),
    ]

    operations = [
        migrations.RunPython(seed.import_research_wave("businesses_2026_11_res_w4.json"), migrations.RunPython.noop),
    ]

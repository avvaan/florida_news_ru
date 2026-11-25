from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0020_batch11_krasota_open"),
    ]

    operations = [
        migrations.RunPython(seed.import_research_wave("businesses_2026_11_res_w1.json"), migrations.RunPython.noop),
    ]

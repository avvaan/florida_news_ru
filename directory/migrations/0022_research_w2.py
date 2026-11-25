from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0021_research_w1"),
    ]

    operations = [
        migrations.RunPython(seed.import_research_wave("businesses_2026_11_res_w2.json"), migrations.RunPython.noop),
    ]

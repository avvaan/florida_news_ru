from django.db import migrations

from directory import seed


class Migration(migrations.Migration):

    dependencies = [
        ("directory", "0022_research_w2"),
    ]

    operations = [
        migrations.RunPython(seed.import_research_wave("businesses_2026_11_res_w3.json"), migrations.RunPython.noop),
    ]

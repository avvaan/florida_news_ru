from django.db import migrations


def shorten(apps, schema_editor):
    """В меню — коротко «ЧП», чтобы все пункты помещались в одну строку; заголовок раздела — «ЧП и происшествия»."""
    apps.get_model("news", "Topic").objects.filter(slug="safety").update(short_name="ЧП")


class Migration(migrations.Migration):

    dependencies = [("news", "0010_merged_topics")]

    operations = [migrations.RunPython(shorten, migrations.RunPython.noop)]

from django.db import migrations

from core import seed


def add_categories(apps, schema_editor):
    from classifieds.data import SECTIONS

    Category = apps.get_model("classifieds", "Category")
    for n, (slug, name, description, children) in enumerate(SECTIONS):
        section, _ = Category.objects.update_or_create(
            slug=slug, defaults={"name": name, "description": description, "order": n * 10, "parent": None})
        for m, (child_slug, child_name, price_label) in enumerate(children):
            Category.objects.update_or_create(slug=child_slug, defaults={
                "name": child_name, "parent": section, "price_label": price_label, "order": m * 10})


class Migration(migrations.Migration):

    dependencies = [
        ("classifieds", "0001_initial"),
        ("events", "0002_privacy_events"),
        ("core", "0011_dmca_agent_name"),
    ]

    operations = [
        migrations.RunPython(add_categories, migrations.RunPython.noop),
        migrations.RunPython(seed.update_privacy_classifieds, migrations.RunPython.noop),
    ]

from django.db import migrations

# Пары тем в меню объединены: «ЧП» + «Происшествия», «Деньги» + «Бизнес» (а «Афиша» ведёт в раздел /afisha/).
# Меняем только названия общих разделов; заметки остаются в своих темах.
NAMES = {
    "safety": ("ЧП и происшествия", "ЧП и происшествия",
               "Ураганы, пожары, наводнения, аварии, преступления и происшествия во Флориде — коротко на русском."),
    "business": ("Деньги и бизнес", "Деньги и бизнес",
                 "Цены, налоги, пособия, акции компаний Флориды и крупные сделки — коротко на русском."),
}
OLD = {
    "safety": ("Безопасность и ЧП", "ЧП"),
    "business": ("Бизнес: акции и сделки", "Бизнес"),
}


def rename(apps, schema_editor):
    Topic = apps.get_model("news", "Topic")
    for slug, (name, short, description) in NAMES.items():
        Topic.objects.filter(slug=slug).update(name=name, short_name=short, description=description)


def unrename(apps, schema_editor):
    Topic = apps.get_model("news", "Topic")
    for slug, (name, short) in OLD.items():
        Topic.objects.filter(slug=slug).update(name=name, short_name=short)


class Migration(migrations.Migration):

    dependencies = [("news", "0009_business")]

    operations = [migrations.RunPython(rename, unrename)]

from django.db import migrations, models

EMAIL = "info@florida-ru.com"


def set_email(apps, schema_editor):
    apps.get_model("core", "SiteSettings").objects.filter(contact_email="").update(contact_email=EMAIL)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_business"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitesettings",
            name="contact_email",
            field=models.EmailField(blank=True, default=EMAIL, max_length=254, verbose_name="e-mail редакции"),
        ),
        migrations.RunPython(set_email, migrations.RunPython.noop),
    ]

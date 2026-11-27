"""Абзац об иммиграционном помощнике в политике конфиденциальности (если её не меняли так, что якоря нет)."""

from django.db import migrations

PRIVACY_IMMIGRATION = """Если вы пользуетесь иммиграционным помощником, мы храним ваш e-mail (для входа по одноразовому коду), \
регион, если вы его указали, и согласие с тем, что помощник даёт общую информацию, а не юридическую консультацию: \
дату, версию текста и IP-адрес. Вопросы и ответы хранятся 30 дней и удаляются автоматически; номера дел USCIS, \
A-number и SSN, если вы их написали, скрываются до сохранения и до отправки в модель ИИ. Вопросы обрабатывает \
модель ИИ компании DeepSeek. Аккаунт и всю историю можно удалить самостоятельно на странице помощника."""

ANCHOR = "По вопросам, связанным с данными"


def add(apps, schema_editor):
    Page = apps.get_model("core", "Page")
    page = Page.objects.filter(slug="privacy").first()
    if page and "иммиграционным помощником" not in page.body:
        paragraphs = page.body.replace("\r\n", "\n").split("\n\n")
        at = next((i for i, p in enumerate(paragraphs) if p.startswith(ANCHOR)), len(paragraphs))
        paragraphs.insert(at, PRIVACY_IMMIGRATION)
        page.body = "\n\n".join(paragraphs)
        page.save(update_fields=["body"])


class Migration(migrations.Migration):
    dependencies = [("immigration", "0001_initial"), ("kids", "0002_seed_cities_privacy")]

    operations = [migrations.RunPython(add, migrations.RunPython.noop)]

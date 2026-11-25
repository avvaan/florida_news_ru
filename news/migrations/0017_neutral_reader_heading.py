"""Подзаголовок «Что это значит для русскоязычных во Флориде» → «Что это значит для вас».

Сайт читают и русско-, и украиноязычные; на /uk/ подзаголовок превращался в «для російськомовних».
Промпт автора уже пишет нейтрально (pipeline/prompts.py), здесь — уже опубликованные заметки.
Если перевод был актуален, правим его так же и пересчитываем uk_hash, чтобы заметка не ушла
на платный повторный перевод из-за одного подзаголовка.
"""
import hashlib

from django.db import migrations

RU_OLD, RU_NEW = "## Что это значит для русскоязычных во Флориде", "## Что это значит для вас"
UK_OLD, UK_NEW = "## Що це означає для російськомовних у Флориді", "## Що це означає для вас"
TRANSLATED = ("title", "teaser", "body", "for_you")  # news.models.Article.TRANSLATED


def source_hash(article) -> str:  # core.i18n.Translatable.source_hash
    text = "\x00".join(str(getattr(article, name) or "") for name in TRANSLATED)
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def neutral_heading(apps, schema_editor):
    Article = apps.get_model("news", "Article")
    for article in Article.objects.filter(body__contains=RU_OLD):
        was_current = article.uk_hash == source_hash(article)
        article.body = article.body.replace(RU_OLD, RU_NEW)
        fields = ["body"]
        if was_current:
            article.body_uk = article.body_uk.replace(UK_OLD, UK_NEW)
            article.uk_hash = source_hash(article)
            fields += ["body_uk", "uk_hash"]
        article.save(update_fields=fields)


class Migration(migrations.Migration):
    dependencies = [("news", "0016_keep_indexed_help_150")]

    operations = [migrations.RunPython(neutral_heading, migrations.RunPython.noop)]

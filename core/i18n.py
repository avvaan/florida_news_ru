"""Украинская версия контента.

Строки интерфейса переводятся обычным gettext ({% translate %}, gettext) — locale/uk/LC_MESSAGES/django.po.
Контент из базы (заметки, гайды, афиша, справочник, рубрики) хранит перевод рядом с оригиналом
в полях <поле>_uk. Модель наследует Translatable и перечисляет переводимые поля в TRANSLATED:

    class Article(Translatable):
        TRANSLATED = ("title", "teaser", "body", "for_you")
        title_uk = models.CharField(...)

В шаблонах — {{ article.tr.title }}: на /uk/… это украинский текст, а пока перевода нет —
русский оригинал. В Python — article.loc("title").

Перевод делает ИИ (core/translation.py, команда translate_content). uk_hash — хеш русских
полей на момент перевода: если оригинал поправили, перевод считается устаревшим и обновится.
"""

from __future__ import annotations

import hashlib

from django.db import models
from django.utils import translation

UK = "uk"


def is_uk() -> bool:
    return (translation.get_language() or "").startswith(UK)


class Localized:
    """{{ obj.tr.<поле> }} — поле на текущем языке с откатом на русский."""

    __slots__ = ("_obj",)

    def __init__(self, obj):
        self._obj = obj

    def __getattr__(self, name):
        return self._obj.loc(name)


class Translatable(models.Model):
    TRANSLATED: tuple[str, ...] = ()

    uk_hash = models.CharField("хеш оригинала перевода", max_length=16, blank=True, default="", editable=False)

    class Meta:
        abstract = True

    def loc(self, name: str):
        if is_uk() and name in self.TRANSLATED and (value := getattr(self, f"{name}_uk", "")):
            return value
        return getattr(self, name)

    @property
    def tr(self) -> Localized:
        return Localized(self)

    @property
    def has_uk(self) -> bool:
        """Есть ли украинский перевод (главное поле заполнено)."""
        return bool(self.TRANSLATED) and bool(getattr(self, f"{self.TRANSLATED[0]}_uk", ""))

    @property
    def shown_translated(self) -> bool:
        """Страница на текущем языке показана целиком на нём: по-русски всегда, по-украински — если есть перевод."""
        return not is_uk() or self.has_uk

    def source_hash(self) -> str:
        text = "\x00".join(str(getattr(self, name) or "") for name in self.TRANSLATED)
        return hashlib.sha1(text.encode()).hexdigest()[:16]

    @property
    def uk_outdated(self) -> bool:
        return self.uk_hash != self.source_hash()


def uk_field(field: models.Field) -> models.Field:
    """Копия поля для перевода: то же ограничение длины, необязательное, без индексов и подсказок."""
    name, path, args, kwargs = field.deconstruct()
    kwargs.update(blank=True, default="", verbose_name=f"{field.verbose_name} (укр.)")
    for key in ("unique", "db_index", "help_text", "choices", "null", "validators"):
        kwargs.pop(key, None)
    return field.__class__(*args, **kwargs)


def uk_fieldset(model) -> tuple:
    """Свёрнутый блок «Українською» для fieldsets в админке: перевод можно поправить руками."""
    return ("Украинская версия (перевод ИИ, можно поправить)", {
        "classes": ("collapse",),
        "fields": tuple(f"{name}_uk" for name in model.TRANSLATED),
        "description": "Пусто — на украинской версии показывается русский текст. Перевод обновляется сам, "
                       "когда меняют русский текст; правки здесь затрутся при следующей правке оригинала.",
    })

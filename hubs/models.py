"""Тематические центры: «Иммиграция: что изменилось» (карточки программ правит редактор в админке).

Центр ураганов (/uragany/) живёт на данных из базы (предупреждения NWS, записи NHC, заметки о погоде)
и на справочнике официальных ссылок по округам — hubs/data/hurricane.json, правится файлом.
"""

from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.i18n import Translatable, uk_field


class ProgramQuerySet(models.QuerySet):
    def published(self):
        return self.filter(is_published=True).order_by("order", "title")


class Program(Translatable):
    """Иммиграционная программа или правило: статус, что изменилось, что делать, официальные источники."""

    class Status(models.TextChoices):
        ACTIVE = "active", "действует"
        CHANGED = "changed", "изменено"
        PENDING = "pending", "ожидается решение"
        PAUSED = "paused", "приостановлено"
        ENDED = "ended", "отменено"

    slug = models.SlugField("адрес (латиница)", max_length=80, unique=True)
    title = models.CharField("программа или правило", max_length=120)
    status = models.CharField("статус", max_length=10, choices=Status.choices, default=Status.ACTIVE)
    summary = models.TextField("что сейчас", help_text="2–4 предложения: положение на дату проверки, ключевые даты")
    what_to_do = models.TextField("что делать", blank=True, help_text="1–3 предложения: что проверить или сделать")
    changed_on = models.DateField("последнее изменение", null=True, blank=True)
    checked_on = models.DateField("проверено редакцией", default=timezone.localdate)
    sources = models.TextField(
        "официальные источники", blank=True,
        help_text="По одному на строку: «Название | https://адрес»",
    )
    guide_slug = models.SlugField("гайд по теме (slug)", max_length=120, blank=True)
    order = models.PositiveSmallIntegerField("порядок", default=0)
    is_published = models.BooleanField("показывать", default=True)
    editor_note = models.TextField("заметка редакции", blank=True, help_text="Видна только в админке")
    updated_at = models.DateTimeField("изменено", auto_now=True)

    TRANSLATED = ("title", "summary", "what_to_do")
    title_uk = uk_field(title)
    summary_uk = uk_field(summary)
    what_to_do_uk = uk_field(what_to_do)

    objects = ProgramQuerySet.as_manager()

    class Meta:
        ordering = ["order", "title"]
        verbose_name = "иммиграционная программа"
        verbose_name_plural = "иммиграция: программы и правила"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("hubs:immigration") + f"#{self.slug}"

    @property
    def source_links(self) -> list[dict]:
        links = []
        for line in self.sources.splitlines():
            title, _, url = line.rpartition("|")
            url = url.strip()
            if url.startswith(("http://", "https://")):
                links.append({"title": title.strip() or url.split("/")[2], "url": url})
        return links

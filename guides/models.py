"""Гайды — постоянные полезные статьи. Создаются только черновиками, публикует редактор вручную."""

from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.text import make_slug

from . import markup


class GuideQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Guide.Status.PUBLISHED, published_at__isnull=False)

    def featured(self, limit: int = 8) -> list:
        """Блок «Полезное»: первый гайд каждого раздела в порядке разделов, затем остальные по алфавиту."""
        sections = [value for value, _ in Guide.Section.choices]
        guides = sorted(self.published(), key=lambda g: (
            g.order != 1, sections.index(g.section) if g.section in sections else len(sections), g.order, g.title,
        ))
        return guides[:limit]


class Guide(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "черновик"
        PUBLISHED = "published", "опубликован"

    class Section(models.TextChoices):
        DOCS = "docs", "Документы и статус"
        CAR = "car", "Машина"
        HOUSING = "housing", "Жильё"
        HURRICANES = "hurricanes", "Ураганы и безопасность"
        MONEY = "money", "Деньги и работа"
        HEALTH = "health", "Медицина"
        KIDS = "kids", "Дети и учёба"
        EVERYDAY = "everyday", "Повседневное"

    title = models.CharField("заголовок", max_length=160)
    slug = models.SlugField("адрес (латиница)", max_length=120, unique=True)
    teaser = models.CharField("анонс", max_length=300, blank=True)
    body = models.TextField(
        "текст", blank=True,
        help_text="Абзацы через пустую строку. Подзаголовок — отдельная строка, начинающаяся с «## »",
    )
    status = models.CharField("статус", max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    section = models.CharField("раздел", max_length=20, choices=Section.choices, blank=True, db_index=True)
    order = models.PositiveSmallIntegerField("порядок в разделе", default=0)
    cover = models.CharField(
        "обложка (static)", max_length=140, blank=True,
        help_text="Путь внутри static/ без расширения, например guides/florida-id-1 "
        "(нужны .webp, -640.webp и .jpg). Иллюстрации в тексте — guides/<slug>-2, -3 …",
    )
    content_hash = models.CharField(
        "хеш файла", max_length=64, blank=True, editable=False,
        help_text="import_guides обновляет гайд, только если файл guides/content/<slug>.md изменился",
    )
    topics = models.ManyToManyField("news.Topic", verbose_name="темы сайта", blank=True)
    brief = models.TextField("о чём гайд", blank=True, help_text="Подсказка для draft_guide: что раскрыть")
    official_domains = models.CharField(
        "официальные сайты", max_length=500, blank=True,
        help_text="Через запятую, например: flhsmv.gov, floridadisaster.org. draft_guide берёт факты только оттуда",
    )
    review_notes = models.TextField("замечания проверки", blank=True)

    created_at = models.DateTimeField("создан", default=timezone.now)
    updated_at = models.DateTimeField("изменён", auto_now=True)
    revised_at = models.DateTimeField("содержимое обновлено", null=True, blank=True)
    published_at = models.DateTimeField("опубликован", null=True, blank=True)
    telegram_posted_at = models.DateTimeField("отправлен в Telegram", null=True, blank=True)
    telegram_message_id = models.BigIntegerField("id сообщения в Telegram", null=True, blank=True)

    objects = GuideQuerySet.as_manager()

    class Meta:
        ordering = ["title"]
        verbose_name = "гайд"
        verbose_name_plural = "гайды"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("guides:detail", args=[self.slug])

    @property
    def is_published(self) -> bool:
        return self.status == self.Status.PUBLISHED and self.published_at is not None

    @property
    def domains(self) -> list[str]:
        return [d.strip().lower() for d in self.official_domains.split(",") if d.strip()]

    @property
    def blocks(self) -> list[markup.Block]:
        """Текст для шаблона: разделы, абзацы, списки, таблицы, врезки и иллюстрации (см. markup.py)."""
        return markup.parse(self.body)

    @property
    def toc(self) -> list[markup.Block]:
        return [b for b in self.blocks if b.kind == "h2"]

    def image(self, number: int) -> str:
        """Базовый путь иллюстрации в static/ без расширения: 1 — обложка, 2, 3 … — в тексте."""
        if number == 1:
            return self.cover
        return f"guides/{self.slug}-{number}" if self.cover else ""

    @property
    def reading_minutes(self) -> int:
        return max(1, round(markup.plain_length(self.body) / 1300))

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_slug(self.title, max_length=110) or "guide"
        super().save(*args, **kwargs)


class GuideSource(models.Model):
    guide = models.ForeignKey(Guide, on_delete=models.CASCADE, related_name="sources")
    name = models.CharField("сайт", max_length=120)
    url = models.URLField("ссылка", max_length=1000)
    title = models.CharField("название страницы", max_length=400, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "первоисточник"
        verbose_name_plural = "первоисточники"

    def __str__(self):
        return self.url

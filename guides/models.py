"""Гайды — постоянные полезные статьи. Создаются только черновиками, публикует редактор вручную."""

from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.text import make_slug


class GuideQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Guide.Status.PUBLISHED, published_at__isnull=False)


class Guide(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "черновик"
        PUBLISHED = "published", "опубликован"

    title = models.CharField("заголовок", max_length=160)
    slug = models.SlugField("адрес (латиница)", max_length=120, unique=True)
    teaser = models.CharField("анонс", max_length=300, blank=True)
    body = models.TextField(
        "текст", blank=True,
        help_text="Абзацы через пустую строку. Подзаголовок — отдельная строка, начинающаяся с «## »",
    )
    status = models.CharField("статус", max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
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
    def blocks(self) -> list[tuple[str, str]]:
        """Текст для шаблона: ("h", подзаголовок) или ("p", абзац)."""
        out = []
        for chunk in self.body.replace("\r\n", "\n").split("\n\n"):
            chunk = chunk.strip()
            if not chunk:
                continue
            if chunk.startswith("## "):
                heading, _, rest = chunk.partition("\n")
                out.append(("h", heading[3:].strip()))
                if rest.strip():
                    out.append(("p", rest.strip()))
            else:
                out.append(("p", chunk))
        return out

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

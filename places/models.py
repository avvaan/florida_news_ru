"""«Что посетить»: большие статьи о парках и достопримечательностях Флориды на русском и украинском.

Одна статья = одно направление (Эверглейдс, Disney World, Сент-Огастин …) в двух языковых версиях с общим slug.
Внутри — карточки мест (адрес, сайт, цена, часы работы) в разметке guides/markup.py: «[[place|Название]]».
Тексты лежат файлами places/content/<ru|uk>/<slug>.md, в базу их переносит import_places.
"""

from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override as language

from guides import markup

from .i18n import OTHER, REGIONS, region_name


class DestinationQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Destination.Status.PUBLISHED, published_at__isnull=False)

    def by_region(self, lang: str) -> list[dict]:
        """Опубликованные статьи языка по регионам: [{"slug", "name", "items"}] в порядке REGIONS."""
        items = list(self.published().filter(lang=lang).order_by("order", "title"))
        return [
            {"slug": slug, "name": names[lang], "items": found}
            for slug, names in REGIONS.items()
            if (found := [d for d in items if d.region == slug])
        ]


class Destination(models.Model):
    class Lang(models.TextChoices):
        RU = "ru", "русский"
        UK = "uk", "украинский"

    class Status(models.TextChoices):
        DRAFT = "draft", "черновик"
        PUBLISHED = "published", "опубликована"

    slug = models.SlugField("адрес (латиница)", max_length=110, help_text="Общий для русской и украинской версии")
    lang = models.CharField("язык", max_length=2, choices=Lang.choices, default=Lang.RU, db_index=True)
    title = models.CharField("заголовок", max_length=160)
    teaser = models.CharField("анонс", max_length=300, blank=True)
    body = models.TextField("текст", blank=True, help_text="Разметка как у гайдов + карточки мест «[[place|…]]»")
    region = models.CharField("регион", max_length=20, choices=[(k, v["ru"]) for k, v in REGIONS.items()],
                              db_index=True)
    order = models.PositiveSmallIntegerField("порядок в регионе", default=0)
    cover = models.CharField("обложка (static)", max_length=140, blank=True,
                             help_text="Путь внутри static/ без расширения: places/<slug>-1")
    cover_caption = models.CharField("подпись к обложке", max_length=300, blank=True)
    photo_credits = models.JSONField("авторство фото", default=dict, blank=True,
                                     help_text="{номер картинки: {credit, url}} — из places/content/photos/<slug>.json")
    status = models.CharField("статус", max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    checked_on = models.DateField("цены и часы проверены", null=True, blank=True)
    content_hash = models.CharField("хеш файла", max_length=64, blank=True, editable=False)

    created_at = models.DateTimeField("создана", default=timezone.now)
    updated_at = models.DateTimeField("изменена", auto_now=True)
    revised_at = models.DateTimeField("содержимое обновлено", null=True, blank=True)
    published_at = models.DateTimeField("опубликована", null=True, blank=True)

    objects = DestinationQuerySet.as_manager()

    class Meta:
        ordering = ["region", "order", "title"]
        constraints = [models.UniqueConstraint(fields=["slug", "lang"], name="destination_slug_lang")]
        verbose_name = "статья «Что посетить»"
        verbose_name_plural = "статьи «Что посетить»"

    def __str__(self):
        return f"{self.title} [{self.lang}]"

    def get_absolute_url(self):
        """/chto-posetit/<slug>/ или /uk/chto-posetit/<slug>/ — по языку статьи, а не страницы."""
        with language(self.lang):
            return reverse("places:detail", args=[self.slug])

    @property
    def is_published(self) -> bool:
        return self.status == self.Status.PUBLISHED and self.published_at is not None

    @property
    def translation(self):
        """Та же статья на другом языке (опубликованная) или None."""
        return Destination.objects.published().filter(slug=self.slug, lang=OTHER[self.lang]).first()

    @property
    def region_name(self) -> str:
        return region_name(self.region, self.lang)

    @property
    def blocks(self) -> list[markup.Block]:
        return markup.parse(self.body)

    @property
    def toc(self) -> list[markup.Block]:
        return [b for b in self.blocks if b.kind == "h2"]

    @property
    def places(self) -> list[markup.Block]:
        """Карточки мест в порядке текста."""
        return [b for b in self.blocks if b.kind == "place"]

    def image(self, number: int) -> str:
        """Базовый путь картинки в static/ без расширения: 1 — обложка, 2, 3 … — в тексте."""
        if number == 1:
            return self.cover
        return f"places/{self.slug}-{number}" if self.cover else ""

    def credit(self, number: int) -> dict:
        """{"credit": «Freepik», "url": ""} или {} — подпись «Фото: …» под картинкой."""
        value = self.photo_credits.get(str(number)) or {}
        return {"credit": value, "url": ""} if isinstance(value, str) else value

    @property
    def image_paths(self) -> list[str]:
        if not self.cover:
            return []
        return [self.cover, *(self.image(b.number) for b in self.blocks if b.kind == "img")]

    @property
    def image_files(self) -> list[str]:
        """Файлы всех картинок в static/ для sitemap и разметки: обложка — JPEG, остальные — WebP."""
        paths = self.image_paths
        return [f"{paths[0]}.jpg", *(f"{p}.webp" for p in paths[1:])] if paths else []

    @property
    def word_count(self) -> int:
        return len(self.body.split())

    @property
    def reading_minutes(self) -> int:
        return max(1, round(markup.plain_length(self.body) / 1300))


class DestinationSource(models.Model):
    destination = models.ForeignKey(Destination, on_delete=models.CASCADE, related_name="sources")
    name = models.CharField("сайт", max_length=120)
    url = models.URLField("ссылка", max_length=1000)
    title = models.CharField("название страницы", max_length=400, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "источник"
        verbose_name_plural = "источники"

    def __str__(self):
        return self.url

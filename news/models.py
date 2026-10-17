from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.text import make_slug

from .covers import all_covers, pick_cover


class Region(models.Model):
    slug = models.SlugField("код", unique=True)
    name = models.CharField("название", max_length=60)
    name_locative = models.CharField(
        "где? (в Майами)", max_length=80, help_text="Для заголовков: «Новости в Майами»"
    )
    description = models.CharField("описание для SEO", max_length=200, blank=True)
    order = models.PositiveSmallIntegerField("порядок", default=0)
    is_statewide = models.BooleanField(
        "весь штат", default=False, help_text="Новости этого региона показываются во всех фильтрах"
    )

    class Meta:
        ordering = ["order"]
        verbose_name = "регион"
        verbose_name_plural = "регионы"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("news:region", args=[self.slug])


class Topic(models.Model):
    slug = models.SlugField("код", unique=True)
    name = models.CharField("название", max_length=60)
    short_name = models.CharField("короткое название", max_length=30)
    description = models.CharField("описание для SEO", max_length=200, blank=True)
    priority = models.PositiveSmallIntegerField(
        "приоритет для аудитории", default=3, help_text="1 — самое важное (безопасность), 5 — наименее"
    )
    cover = models.CharField(
        "обложка (static)", max_length=120, blank=True,
        help_text="Путь внутри static/ без расширения, например covers/weather "
        "(нужны файлы .webp, -640.webp и .jpg)",
    )
    order = models.PositiveSmallIntegerField("порядок", default=0)

    class Meta:
        ordering = ["order"]
        verbose_name = "тема"
        verbose_name_plural = "темы"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("news:topic", args=[self.slug])


class Tag(models.Model):
    name = models.CharField("тег", max_length=60, unique=True)
    slug = models.SlugField(max_length=80, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "тег"
        verbose_name_plural = "теги"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_slug(self.name, max_length=70) or "tag"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("news:tag", args=[self.slug])


class Story(models.Model):
    """Сюжет: одна история, о которой написали одно или несколько СМИ."""

    class Status(models.TextChoices):
        NEW = "new", "новый"
        CLASSIFIED = "classified", "оценён"
        SKIPPED = "skipped", "пропущен"
        WRITTEN = "written", "заметка написана"
        MERGED = "merged", "присоединён к заметке"
        FAILED = "failed", "ошибка"

    title = models.CharField("заголовок (из источника)", max_length=400)
    status = models.CharField("статус", max_length=20, choices=Status.choices, default=Status.NEW)
    score = models.PositiveSmallIntegerField("важность 0–10", null=True, blank=True)
    region = models.ForeignKey(Region, verbose_name="регион", null=True, blank=True, on_delete=models.SET_NULL)
    topic = models.ForeignKey(Topic, verbose_name="тема", null=True, blank=True, on_delete=models.SET_NULL)
    is_urgent = models.BooleanField("срочно", default=False)
    is_sensitive = models.BooleanField("чувствительно", default=False)
    classification = models.JSONField("ответ классификатора", default=dict, blank=True)
    note = models.CharField("причина пропуска / ошибка", max_length=500, blank=True)
    created_at = models.DateTimeField("создан", default=timezone.now)
    updated_at = models.DateTimeField("обновлён", auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "сюжет"
        verbose_name_plural = "сюжеты"

    def __str__(self):
        return self.title[:100]


class ArticleQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Article.Status.PUBLISHED, published_at__lte=timezone.now())

    def for_region(self, region: Region):
        """Новости региона плюс общештатные — они касаются всех."""
        return self.filter(models.Q(region=region) | models.Q(region__is_statewide=True))


class Article(models.Model):
    """Наша заметка на русском."""

    class Status(models.TextChoices):
        REVIEW = "review", "на проверке"
        PUBLISHED = "published", "опубликовано"
        REJECTED = "rejected", "отклонено"
        DRAFT = "draft", "черновик"

    story = models.OneToOneField(
        Story, verbose_name="сюжет", null=True, blank=True, on_delete=models.SET_NULL, related_name="article"
    )
    title = models.CharField("заголовок", max_length=120)
    slug = models.SlugField("адрес (латиница)", max_length=110, unique=True)
    teaser = models.CharField("анонс (для Telegram и карточек)", max_length=300)
    body = models.TextField("текст", help_text="Абзацы разделяются пустой строкой")
    for_you = models.TextField(
        "что это значит для вас", blank=True,
        help_text="2–4 пункта, по одному на строку: что новость меняет для читателя. Пусто — блок не показывается",
    )
    guide = models.ForeignKey(
        "guides.Guide", verbose_name="гайд «Подробнее»", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="articles",
    )
    region = models.ForeignKey(Region, verbose_name="регион", null=True, blank=True, on_delete=models.SET_NULL)
    topic = models.ForeignKey(Topic, verbose_name="тема", null=True, blank=True, on_delete=models.SET_NULL)
    tags = models.ManyToManyField(Tag, verbose_name="теги", blank=True)
    cover_image = models.CharField(
        "обложка", max_length=100, blank=True,
        help_text="Выбирает ИИ по смыслу заметки. Пусто — обложка из набора рубрики по очереди",
    )

    status = models.CharField("статус", max_length=20, choices=Status.choices, default=Status.REVIEW, db_index=True)
    is_urgent = models.BooleanField("🚨 срочно", default=False)
    is_sensitive = models.BooleanField("чувствительно", default=False)
    score = models.PositiveSmallIntegerField("важность", null=True, blank=True)
    review_reason = models.CharField("почему на проверке", max_length=500, blank=True)
    verification = models.JSONField("результат проверки", default=dict, blank=True)

    created_at = models.DateTimeField("создано", default=timezone.now)
    updated_at = models.DateTimeField("изменено", auto_now=True)
    published_at = models.DateTimeField("опубликовано", null=True, blank=True, db_index=True)
    revised_at = models.DateTimeField(
        "текст обновлён", null=True, blank=True,
        help_text="Ставится сам, когда после публикации меняют текст или добавляют источники",
    )

    telegram_message_id = models.BigIntegerField("id сообщения в Telegram", null=True, blank=True)
    telegram_posted_at = models.DateTimeField("отправлено в Telegram", null=True, blank=True)

    objects = ArticleQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at", "-created_at"]
        verbose_name = "заметка"
        verbose_name_plural = "заметки"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("news:article", args=[self.slug])

    @property
    def paragraphs(self) -> list[str]:
        return [p.strip() for p in self.body.replace("\r\n", "\n").split("\n\n") if p.strip()]

    @property
    def for_you_points(self) -> list[str]:
        return [line.strip(" -•\t") for line in self.for_you.splitlines() if line.strip(" -•\t")]

    @property
    def word_count(self) -> int:
        return len(self.body.split())

    @property
    def cover_info(self):
        """Выбранная обложка или, если её нет, обложка из набора рубрики (см. news/covers.py)."""
        if self.cover_image and (chosen := all_covers().get(self.cover_image)):
            return chosen
        if self.is_urgent and self.topic and self.topic.slug in ("weather", "safety"):
            pool = "hurricane"
        else:
            pool = self.topic.slug if self.topic else "florida"
        return pick_cover(pool, self.pk)

    @property
    def cover(self) -> str:
        """Базовый путь обложки в static/ без расширения: есть .webp, -640.webp и .jpg."""
        return self.cover_info.base

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_article_slug(self.title, exclude_pk=self.pk)
        super().save(*args, **kwargs)


class ArticleSource(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="sources")
    source = models.ForeignKey(
        "sources.Source", verbose_name="источник", null=True, blank=True, on_delete=models.SET_NULL
    )
    name = models.CharField("название СМИ", max_length=120)
    url = models.URLField("ссылка", max_length=1000)
    title = models.CharField("заголовок оригинала", max_length=400, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "первоисточник"
        verbose_name_plural = "первоисточники"

    def __str__(self):
        return self.name


def unique_article_slug(title: str, exclude_pk=None) -> str:
    base = make_slug(title, max_length=90) or "novost"
    slug, n = base, 2
    qs = Article.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    while qs.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug

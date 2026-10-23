from django.conf import settings
from django.db import models
from django.utils import timezone


class Source(models.Model):
    """Источник новостей. Список хранится как данные и правится в админке."""

    class Kind(models.TextChoices):
        RSS = "rss", "RSS / Atom"
        NWS_ALERTS = "nws_alerts", "NWS alerts API (GeoJSON)"
        TELEGRAM = "telegram", "Telegram-канал (публичный)"

    class SourceType(models.TextChoices):
        MEDIA = "media", "СМИ"
        OFFICIAL = "official", "официальный"
        WEATHER = "weather", "погода"

    name = models.CharField("название", max_length=120)
    homepage = models.URLField("сайт", blank=True)
    url = models.URLField("адрес фида", max_length=1000, unique=True)
    kind = models.CharField("формат", max_length=20, choices=Kind.choices, default=Kind.RSS)
    source_type = models.CharField("тип", max_length=20, choices=SourceType.choices, default=SourceType.MEDIA)
    region = models.ForeignKey(
        "news.Region", verbose_name="регион", null=True, blank=True, on_delete=models.SET_NULL
    )
    trust_weight = models.PositiveSmallIntegerField(
        "вес доверия", default=5, help_text="1–10. Официальные источники — 9–10"
    )
    is_active = models.BooleanField("активен", default=True)
    is_verified = models.BooleanField(
        "фид проверен", default=False,
        help_text="Отмечается командой check_sources, когда адрес реально отдаёт RSS/Atom",
    )
    verified_at = models.DateTimeField("проверен", null=True, blank=True)
    notes = models.CharField("заметки", max_length=300, blank=True)

    # HTTP-кэширование
    etag = models.CharField(max_length=300, blank=True)
    last_modified = models.CharField(max_length=100, blank=True)

    # Здоровье источника
    last_fetched_at = models.DateTimeField("последний запрос", null=True, blank=True)
    last_success_at = models.DateTimeField("последний успех", null=True, blank=True)
    consecutive_failures = models.PositiveSmallIntegerField("ошибок подряд", default=0)
    is_broken = models.BooleanField(
        "сломан", default=False,
        help_text=f"Ставится автоматически после {settings.SOURCE_MAX_FAILURES} ошибок подряд. "
        "Снимите галочку, когда источник починится",
    )
    last_error = models.TextField("последняя ошибка", blank=True)

    class Meta:
        ordering = ["source_type", "name"]
        verbose_name = "источник"
        verbose_name_plural = "источники"

    def __str__(self):
        return self.name

    @property
    def is_official(self) -> bool:
        return self.source_type in (self.SourceType.OFFICIAL, self.SourceType.WEATHER)

    def record_success(self):
        now = timezone.now()
        self.last_fetched_at = now
        self.last_success_at = now
        self.consecutive_failures = 0
        self.last_error = ""
        self.save(update_fields=[
            "last_fetched_at", "last_success_at", "consecutive_failures", "last_error",
            "etag", "last_modified",
        ])

    def record_failure(self, error: str):
        self.last_fetched_at = timezone.now()
        self.consecutive_failures += 1
        self.last_error = error[:2000]
        if self.consecutive_failures >= settings.SOURCE_MAX_FAILURES:
            self.is_broken = True
        self.save(update_fields=["last_fetched_at", "consecutive_failures", "last_error", "is_broken"])


class FeedItem(models.Model):
    """Запись из фида: только заголовок, ссылка, дата и короткое описание.

    Полный текст статей мы не храним и не публикуем.
    """

    source = models.ForeignKey(Source, verbose_name="источник", on_delete=models.CASCADE, related_name="items")
    guid = models.CharField("guid", max_length=500)
    url = models.URLField("ссылка", max_length=1000)
    title = models.CharField("заголовок", max_length=400)
    summary = models.TextField("описание из фида", blank=True)
    published_at = models.DateTimeField("дата публикации", null=True, blank=True)
    fetched_at = models.DateTimeField("получено", default=timezone.now)
    story = models.ForeignKey(
        "news.Story", verbose_name="сюжет", null=True, blank=True, on_delete=models.SET_NULL, related_name="items"
    )

    class Meta:
        ordering = ["-fetched_at"]
        verbose_name = "запись фида"
        verbose_name_plural = "записи фидов"
        constraints = [models.UniqueConstraint(fields=["source", "guid"], name="uniq_feeditem_source_guid")]

    def __str__(self):
        return self.title[:100]


class WeatherAlert(models.Model):
    """Активные предупреждения NWS / NHC для блока «Погода и ураганы»."""

    class Severity(models.TextChoices):
        EXTREME = "Extreme", "чрезвычайное"
        SEVERE = "Severe", "сильное"
        MODERATE = "Moderate", "умеренное"
        MINOR = "Minor", "слабое"
        UNKNOWN = "Unknown", "неизвестно"

    source = models.ForeignKey(Source, null=True, blank=True, on_delete=models.SET_NULL)
    external_id = models.CharField(max_length=300, unique=True)
    event = models.CharField("событие (англ.)", max_length=120)
    event_ru = models.CharField("событие", max_length=160, blank=True)
    headline = models.CharField("заголовок", max_length=500, blank=True)
    area = models.TextField("районы", blank=True)
    severity = models.CharField("опасность", max_length=20, choices=Severity.choices, default=Severity.UNKNOWN)
    url = models.URLField("ссылка", max_length=1000, blank=True)
    effective = models.DateTimeField("начало", null=True, blank=True)
    expires = models.DateTimeField("окончание", null=True, blank=True)
    is_active = models.BooleanField("активно", default=True)
    is_hidden = models.BooleanField("скрыть на сайте", default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-effective"]
        verbose_name = "погодное предупреждение"
        verbose_name_plural = "погодные предупреждения"

    def __str__(self):
        return self.event_ru or self.event

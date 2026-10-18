"""Афиша: события, которые присылают организаторы. ИИ проверяет заявку и сам публикует или отклоняет."""

import uuid
from datetime import timedelta

from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.text import make_slug


class EventQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Event.Status.APPROVED)

    def upcoming(self):
        today = timezone.localdate()
        return (self.published()
                .filter(models.Q(ends_on__gte=today) | models.Q(ends_on=None, starts_on__gte=today))
                .order_by("starts_on", models.F("starts_at").asc(nulls_first=True), "title"))

    def since(self, hours: int = 24):
        return self.filter(created_at__gte=timezone.now() - timedelta(hours=hours))


class Event(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "на проверке"
        APPROVED = "approved", "опубликовано"
        REJECTED = "rejected", "отклонено"

    class ImageStatus(models.TextChoices):
        NONE = "", "нет картинки"
        PENDING = "pending", "ждёт проверки или загрузки"
        PUBLISHED = "published", "опубликована"
        REJECTED = "rejected", "отклонена"
        SKIPPED = "skipped", "не проверить: нет модели со зрением или ImageKit"

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    slug = models.SlugField("адрес", max_length=120, unique=True, blank=True)
    status = models.CharField("статус", max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)

    title = models.CharField("название", max_length=160)
    description = models.TextField("описание", max_length=2000)
    starts_on = models.DateField("дата начала", db_index=True)
    starts_at = models.TimeField("время начала", null=True, blank=True)
    ends_on = models.DateField("дата окончания", null=True, blank=True, help_text="Для фестивалей на несколько дней")
    venue = models.CharField("место", max_length=160)
    address = models.CharField("адрес", max_length=200)
    city = models.CharField("город", max_length=80)
    region = models.ForeignKey("news.Region", verbose_name="регион", null=True, blank=True, on_delete=models.SET_NULL)
    price = models.CharField("цена", max_length=80, blank=True)
    url = models.URLField("билеты или подробности", max_length=500, blank=True)
    organizer = models.CharField("организатор", max_length=160)

    image_data = models.BinaryField("картинка до проверки", null=True, blank=True, editable=False)
    image_status = models.CharField(
        "картинка", max_length=10, choices=ImageStatus.choices, default=ImageStatus.NONE, blank=True,
    )
    image_url = models.URLField("картинка (ImageKit)", max_length=500, blank=True)
    image_file_id = models.CharField("ImageKit fileId", max_length=80, blank=True)
    image_note = models.CharField("проверка картинки", max_length=500, blank=True)

    contact_name = models.CharField("контактное лицо", max_length=120)
    contact_email = models.EmailField("e-mail для связи")
    ip_hash = models.CharField("IP (хэш)", max_length=32, blank=True, db_index=True)

    violation = models.CharField("нарушение", max_length=30, blank=True)
    reason = models.TextField("решение ИИ: почему", blank=True)
    public_reason = models.TextField("ответ заявителю", blank=True)
    attempts = models.PositiveSmallIntegerField("попыток проверки", default=0)
    created_at = models.DateTimeField("получено", default=timezone.now, db_index=True)
    moderated_at = models.DateTimeField("проверено", null=True, blank=True)

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "событие"
        verbose_name_plural = "афиша: события"

    def __str__(self):
        return f"{self.title} · {self.starts_on:%d.%m.%Y} · {self.get_status_display()}"

    def get_absolute_url(self):
        return reverse("events:detail", args=[self.slug])

    @property
    def last_day(self):
        return self.ends_on or self.starts_on

    @property
    def is_past(self) -> bool:
        return self.last_day < timezone.localdate()

    @property
    def is_multiday(self) -> bool:
        return bool(self.ends_on and self.ends_on != self.starts_on)

    @property
    def is_free(self) -> bool:
        return self.price.strip().lower() in {"бесплатно", "free", "вход свободный", "0", "$0"}

    def make_unique_slug(self) -> str:
        base = make_slug(f"{self.title} {self.starts_on:%Y-%m-%d}", max_length=100) or f"event-{self.starts_on:%Y-%m-%d}"
        slug, n = base, 2
        while Event.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug, n = f"{base}-{n}", n + 1
        return slug

"""Частные объявления. Автор подаёт без регистрации, ИИ проверяет текст и фото и сам публикует или отклоняет.

Управление — по секретной ссылке с токеном: править, продлить на 30 дней, снять. Контакты автора
видны только по кнопке, чтобы их не собирали боты.
"""

import re
import uuid
from datetime import timedelta

from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.text import make_slug

LIFETIME = timedelta(days=30)
RENEW_WINDOW = timedelta(days=5)  # продлить можно за 5 дней до конца и после
RENEW_GRACE = timedelta(days=60)  # …но не позже, чем через 60 дней после окончания
MAX_PHOTOS = 5


class Category(models.Model):
    """Двухуровневый рубрикатор: раздел («Недвижимость») → рубрика («Сдам квартиру»).

    Объявление всегда лежит в рубрике; раздел показывает объявления всех своих рубрик.
    """

    parent = models.ForeignKey("self", verbose_name="раздел", null=True, blank=True, on_delete=models.CASCADE,
                               related_name="children")
    slug = models.SlugField("адрес (латиница)", max_length=60, unique=True)
    name = models.CharField("название", max_length=60)
    description = models.CharField("описание", max_length=300, blank=True, help_text="Подзаголовок и описание для SEO")
    price_label = models.CharField("подпись цены", max_length=20, default="Цена",
                                   help_text="«Цена», «Зарплата», «Аренда»")
    order = models.PositiveSmallIntegerField("порядок", default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "рубрика"
        verbose_name_plural = "рубрики"

    def __str__(self):
        return f"{self.parent.name} → {self.name}" if self.parent_id else self.name

    def get_absolute_url(self):
        return reverse("classifieds:category", args=[self.slug])

    @property
    def is_section(self) -> bool:
        return self.parent_id is None


class AdQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=Ad.Status.APPROVED, expires_at__gt=timezone.now())

    def newest(self):
        return self.order_by("-published_at", "-pk")

    def since(self, hours: int = 24):
        return self.filter(created_at__gte=timezone.now() - timedelta(hours=hours))


class Ad(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "на проверке"
        APPROVED = "approved", "опубликовано"
        REJECTED = "rejected", "отклонено"
        HIDDEN = "hidden", "скрыто по жалобам"
        CLOSED = "closed", "снято автором"

    class PriceUnit(models.TextChoices):
        TOTAL = "", "за всё"
        MONTH = "month", "в месяц"
        WEEK = "week", "в неделю"
        DAY = "day", "в сутки"
        HOUR = "hour", "в час"

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    slug = models.SlugField("адрес", max_length=90, blank=True)
    status = models.CharField("статус", max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    category = models.ForeignKey(Category, verbose_name="рубрика", on_delete=models.PROTECT, related_name="ads")

    title = models.CharField("заголовок", max_length=100)
    description = models.TextField("текст", max_length=3000)
    price = models.PositiveIntegerField("цена, $", null=True, blank=True)
    price_unit = models.CharField("за что цена", max_length=5, choices=PriceUnit.choices, default="", blank=True)

    city = models.CharField("город", max_length=80)
    zip_code = models.CharField("ZIP", max_length=5, blank=True, db_index=True)
    region = models.ForeignKey("news.Region", verbose_name="регион", null=True, blank=True, on_delete=models.SET_NULL)

    contact_name = models.CharField("имя", max_length=60)
    phone = models.CharField("телефон", max_length=16, blank=True, help_text="+13055551234")
    has_whatsapp = models.BooleanField("есть WhatsApp", default=False)
    telegram = models.CharField("Telegram", max_length=32, blank=True, help_text="Без @")
    ip_hash = models.CharField("IP (хэш)", max_length=32, blank=True, db_index=True)

    violation = models.CharField("нарушение", max_length=30, blank=True)
    reason = models.TextField("решение ИИ: почему", blank=True)
    public_reason = models.TextField("ответ автору", blank=True)
    attempts = models.PositiveSmallIntegerField("попыток проверки", default=0)
    views = models.PositiveIntegerField("просмотры", default=0)
    contact_views = models.PositiveIntegerField("показы контактов", default=0)
    search = models.TextField("для поиска", blank=True, editable=False,
                              help_text="Заголовок, текст и город в нижнем регистре: SQLite не умеет без учёта регистра в кириллице")

    created_at = models.DateTimeField("подано", default=timezone.now, db_index=True)
    moderated_at = models.DateTimeField("проверено", null=True, blank=True)
    published_at = models.DateTimeField("опубликовано или продлено", null=True, blank=True, db_index=True)
    expires_at = models.DateTimeField("активно до", null=True, blank=True, db_index=True)
    closed_at = models.DateTimeField("снято", null=True, blank=True)

    objects = AdQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "объявление"
        verbose_name_plural = "объявления"

    def __str__(self):
        return f"{self.title} · {self.city} · {self.get_status_display()}"

    def save(self, *args, **kwargs):
        self.slug = make_slug(self.title, max_length=80) or "obyavlenie"
        self.search = " ".join([self.title, self.description, self.city, self.zip_code]).lower().replace("ё", "е")
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {*kwargs["update_fields"], "slug", "search"}
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("classifieds:detail", args=[self.pk, self.slug or "obyavlenie"])

    def get_manage_url(self):
        return reverse("classifieds:manage", args=[self.token])

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.APPROVED and bool(self.expires_at) and self.expires_at > timezone.now()

    @property
    def is_expired(self) -> bool:
        return self.status == self.Status.APPROVED and bool(self.expires_at) and self.expires_at <= timezone.now()

    @property
    def is_public(self) -> bool:
        """Страница открывается: живое, истёкшее или снятое автором (без контактов)."""
        return self.status in (self.Status.APPROVED, self.Status.CLOSED)

    @property
    def can_renew(self) -> bool:
        if self.status != self.Status.APPROVED or not self.expires_at:
            return False
        now = timezone.now()
        return self.expires_at - RENEW_WINDOW <= now <= self.expires_at + RENEW_GRACE

    def renew(self) -> None:
        now = timezone.now()
        self.published_at = now
        self.expires_at = now + LIFETIME

    @property
    def price_text(self) -> str:
        if self.price is None:
            return "Договорная"
        if self.price == 0:
            return "Бесплатно"
        amount = f"${self.price:,}".replace(",", " ")
        return f"{amount} {self.get_price_unit_display()}" if self.price_unit else amount

    @property
    def place(self) -> str:
        return f"{self.city}, FL {self.zip_code}" if self.zip_code else self.city

    @property
    def map_query(self) -> str:
        return f"{self.zip_code} FL" if self.zip_code else f"{self.city}, FL"

    @property
    def phone_digits(self) -> str:
        return re.sub(r"\D", "", self.phone)

    @property
    def phone_display(self) -> str:
        digits = self.phone_digits
        if len(digits) == 11 and digits.startswith("1"):
            return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        return self.phone

    @property
    def whatsapp_url(self) -> str:
        return f"https://wa.me/{self.phone_digits}" if self.phone and self.has_whatsapp else ""

    @property
    def telegram_url(self) -> str:
        return f"https://t.me/{self.telegram}" if self.telegram else ""

    def public_photos(self):
        return [p for p in self.photos.all() if p.status == Photo.Status.PUBLISHED and p.url]

    @property
    def cover(self):
        return next(iter(self.public_photos()), None)


class Photo(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "ждёт проверки или загрузки"
        PUBLISHED = "published", "опубликовано"
        REJECTED = "rejected", "отклонено"
        SKIPPED = "skipped", "не проверить: нет модели со зрением или ImageKit"

    ad = models.ForeignKey(Ad, verbose_name="объявление", on_delete=models.CASCADE, related_name="photos")
    order = models.PositiveSmallIntegerField("порядок", default=0)
    status = models.CharField("статус", max_length=10, choices=Status.choices, default=Status.PENDING)
    data = models.BinaryField("фото до проверки", null=True, blank=True, editable=False)
    url = models.URLField("фото (ImageKit)", max_length=500, blank=True)
    file_id = models.CharField("ImageKit fileId", max_length=80, blank=True)
    note = models.CharField("проверка", max_length=500, blank=True)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "фото"
        verbose_name_plural = "фото"

    def __str__(self):
        return f"Фото {self.order + 1} · {self.get_status_display()}"


class Report(models.Model):
    """Жалоба посетителя. После нескольких жалоб с разных адресов объявление скрывается до решения редакции."""

    class Reason(models.TextChoices):
        SCAM = "scam", "Похоже на мошенничество"
        PROHIBITED = "prohibited", "Запрещённый товар или услуга"
        WRONG = "wrong", "Не та рубрика или неверные данные"
        SOLD = "sold", "Уже продано, неактуально"
        OFFENSIVE = "offensive", "Оскорбительное содержание"
        OTHER = "other", "Другое"

    ad = models.ForeignKey(Ad, verbose_name="объявление", on_delete=models.CASCADE, related_name="reports")
    reason = models.CharField("причина", max_length=12, choices=Reason.choices)
    comment = models.CharField("комментарий", max_length=500, blank=True)
    ip_hash = models.CharField("IP (хэш)", max_length=32)
    created_at = models.DateTimeField("получено", default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "жалоба"
        verbose_name_plural = "жалобы"
        constraints = [models.UniqueConstraint(fields=["ad", "ip_hash"], name="one_report_per_ip")]

    def __str__(self):
        return f"{self.get_reason_display()} · {self.ad_id}"

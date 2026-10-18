"""Справочник: полезные официальные ссылки и рекомендации бизнесов по категориям."""

import uuid
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from django.db import models
from django.utils import timezone
from django.urls import reverse


@lru_cache(maxsize=256)
def category_icon(slug: str) -> str:
    path = f"directory/{slug}.webp"
    return path if (Path(settings.BASE_DIR) / "static" / path).exists() else ""


class CategoryQuerySet(models.QuerySet):
    def with_listings(self):
        return self.prefetch_related(models.Prefetch("listings", queryset=Listing.objects.active()))


class Category(models.Model):
    class Kind(models.TextChoices):
        LINKS = "links", "Полезные ссылки"
        BUSINESS = "business", "Бизнесы"

    kind = models.CharField("вид", max_length=10, choices=Kind.choices, default=Kind.BUSINESS, db_index=True)
    slug = models.SlugField("адрес (латиница)", max_length=80, unique=True)
    name = models.CharField("название", max_length=80)
    description = models.CharField("описание", max_length=300, blank=True, help_text="Подзаголовок и описание для SEO")
    schema_type = models.CharField(
        "тип Schema.org", max_length=60, blank=True, default="LocalBusiness",
        help_text="Для разметки бизнесов: Church, MedicalClinic, Dentist, LegalService, AccountingService, "
        "RealEstateAgent, InsuranceAgency, AutoRepair, Store, Restaurant, BeautySalon …",
    )
    order = models.PositiveSmallIntegerField("порядок", default=0)

    objects = CategoryQuerySet.as_manager()

    class Meta:
        ordering = ["kind", "order", "name"]
        verbose_name = "категория"
        verbose_name_plural = "категории"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("directory:category", args=[self.slug])

    @property
    def icon(self) -> str:
        """Путь иконки в static/ (directory/<slug>.webp) или пусто, если иконки нет."""
        return category_icon(self.slug)


class ListingQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True).order_by(
            "-is_partner", "-is_recommended", "order", models.F("region__order").asc(nulls_last=True), "city", "name",
        )


class Listing(models.Model):
    category = models.ForeignKey(Category, verbose_name="категория", on_delete=models.CASCADE, related_name="listings")
    name = models.CharField("название", max_length=160)
    description = models.TextField("описание", blank=True, help_text="2–4 предложения: чем полезен, для кого")
    url = models.URLField("сайт", max_length=500, blank=True)
    phone = models.CharField("телефон", max_length=40, blank=True)
    address = models.CharField("адрес", max_length=200, blank=True)
    city = models.CharField("город", max_length=80, blank=True)
    region = models.ForeignKey(
        "news.Region", verbose_name="регион", null=True, blank=True, on_delete=models.SET_NULL,
    )
    languages = models.CharField("языки", max_length=120, blank=True, help_text="Например: русский, украинский, английский")
    hours = models.CharField("часы работы / расписание", max_length=200, blank=True)
    guide_slug = models.SlugField(
        "гайд по теме (slug)", max_length=120, blank=True,
        help_text="Адрес гайда из /guides/<slug>/ — под записью появится ссылка «Подробнее в гайде»",
    )
    is_recommended = models.BooleanField("рекомендуем", default=False, help_text="Метка «Рекомендуем» от редакции")
    is_partner = models.BooleanField(
        "партнёр (платно)", default=False, help_text="Платное размещение — показывается с меткой «Партнёр» и выше",
    )
    is_active = models.BooleanField("показывать", default=True)
    from_owner = models.BooleanField(
        "от владельца", default=False,
        help_text="Добавлено представителем бизнеса через форму — читатели видят метку «Данные от владельца»",
    )
    editor_note = models.TextField(
        "заметка редакции", blank=True, help_text="Видна только в админке: откуда данные, что перепроверить",
    )
    order = models.PositiveSmallIntegerField("порядок", default=0)
    created_at = models.DateTimeField("добавлено", auto_now_add=True)
    updated_at = models.DateTimeField("изменено", auto_now=True)

    objects = ListingQuerySet.as_manager()

    class Meta:
        ordering = ["category", "order", "name"]
        verbose_name = "запись справочника"
        verbose_name_plural = "записи справочника"

    def __str__(self):
        return self.name

    @property
    def phone_href(self) -> str:
        digits = "".join(ch for ch in self.phone if ch.isdigit() or ch == "+")
        return f"tel:{digits}" if digits else ""

    @property
    def domain(self) -> str:
        return self.url.split("://", 1)[-1].split("/", 1)[0].removeprefix("www.") if self.url else ""


class SubmissionQuerySet(models.QuerySet):
    def since(self, hours: int = 24):
        return self.filter(created_at__gte=timezone.now() - timedelta(hours=hours))


class Submission(models.Model):
    """Заявка бизнеса через форму на сайте. ИИ проверяет её и сам публикует или отклоняет."""

    class Status(models.TextChoices):
        PENDING = "pending", "на проверке"
        APPROVED = "approved", "опубликовано"
        REJECTED = "rejected", "отклонено"

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField("статус", max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    category = models.ForeignKey(
        Category, verbose_name="категория (выбрал заявитель)", null=True, on_delete=models.SET_NULL,
        limit_choices_to={"kind": Category.Kind.BUSINESS},
    )
    name = models.CharField("название", max_length=160)
    description = models.TextField("описание от заявителя", max_length=1500)
    url = models.URLField("сайт или страница", max_length=500, blank=True)
    phone = models.CharField("телефон", max_length=40, blank=True)
    address = models.CharField("адрес", max_length=200, blank=True)
    city = models.CharField("город", max_length=80)
    languages = models.CharField("языки", max_length=120, blank=True)
    hours = models.CharField("часы работы", max_length=200, blank=True)
    contact_name = models.CharField("контактное лицо", max_length=120)
    contact_email = models.EmailField("e-mail для связи")
    ip_hash = models.CharField("IP (хэш)", max_length=32, blank=True, db_index=True)

    violation = models.CharField("нарушение", max_length=30, blank=True)
    reason = models.TextField("решение ИИ: почему", blank=True)
    public_reason = models.TextField("ответ заявителю", blank=True)
    listing = models.OneToOneField(
        Listing, verbose_name="запись в справочнике", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="submission",
    )
    attempts = models.PositiveSmallIntegerField("попыток проверки", default=0)
    created_at = models.DateTimeField("получено", default=timezone.now, db_index=True)
    moderated_at = models.DateTimeField("проверено", null=True, blank=True)

    objects = SubmissionQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "заявка бизнеса"
        verbose_name_plural = "заявки бизнесов"

    def __str__(self):
        return f"{self.name} · {self.get_status_display()}"

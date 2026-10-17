"""Справочник: полезные официальные ссылки и рекомендации бизнесов по категориям."""

from django.db import models
from django.urls import reverse


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


class ListingQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True).order_by("-is_partner", "-is_recommended", "order", "name")


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

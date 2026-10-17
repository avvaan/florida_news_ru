from django.db import models
from django.db.models import Q
from django.utils import timezone


class AdBannerQuerySet(models.QuerySet):
    def running(self, slot: str, region=None):
        now = timezone.now()
        qs = self.filter(slot=slot, is_active=True).filter(
            Q(starts_at__isnull=True) | Q(starts_at__lte=now),
            Q(ends_at__isnull=True) | Q(ends_at__gte=now),
        )
        if region is not None:
            qs = qs.filter(Q(region__isnull=True) | Q(region=region))
        return qs.order_by("-priority", "?")


class AdBanner(models.Model):
    """Прямая реклама местного бизнеса."""

    class Slot(models.TextChoices):
        TOP = "top", "Под шапкой (широкий)"
        SIDEBAR = "sidebar", "Боковая колонка"
        INFEED = "infeed", "В ленте / под заметкой"

    advertiser = models.CharField("рекламодатель", max_length=120)
    slot = models.CharField("место", max_length=20, choices=Slot.choices)
    image = models.ImageField("картинка", upload_to="ads/", blank=True)
    headline = models.CharField(
        "текст", max_length=140, blank=True, help_text="Показывается, если нет картинки, и как alt"
    )
    url = models.URLField("ссылка")
    region = models.ForeignKey(
        "news.Region", verbose_name="город", null=True, blank=True, on_delete=models.SET_NULL,
        help_text="Пусто — показывать везде",
    )
    starts_at = models.DateTimeField("показывать с", null=True, blank=True)
    ends_at = models.DateTimeField("показывать до", null=True, blank=True)
    is_active = models.BooleanField("включено", default=True)
    priority = models.PositiveSmallIntegerField("приоритет", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AdBannerQuerySet.as_manager()

    class Meta:
        ordering = ["-is_active", "-priority", "-created_at"]
        verbose_name = "рекламный блок"
        verbose_name_plural = "рекламные блоки"

    def __str__(self):
        return f"{self.advertiser} — {self.get_slot_display()}"

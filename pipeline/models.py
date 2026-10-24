from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.utils import timezone


class AICallQuerySet(models.QuerySet):
    def today(self):
        start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.filter(created_at__gte=start)

    def this_month(self):
        start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return self.filter(created_at__gte=start)

    def total_cost(self) -> Decimal:
        return self.aggregate(total=Sum("cost_usd"))["total"] or Decimal("0")


class AICall(models.Model):
    """Лог каждого обращения к ИИ: токены и стоимость."""

    class Purpose(models.TextChoices):
        CLASSIFY = "classify", "отбор"
        WRITE = "write", "написание"
        VERIFY = "verify", "проверка"
        COVER = "cover", "обложка"
        SIGNALS = "signals", "сбор сигналов"
        TRIAGE = "triage", "разбор сигналов"
        GUIDE = "guide", "гайды"
        MODERATE = "moderate", "проверка заявок бизнесов"
        MODERATE_EVENT = "moderate_event", "проверка афиш"
        MODERATE_AD = "moderate_ad", "проверка объявлений"
        DEDUP = "dedup", "проверка дублей"

    created_at = models.DateTimeField("время", default=timezone.now, db_index=True)
    purpose = models.CharField("задача", max_length=20, choices=Purpose.choices)
    model = models.CharField("модель", max_length=60)
    input_tokens = models.PositiveIntegerField("вход", default=0)
    output_tokens = models.PositiveIntegerField("выход", default=0)
    cache_read_tokens = models.PositiveIntegerField("из кэша", default=0)
    cache_write_tokens = models.PositiveIntegerField("в кэш", default=0)
    cost_usd = models.DecimalField("стоимость, $", max_digits=10, decimal_places=6, default=Decimal("0"))
    success = models.BooleanField("успех", default=True)
    error = models.TextField("ошибка", blank=True)
    request_id = models.CharField("request id", max_length=100, blank=True)
    story = models.ForeignKey("news.Story", null=True, blank=True, on_delete=models.SET_NULL)

    objects = AICallQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "вызов ИИ"
        verbose_name_plural = "расходы на ИИ"

    def __str__(self):
        return f"{self.get_purpose_display()} · {self.model} · ${self.cost_usd:.4f}"


class PipelineRun(models.Model):
    started_at = models.DateTimeField("начало", default=timezone.now)
    finished_at = models.DateTimeField("конец", null=True, blank=True)
    stats = models.JSONField("итоги", default=dict, blank=True)
    log = models.TextField("журнал", blank=True)
    success = models.BooleanField("без сбоев", default=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "запуск конвейера"
        verbose_name_plural = "запуски конвейера"

    def __str__(self):
        return timezone.localtime(self.started_at).strftime("%d.%m %H:%M")

"""Сигналы из соцсетей — подсказки, о чём говорят. Не источник фактов и не источник публикаций."""

from django.db import models
from django.utils import timezone


class SignalSource(models.Model):
    """Откуда берём сигналы: поисковый запрос к Perplexity или Grok либо публичный Telegram-канал."""

    class Kind(models.TextChoices):
        PERPLEXITY = "perplexity", "Perplexity (поиск по сети)"
        GROK = "grok", "Grok (поиск по X)"
        TELEGRAM = "telegram", "Telegram-канал"

    name = models.CharField("название", max_length=120)
    kind = models.CharField("вид", max_length=20, choices=Kind.choices)
    query = models.CharField(
        "запрос или канал", max_length=500,
        help_text="Для Perplexity и Grok — текст запроса. Для Telegram — @username публичного канала "
        "(чаты, группы и личные сообщения не читаются)",
    )
    region = models.ForeignKey("news.Region", verbose_name="регион", null=True, blank=True,
                               on_delete=models.SET_NULL)
    is_active = models.BooleanField("активен", default=True)
    notes = models.CharField("заметки", max_length=300, blank=True)

    last_fetched_at = models.DateTimeField("последний запрос", null=True, blank=True)
    last_success_at = models.DateTimeField("последний успех", null=True, blank=True)
    consecutive_failures = models.PositiveSmallIntegerField("ошибок подряд", default=0)
    last_error = models.TextField("последняя ошибка", blank=True)
    last_message_id = models.PositiveBigIntegerField(
        "последнее прочитанное сообщение", default=0, help_text="Только для Telegram")

    class Meta:
        ordering = ["kind", "name"]
        verbose_name = "источник сигналов"
        verbose_name_plural = "источники сигналов"

    def __str__(self):
        return f"{self.get_kind_display()}: {self.name}"

    def record_success(self):
        now = timezone.now()
        self.last_fetched_at = self.last_success_at = now
        self.consecutive_failures = 0
        self.last_error = ""
        self.save(update_fields=["last_fetched_at", "last_success_at", "consecutive_failures", "last_error",
                                 "last_message_id"])

    def record_failure(self, error: str):
        self.last_fetched_at = timezone.now()
        self.consecutive_failures += 1
        self.last_error = error[:2000]
        self.save(update_fields=["last_fetched_at", "consecutive_failures", "last_error"])


class Hint(models.Model):
    """«Подсказка»: интересная тема из соцсетей, которой ещё нет среди сюжетов.

    Заметка по ней появится, только когда тот же сюжет придёт от СМИ или официального источника.
    """

    class Status(models.TextChoices):
        OPEN = "open", "ждёт подтверждения"
        CONFIRMED = "confirmed", "подтверждена"
        EXPIRED = "expired", "устарела"
        DISMISSED = "dismissed", "отклонена"

    title = models.CharField("тема", max_length=200)
    summary = models.TextField("пересказ редакции", blank=True,
                               help_text="Своими словами, без цитат. Не факт — только что обсуждают")
    region = models.ForeignKey("news.Region", verbose_name="регион", null=True, blank=True,
                               on_delete=models.SET_NULL)
    topic = models.ForeignKey("news.Topic", verbose_name="тема сайта", null=True, blank=True,
                              on_delete=models.SET_NULL)
    status = models.CharField("статус", max_length=20, choices=Status.choices, default=Status.OPEN)
    story = models.ForeignKey("news.Story", verbose_name="подтверждающий сюжет", null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="hints")
    created_at = models.DateTimeField("создана", default=timezone.now)
    confirmed_at = models.DateTimeField("подтверждена", null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "подсказка"
        verbose_name_plural = "💡 Подсказки"

    def __str__(self):
        return self.title


class Signal(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "новый"
        NOISE = "noise", "неинтересно"
        STORY = "story", "совпал с сюжетом"
        HINT = "hint", "в подсказке"

    source = models.ForeignKey(SignalSource, verbose_name="источник", on_delete=models.CASCADE,
                               related_name="signals")
    url = models.URLField("ссылка", max_length=1000, unique=True)
    author = models.CharField("автор", max_length=200, blank=True)
    text = models.TextField("текст", help_text="Коротко, для сопоставления. На сайт не выводится")
    published_at = models.DateTimeField("время", null=True, blank=True)
    fetched_at = models.DateTimeField("получен", default=timezone.now, db_index=True)
    region = models.ForeignKey("news.Region", verbose_name="регион", null=True, blank=True,
                               on_delete=models.SET_NULL)
    topic = models.ForeignKey("news.Topic", verbose_name="тема", null=True, blank=True,
                              on_delete=models.SET_NULL)
    status = models.CharField("статус", max_length=20, choices=Status.choices, default=Status.NEW)
    story = models.ForeignKey("news.Story", verbose_name="сюжет", null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="signals")
    hint = models.ForeignKey(Hint, verbose_name="подсказка", null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="signals")

    class Meta:
        ordering = ["-fetched_at"]
        verbose_name = "сигнал"
        verbose_name_plural = "сигналы"

    def __str__(self):
        return self.text[:80]

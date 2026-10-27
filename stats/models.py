"""Посещаемость без cookie и без IP.

С 27.10.2026 каждый просмотр — строка Hit, присланная скриптом из браузера; боты не выбрасываются, а
помечаются (is_bot, bot_reason). До этого сервер копил только дневные суммы (DailyStat, PageView, Source)
и многих ботов не отличал — эти таблицы остаются как «старый счётчик» и больше не пополняются.

Уникальных посетителей за день считаем по обезличенному коду: HMAC(секрет + дата, случайный код из
localStorage). Код меняется каждые сутки, связать посетителя между днями нельзя.
"""

from django.db import models
from django.utils import timezone


class DailyStat(models.Model):
    """Старый серверный счётчик: дневные суммы до перехода на сигнал из браузера."""

    date = models.DateField("день", unique=True)
    views = models.PositiveIntegerField("просмотры", default=0)
    visitors = models.PositiveIntegerField("посетители", default=0)
    mobile = models.PositiveIntegerField("телефоны", default=0, help_text="посетители с телефона")
    tablet = models.PositiveIntegerField("планшеты", default=0)
    desktop = models.PositiveIntegerField("компьютеры", default=0)

    class Meta:
        ordering = ["-date"]
        verbose_name = "посещаемость за день"
        verbose_name_plural = "посещаемость"

    def __str__(self):
        return f"{self.date}: {self.visitors} посетителей, {self.views} просмотров"


class PageView(models.Model):
    date = models.DateField("день", db_index=True)
    path = models.CharField("страница", max_length=300)
    views = models.PositiveIntegerField("просмотры", default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["date", "path"], name="stats_pageview_day_path")]
        verbose_name = "просмотры страницы"
        verbose_name_plural = "просмотры страниц"


class Source(models.Model):
    """Откуда пришли: домен внешнего сайта или «прямой заход». Считаем только входы на сайт."""

    DIRECT = "прямой заход"

    date = models.DateField("день", db_index=True)
    source = models.CharField("источник", max_length=120)
    visits = models.PositiveIntegerField("входы", default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["date", "source"], name="stats_source_day_source")]
        verbose_name = "источник"
        verbose_name_plural = "источники"


class VisitorKey(models.Model):
    """Обезличенный дневной код посетителя — только чтобы не считать одного человека дважды за день."""

    date = models.DateField(db_index=True)
    key = models.CharField(max_length=32)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["date", "key"], name="stats_visitorkey_day_key")]


class Hit(models.Model):
    """Один просмотр по сигналу из браузера. IP не храним, адрес источника — только домен."""

    created_at = models.DateTimeField("время", default=timezone.now)
    date = models.DateField("день")
    path = models.CharField("страница", max_length=300)
    visitor = models.CharField("посетитель за день", max_length=32,
                               help_text="Обезличенный код, меняется каждые сутки")
    source = models.CharField("источник входа", max_length=120, blank=True,
                              help_text="Пусто — переход внутри сайта")
    referrer = models.CharField("откуда пришли", max_length=200, blank=True, help_text="Только схема и домен")
    utm_source = models.CharField("utm_source", max_length=60, blank=True)
    utm_medium = models.CharField("utm_medium", max_length=60, blank=True)
    utm_campaign = models.CharField("utm_campaign", max_length=100, blank=True)
    device = models.CharField("устройство", max_length=10)
    screen_width = models.PositiveSmallIntegerField("ширина экрана", null=True, blank=True)
    agent = models.CharField("User-Agent", max_length=300, blank=True)
    automation = models.BooleanField("автоматизация", default=False, help_text="navigator.webdriver")
    is_bot = models.BooleanField("бот", default=False)
    bot_reason = models.CharField("почему бот", max_length=60, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["date", "is_bot"], name="stats_hit_date_bot")]
        verbose_name = "просмотр"
        verbose_name_plural = "просмотры (сырые)"

    def __str__(self):
        return f"{self.created_at:%d.%m %H:%M} {self.path}{' [бот]' if self.is_bot else ''}"

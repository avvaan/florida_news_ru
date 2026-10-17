"""Посещаемость: только дневные агрегаты, без cookie и без IP.

Уникальных посетителей за день считаем по обезличенному коду: HMAC(секрет + дата, IP + браузер).
Код меняется каждые сутки, связать посетителя между днями нельзя; коды старше двух дней удаляются.
"""

from django.db import models


class DailyStat(models.Model):
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

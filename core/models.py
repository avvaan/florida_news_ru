from decimal import Decimal

from django.db import models
from django.urls import reverse


class SiteSettings(models.Model):
    """Единственная запись с порогами, лимитами и переключателями."""

    min_score_to_write = models.PositiveSmallIntegerField(
        "порог важности для заметки", default=6,
        help_text="Сюжеты с оценкой ниже не идут в работу (0–10)",
    )
    publish_without_review = models.BooleanField(
        "публиковать всё без проверки", default=True,
        help_text="Все написанные заметки сразу идут на сайт и в Telegram, очередь «На проверку» не используется. "
        "Причина, по которой заметка попала бы в очередь, сохраняется в её карточке",
    )
    auto_publish_enabled = models.BooleanField(
        "автопубликация включена", default=True,
        help_text="Если выключить, всё идёт в очередь «На проверку»",
    )
    auto_publish_min_score = models.PositiveSmallIntegerField(
        "порог автопубликации", default=7,
        help_text="Обычные заметки с оценкой не ниже и чистой проверкой публикуются сами",
    )
    min_verifier_confidence = models.DecimalField(
        "мин. уверенность проверки", max_digits=3, decimal_places=2, default=Decimal("0.80"),
    )
    max_articles_per_day = models.PositiveSmallIntegerField(
        "максимум заметок в день", default=40,
        help_text="При превышении пишем только срочное",
    )
    ai_budget_per_day_usd = models.DecimalField(
        "бюджет на ИИ в день, $", max_digits=7, decimal_places=2, default=Decimal("3.00"),
        help_text="При превышении пишем только срочное",
    )
    max_items_per_source = models.PositiveSmallIntegerField(
        "макс. новостей с одного фида за проход", default=30,
    )
    cluster_window_hours = models.PositiveSmallIntegerField(
        "окно склейки сюжетов, часов", default=48,
    )
    cluster_similarity = models.DecimalField(
        "порог похожести заголовков", max_digits=3, decimal_places=2, default=Decimal("0.45"),
        help_text="Коэффициент Жаккара по словам заголовка: 0.45 — разумно, выше — строже",
    )

    telegram_enabled = models.BooleanField(
        "отправлять в Telegram", default=False,
        help_text="Пока выключено — посты только пишутся в лог (dry-run)",
    )
    telegram_channel_url = models.URLField(
        "ссылка на канал", blank=True, help_text="Для кнопки «Подписаться» на сайте"
    )

    adsense_enabled = models.BooleanField("Google AdSense", default=False)
    adsense_client = models.CharField("AdSense client id", max_length=60, blank=True)

    contact_email = models.EmailField("e-mail редакции", blank=True)

    # Уполномоченный агент по DMCA (17 U.S.C. §512(c)) — точно как в записи в Copyright Office.
    dmca_agent_name = models.CharField("агент DMCA: имя", max_length=120, blank=True, default="Andrii Syrkin")
    dmca_agent_address = models.TextField("агент DMCA: почтовый адрес", blank=True,
                                          help_text="Точно как в записи агента в Copyright Office")
    dmca_agent_phone = models.CharField("агент DMCA: телефон", max_length=40, blank=True)
    dmca_agent_email = models.EmailField("агент DMCA: e-mail", blank=True)

    class Meta:
        verbose_name = "настройки"
        verbose_name_plural = "настройки"

    def __str__(self):
        return "Настройки сайта и конвейера"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "SiteSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Page(models.Model):
    """Статические страницы: «О проекте», «Реклама», «Контакты» и т.п."""

    slug = models.SlugField("адрес", unique=True)
    title = models.CharField("заголовок", max_length=120)
    body = models.TextField("текст", help_text="Абзацы через пустую строку. Можно простой HTML.")
    in_footer = models.BooleanField("в подвале", default=True)
    order = models.PositiveSmallIntegerField("порядок", default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order"]
        verbose_name = "страница"
        verbose_name_plural = "страницы"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("core-page", args=[self.slug])

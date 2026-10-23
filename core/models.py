from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse


class SiteSettings(models.Model):
    """Единственная запись с порогами, лимитами и переключателями."""

    min_score_to_write = models.PositiveSmallIntegerField(
        "порог важности для заметки", default=4,
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
        "публикаций в день", default=8,
        help_text="Пишем и публикуем самые важные; остальное отклоняется. Утренний проход берёт не больше "
        "половины, вечерний — остаток. Срочное (ураган, эвакуация) публикуется сверх лимита",
    )
    max_business_per_day = models.PositiveSmallIntegerField(
        "бизнес-заметок в день", default=4,
        help_text="Свой лимит раздела «Бизнес: акции и сделки», не входит в «публикаций в день». "
        "Утром — не больше половины, вечером — остаток",
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

    signals_perplexity_enabled = models.BooleanField(
        "сигналы: Perplexity", default=False, help_text="Поиск по сети. Нужен PERPLEXITY_API_KEY")
    signals_grok_enabled = models.BooleanField(
        "сигналы: Grok (X)", default=False, help_text="Поиск по X. Нужен XAI_API_KEY")
    signals_telegram_enabled = models.BooleanField(
        "сигналы: Telegram", default=False,
        help_text="Публичные каналы из «Источников сигналов». Нужны TG_API_ID, TG_API_HASH, TG_SESSION")
    signals_max_per_source = models.PositiveSmallIntegerField(
        "сигналов с источника за раз", default=15, validators=[MinValueValidator(1), MaxValueValidator(50)])

    # Уполномоченный агент по DMCA (17 U.S.C. §512(c)) — точно как в записи в Copyright Office.
    dmca_agent_name = models.CharField("агент DMCA: имя", max_length=120, blank=True, default="John Suvorov")
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
        if self.slug == "about":
            return reverse("core-about")
        return reverse("core-page", args=[self.slug])


class Author(models.Model):
    """Автор или редактор. Заполняется в админке; на сайте видны только включённые."""

    name = models.CharField("имя", max_length=120)
    slug = models.SlugField("адрес (латиница)", unique=True)
    role = models.CharField("должность", max_length=120, blank=True)
    bio = models.TextField("коротко о себе", blank=True)
    photo = models.ImageField("фото", upload_to="authors/", blank=True)
    is_active = models.BooleanField("показывать на сайте", default=False)
    order = models.PositiveSmallIntegerField("порядок", default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "автор / редактор"
        verbose_name_plural = "авторы и редакторы"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("core-author", args=[self.slug])

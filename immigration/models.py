"""Иммиграционный помощник: база знаний из официальных источников, читатели и их вопросы.

Помощник — навигатор и справочник, а не юридическая консультация: объясняет общие процессы и всегда даёт
официальный источник. Вопросы о личной ситуации не разбирает (см. immigration/assistant.py).
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Source(models.Model):
    """Страница официального источника или наш материал, разобранный на фрагменты."""

    class Agency(models.TextChoices):
        USCIS = "uscis", "USCIS"
        STATE = "state", "Госдеп (travel.state.gov)"
        EOIR = "eoir", "EOIR (иммиграционные суды)"
        FEDERAL_REGISTER = "fr", "Federal Register"
        TUTFLORIDA = "tutflorida", "TutFlorida"

    class Kind(models.TextChoices):
        PAGE = "page", "страница"
        FORM = "form", "страница формы"
        POLICY = "policy", "Policy Manual"
        FEES = "fees", "пошлины"
        NEWS = "news", "новость ведомства"
        VISA_BULLETIN = "visa_bulletin", "Visa Bulletin"
        FR_DOCUMENT = "fr_doc", "документ Federal Register"
        GUIDE = "guide", "наш гайд"
        ARTICLE = "article", "наша заметка"

    class Status(models.TextChoices):
        OK = "ok", "скачано"
        BLOCKED = "blocked", "сайт не пустил (403)"
        NOT_FOUND = "not_found", "страницы нет (404)"
        JS_ONLY = "js_only", "собирается JavaScript"
        FAILED = "failed", "ошибка"

    url = models.URLField("адрес", max_length=700, unique=True)
    title = models.CharField("заголовок", max_length=400, blank=True)
    agency = models.CharField("ведомство", max_length=12, choices=Agency.choices, db_index=True)
    kind = models.CharField("вид", max_length=16, choices=Kind.choices, default=Kind.PAGE)
    language = models.CharField("язык", max_length=2, default="en")
    status = models.CharField("состояние", max_length=10, choices=Status.choices, default=Status.OK, db_index=True)
    last_error = models.CharField("последняя ошибка", max_length=500, blank=True)
    content_hash = models.CharField("хэш текста", max_length=64, blank=True)
    published_on = models.DateField("дата публикации", null=True, blank=True)
    fetched_at = models.DateTimeField("скачано", null=True, blank=True)
    checked_at = models.DateTimeField("проверено", null=True, blank=True, db_index=True,
                                      help_text="Последний раз, когда страница открылась и текст сверен")
    changed_at = models.DateTimeField("текст изменился", null=True, blank=True)
    is_active = models.BooleanField("в базе", default=True, help_text="Выключенный источник в ответы не попадает")

    class Meta:
        ordering = ["agency", "title"]
        verbose_name = "источник"
        verbose_name_plural = "источники базы знаний"

    def __str__(self):
        return self.title or self.url

    @property
    def is_stale(self) -> bool:
        return not self.checked_at or self.checked_at < timezone.now() - timedelta(days=STALE_DAYS)


STALE_DAYS = 14  # источник, который не открывался дольше, подсвечивается в админке


class Chunk(models.Model):
    """Фрагмент текста источника: раздел страницы, до ~350 слов."""

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="chunks")
    section = models.CharField("раздел", max_length=300, blank=True)
    text = models.TextField("текст")
    position = models.PositiveIntegerField("порядок", default=0)

    class Meta:
        ordering = ["source", "position"]
        verbose_name = "фрагмент"
        verbose_name_plural = "фрагменты"

    def __str__(self):
        return f"{self.source} · {self.section or self.position}"


class AssistantSettings(models.Model):
    """Единственная запись: выключатель и лимиты помощника (Админка → Иммиграционный помощник → Настройки)."""

    enabled = models.BooleanField(
        "открыт для читателей", default=False,
        help_text="Выключено — помощник работает только для сотрудников (закрытая проверка)",
    )
    daily_questions = models.PositiveSmallIntegerField("вопросов в день на читателя", default=10)
    monthly_budget_usd = models.DecimalField(
        "предохранитель: $ в месяц на весь помощник", max_digits=8, decimal_places=2, default=Decimal("50.00"),
        help_text="Когда расход на помощник за календарный месяц дойдёт до этой суммы, он перестаёт отвечать "
                  "до 1-го числа (по учёту вызовов ИИ)",
    )
    max_question_chars = models.PositiveSmallIntegerField("предел длины вопроса, знаков", default=800)
    max_answer_tokens = models.PositiveSmallIntegerField("предел длины ответа, токенов", default=1500)
    retention_days = models.PositiveSmallIntegerField(
        "хранить переписку, дней", default=30, help_text="Старше — удаляется автоматически",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "настройки помощника"
        verbose_name_plural = "настройки помощника"

    def __str__(self):
        return "Настройки помощника"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "AssistantSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# Версия текста согласия: меняете текст в CONSENT_TEXT — поднимите версию, и новые согласия сохранятся с ней.
CONSENT_VERSION = "2026-11-27"


class Reader(models.Model):
    """Читатель помощника: аккаунт без пароля (вход по коду из письма) и его согласие."""

    class Region(models.TextChoices):
        MIAMI = "miami", _("Майами и Южная Флорида")
        ORLANDO = "orlando", _("Орландо и Центральная Флорида")
        TAMPA = "tampa", _("Тампа")
        JACKSONVILLE = "jacksonville", _("Джексонвилл")

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reader")
    region = models.CharField("регион", max_length=12, choices=Region.choices, blank=True)
    consent_at = models.DateTimeField("согласие: когда", null=True, blank=True)
    consent_version = models.CharField("согласие: версия текста", max_length=20, blank=True)
    consent_ip = models.GenericIPAddressField("согласие: IP", null=True, blank=True)
    created_at = models.DateTimeField("зарегистрирован", default=timezone.now)

    class Meta:
        verbose_name = "читатель помощника"
        verbose_name_plural = "читатели помощника"

    def __str__(self):
        return self.user.email or self.user.username

    @property
    def has_consent(self) -> bool:
        return bool(self.consent_at)


class LoginCode(models.Model):
    """Одноразовый код входа: храним только хэш, живёт 15 минут, 5 попыток."""

    email = models.EmailField(db_index=True)
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    used = models.BooleanField(default=False)
    ip_hash = models.CharField(max_length=32, blank=True, db_index=True)

    LIFETIME = timedelta(minutes=15)
    MAX_ATTEMPTS = 5

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_valid(self) -> bool:
        return not self.used and self.attempts < self.MAX_ATTEMPTS and \
            self.created_at > timezone.now() - self.LIFETIME


class QuestionQuerySet(models.QuerySet):
    def today(self):
        start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.filter(created_at__gte=start)

    def expired(self, days: int):
        return self.filter(created_at__lt=timezone.now() - timedelta(days=days))


class Question(models.Model):
    """Вопрос читателя и ответ помощника. Номера (A-number, дела USCIS, SSN) маскируются до сохранения."""

    class Kind(models.TextChoices):
        ANSWERED = "answered", "ответ по источникам"
        NO_SOURCES = "no_sources", "в базе нет"
        PERSONAL = "personal", "личная ситуация — отказ + адвокаты"
        PROHIBITED = "prohibited", "запрещённое — отказ"
        OFF_TOPIC = "off_topic", "не про иммиграцию"
        LIMIT = "limit", "лимит"
        ERROR = "error", "сбой"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="immigration_questions")
    language = models.CharField("язык", max_length=2, default="ru")
    question = models.TextField("вопрос (замаскирован)")
    kind = models.CharField("итог", max_length=12, choices=Kind.choices, db_index=True)
    answer = models.TextField("ответ", blank=True)
    sources = models.JSONField("источники", default=list, blank=True)
    lawyers = models.JSONField("адвокаты", default=list, blank=True)
    search_query = models.CharField("поисковый запрос", max_length=300, blank=True)
    cost_usd = models.DecimalField("стоимость, $", max_digits=10, decimal_places=6, default=Decimal("0"))
    feedback = models.SmallIntegerField("оценка", null=True, blank=True, choices=[(1, "👍"), (-1, "👎")],
                                        db_index=True)
    reviewed = models.BooleanField("разобрано редакцией", default=False)
    created_at = models.DateTimeField("время", default=timezone.now, db_index=True)

    objects = QuestionQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "вопрос помощнику"
        verbose_name_plural = "вопросы помощнику"

    def __str__(self):
        return self.question[:80]

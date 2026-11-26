"""«Детям»: каталог детских кружков и секций Центральной Флориды.

Кружок публикует только редактор (статус draft → published). Всё, что неизвестно, остаётся пустым и
показывается как «не указано»: ни цен, ни расписаний, ни статуса стипендий мы не придумываем.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from core.i18n import Translatable, uk_field
from core.text import make_slug

MAX_AGE = 18
STALE_DAYS = 90  # «не проверялось больше 90 дней» — фильтр в админке


class Category(models.TextChoices):
    """Направления. Значение — оно же адрес страницы: /deti/shakhmaty/."""

    MATH = "matematika", _("Математика")
    CHESS = "shakhmaty", _("Шахматы")
    DANCE = "tantsy", _("Балет и танцы")
    GYMNASTICS = "gimnastika", _("Гимнастика")
    SWIMMING = "plavanie", _("Плавание")
    MUSIC = "muzyka", _("Музыка")
    ART = "risovanie", _("Рисование и искусство")
    LANGUAGES = "yazyki", _("Языки")
    ROBOTICS = "robototekhnika", _("Робототехника и программирование")
    MARTIAL = "edinoborstva", _("Единоборства")
    TEAM = "komandnyy-sport", _("Командный спорт")
    SCHOOL_PREP = "podgotovka-k-shkole", _("Подготовка к школе")
    OTHER = "drugoe", _("Другое")


# Для заголовков: «Кружки по шахматам для детей в Орландо — на русском языке».
CATEGORY_TITLES = {
    Category.MATH: _("Кружки по математике"),
    Category.CHESS: _("Кружки по шахматам"),
    Category.DANCE: _("Студии балета и танцев"),
    Category.GYMNASTICS: _("Секции гимнастики"),
    Category.SWIMMING: _("Секции плавания"),
    Category.MUSIC: _("Музыкальные кружки и студии"),
    Category.ART: _("Студии рисования и искусства"),
    Category.LANGUAGES: _("Языковые кружки"),
    Category.ROBOTICS: _("Кружки робототехники и программирования"),
    Category.MARTIAL: _("Секции единоборств"),
    Category.TEAM: _("Секции командного спорта"),
    Category.SCHOOL_PREP: _("Подготовка к школе"),
    Category.OTHER: _("Другие кружки"),
}

# Адреса внутри /deti/, которые не могут быть адресом города или направления.
RESERVED_SLUGS = {"kruzhok", "dobavit", "stipendii-pep-fes", "karta", *Category.values}


class Format(models.TextChoices):
    OFFLINE = "offline", _("очно")
    ONLINE = "online", _("онлайн")
    BOTH = "both", _("очно и онлайн")


class Esa(models.TextChoices):
    YES = "yes", _("принимает")
    NO = "no", _("не принимает")
    UNKNOWN = "unknown", _("не указано")


# Программы стипендий Step Up For Students: (код в фильтре и CSV, поле модели, подпись)
ESA_PROGRAMS = [
    ("pep", "esa_pep", "PEP"),
    ("fes-ua", "esa_fes_ua", "FES-UA"),
    ("fes-eo", "esa_fes_eo", "FES-EO"),
    ("ftc", "esa_ftc", "FTC"),
]

# Языки занятий: (код в фильтре и CSV, поле модели, подпись)
LANGUAGES = [
    ("ru", "lang_ru", pgettext_lazy("язык занятий", "русский")),
    ("uk", "lang_uk", pgettext_lazy("язык занятий", "украинский")),
    ("en", "lang_en", pgettext_lazy("язык занятий", "английский")),
    ("bilingual", "lang_bilingual", pgettext_lazy("язык занятий", "двуязычный")),
]


class CityQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class City(Translatable):
    """Справочник городов для страниц /deti/<город>/. Расширяется в админке."""

    name = models.CharField("название", max_length=60, help_text="Орландо")
    name_en = models.CharField("по-английски", max_length=60, help_text="Orlando — для импорта из CSV и адресов")
    name_locative = models.CharField("где? (в Орландо)", max_length=80, help_text="Для заголовков: «Кружки в Лонгвуде»")
    slug = models.SlugField("адрес (латиница)", max_length=60, unique=True)
    lat = models.FloatField("широта", null=True, blank=True)
    lng = models.FloatField("долгота", null=True, blank=True)
    order = models.PositiveSmallIntegerField("порядок", default=0)
    is_active = models.BooleanField("показывать", default=True)

    TRANSLATED = ("name", "name_locative")
    name_uk = uk_field(name)
    name_locative_uk = uk_field(name_locative)

    objects = CityQuerySet.as_manager()

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "город"
        verbose_name_plural = "города (детские кружки)"

    def __str__(self):
        return self.name

    def clean(self):
        if self.slug in RESERVED_SLUGS:
            raise ValidationError({"slug": f"Адрес «{self.slug}» занят направлением или служебной страницей."})

    def get_absolute_url(self):
        return reverse("kids:section", args=[self.slug])


class ClubQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Club.Status.PUBLISHED)

    def stale(self, days: int = STALE_DAYS):
        """Не проверялись больше days дней (или ни разу)."""
        border = timezone.localdate() - timedelta(days=days)
        return self.filter(models.Q(last_verified_at__isnull=True) | models.Q(last_verified_at__lt=border))

    def ordered(self):
        return self.order_by("-is_featured", models.F("city__order").asc(nulls_last=True), "name")


class Club(Translatable):
    class Status(models.TextChoices):
        DRAFT = "draft", "черновик"
        PUBLISHED = "published", "опубликован"
        ARCHIVED = "archived", "в архиве"

    class Origin(models.TextChoices):
        ADMIN = "admin", "редакция"
        FORM = "form", "форма на сайте"
        IMPORT = "import", "импорт CSV"

    class Role(models.TextChoices):
        OWNER = "owner", _("владелец или сотрудник кружка")
        PARENT = "parent", _("родитель")

    name = models.CharField("название", max_length=160)
    slug = models.SlugField("адрес (латиница)", max_length=120, unique=True, blank=True,
                            help_text="Пусто — составится из названия и города")
    description = models.TextField("описание", blank=True, help_text="По-русски, 2–5 предложений: чем занимаются, для кого")
    category = models.CharField("направление", max_length=24, choices=Category.choices, db_index=True)

    age_min = models.PositiveSmallIntegerField("возраст от", null=True, blank=True,
                                               validators=[MaxValueValidator(MAX_AGE)])
    age_max = models.PositiveSmallIntegerField("возраст до", null=True, blank=True,
                                               validators=[MaxValueValidator(MAX_AGE)])

    lang_ru = models.BooleanField("занятия на русском", default=False)
    lang_uk = models.BooleanField("занятия на украинском", default=False)
    lang_en = models.BooleanField("занятия на английском", default=False)
    lang_bilingual = models.BooleanField("двуязычные занятия", default=False)

    city = models.ForeignKey(City, verbose_name="город", null=True, blank=True, on_delete=models.PROTECT,
                             related_name="clubs", help_text="Пусто — только онлайн")
    address = models.CharField("адрес", max_length=200, blank=True)
    lat = models.FloatField("широта", null=True, blank=True)
    lng = models.FloatField("долгота", null=True, blank=True)
    format = models.CharField("формат", max_length=8, choices=Format.choices, default=Format.OFFLINE)

    schedule_text = models.TextField("расписание", blank=True, help_text="Свободный текст, только проверенное")
    price_text = models.TextField("стоимость", blank=True, help_text="Свободный текст, только проверенное")

    esa_status = models.CharField("оплата из стипендии", max_length=8, choices=Esa.choices, default=Esa.UNKNOWN,
                                  db_index=True)
    esa_pep = models.BooleanField("PEP", default=False)
    esa_fes_ua = models.BooleanField("FES-UA", default=False)
    esa_fes_eo = models.BooleanField("FES-EO", default=False)
    esa_ftc = models.BooleanField("FTC", default=False)
    esa_note = models.CharField("примечание о стипендии", max_length=300, blank=True)

    phone = models.CharField("телефон", max_length=40, blank=True)
    email = models.EmailField("e-mail", blank=True)
    website = models.URLField("сайт", max_length=500, blank=True)
    instagram = models.URLField("Instagram", max_length=300, blank=True)
    facebook = models.URLField("Facebook", max_length=300, blank=True)
    telegram = models.CharField("Telegram", max_length=100, blank=True, help_text="@имя или ссылка t.me")
    whatsapp = models.CharField("WhatsApp", max_length=40, blank=True, help_text="Номер или ссылка wa.me")

    source_url = models.URLField("источник данных", max_length=500, blank=True)
    last_verified_at = models.DateField("проверено", null=True, blank=True, db_index=True)
    status = models.CharField("статус", max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    is_featured = models.BooleanField("выделить (платно)", default=False,
                                      help_text="На будущее: платное размещение")

    origin = models.CharField("откуда", max_length=8, choices=Origin.choices, default=Origin.ADMIN)
    submitter_role = models.CharField("заявитель", max_length=8, choices=Role.choices, blank=True)
    submitter_name = models.CharField("имя заявителя", max_length=120, blank=True)
    submitter_email = models.EmailField("e-mail заявителя", blank=True)
    photos_link = models.URLField("ссылка на фото от заявителя", max_length=500, blank=True)
    ip_hash = models.CharField("IP (хэш)", max_length=32, blank=True, db_index=True)
    editor_note = models.TextField("заметка редакции", blank=True, help_text="Видна только в админке")
    created_at = models.DateTimeField("добавлено", default=timezone.now, db_index=True)
    updated_at = models.DateTimeField("изменено", auto_now=True)

    TRANSLATED = ("description", "schedule_text", "price_text", "esa_note")
    description_uk = uk_field(description)
    schedule_text_uk = uk_field(schedule_text)
    price_text_uk = uk_field(price_text)
    esa_note_uk = uk_field(esa_note)

    objects = ClubQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        verbose_name = "кружок"
        verbose_name_plural = "кружки и секции"

    def __str__(self):
        return self.name

    def clean(self):
        if self.age_min is not None and self.age_max is not None and self.age_min > self.age_max:
            raise ValidationError({"age_max": "«Возраст до» меньше, чем «возраст от»."})
        if self.format != Format.ONLINE and self.city is None and self.status == self.Status.PUBLISHED:
            raise ValidationError({"city": "Для очных занятий укажите город."})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self.unique_slug()
        super().save(*args, **kwargs)

    def unique_slug(self) -> str:
        city = self.city.name_en if self.city_id else ""
        base = make_slug(f"{self.name} {city}", 100) or "kruzhok"
        slug, n = base, 2
        while Club.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug, n = f"{base}-{n}", n + 1
        return slug

    def get_absolute_url(self):
        return reverse("kids:club", args=[self.slug])

    def get_report_url(self):
        return reverse("kids:report", args=[self.slug])

    # --- для шаблонов ---

    @property
    def is_published(self) -> bool:
        return self.status == self.Status.PUBLISHED

    @property
    def is_archived(self) -> bool:
        return self.status == self.Status.ARCHIVED

    @property
    def category_label(self) -> str:
        return Category(self.category).label if self.category in Category.values else ""

    @property
    def languages(self) -> list[str]:
        return [str(label) for _code, field, label in LANGUAGES if getattr(self, field)]

    @property
    def esa_programs(self) -> list[str]:
        return [label for _code, field, label in ESA_PROGRAMS if getattr(self, field)]

    @property
    def accepts_esa(self) -> bool:
        return self.esa_status == Esa.YES

    @property
    def age_text(self) -> str:
        if self.age_min is not None and self.age_max is not None:
            return _("от %(a)s до %(b)s лет") % {"a": self.age_min, "b": self.age_max}
        if self.age_min is not None:
            return _("от %(a)s лет") % {"a": self.age_min}
        if self.age_max is not None:
            return _("до %(b)s лет") % {"b": self.age_max}
        return ""

    @property
    def has_offline(self) -> bool:
        return self.format != Format.ONLINE

    @property
    def point(self) -> tuple[float, float] | None:
        """Точка на карте: свои координаты, иначе центр города (для очных занятий)."""
        if self.lat is not None and self.lng is not None:
            return (self.lat, self.lng)
        if self.has_offline and self.city_id and self.city.lat is not None:
            return (self.city.lat, self.city.lng)
        return None

    @property
    def point_is_exact(self) -> bool:
        return self.lat is not None and self.lng is not None

    @property
    def map_query(self) -> str:
        """Запрос для встроенной карты Google в карточке."""
        if self.point_is_exact:
            return f"{self.lat},{self.lng}"
        if self.address:
            return self.address
        return f"{self.city.name_en}, FL" if self.city_id else ""

    @property
    def phone_href(self) -> str:
        digits = "".join(ch for ch in self.phone if ch.isdigit() or ch == "+")
        return f"tel:{digits}" if digits else ""

    @property
    def telegram_url(self) -> str:
        value = self.telegram.strip()
        if not value:
            return ""
        if value.startswith("http"):
            return value
        return f"https://t.me/{value.lstrip('@')}"

    @property
    def whatsapp_url(self) -> str:
        value = self.whatsapp.strip()
        if not value or value.startswith("http"):
            return value
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) == 10:  # номер США без кода страны
            digits = "1" + digits
        return f"https://wa.me/{digits}" if digits else ""

    @property
    def domain(self) -> str:
        return self.website.split("://", 1)[-1].split("/", 1)[0].removeprefix("www.") if self.website else ""

    def public_photos(self):
        """Только фото с подтверждённым разрешением владельца кружка."""
        return [p for p in self.photos.all() if p.permission_confirmed and p.media_id]


class ClubPhoto(models.Model):
    club = models.ForeignKey(Club, verbose_name="кружок", on_delete=models.CASCADE, related_name="photos")
    media = models.ForeignKey("gallery.MediaItem", verbose_name="фото", on_delete=models.CASCADE, related_name="+",
                              limit_choices_to={"kind": "photo"})
    permission_confirmed = models.BooleanField(
        "владелец разрешил публикацию", default=False,
        help_text="Обязательно для показа. Фото с детьми — только с явного разрешения владельца кружка.",
    )
    order = models.PositiveSmallIntegerField("порядок", default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "фото кружка"
        verbose_name_plural = "фото кружка"

    def __str__(self):
        return f"{self.club} · фото {self.order}"


class ClubReport(models.Model):
    """«Сообщить об ошибке / неактуально» с карточки кружка."""

    class Reason(models.TextChoices):
        ERROR = "error", _("Ошибка в данных")
        OUTDATED = "outdated", _("Информация устарела")
        CLOSED = "closed", _("Кружок закрылся")
        OTHER = "other", _("Другое")

    class Status(models.TextChoices):
        NEW = "new", "новое"
        DONE = "done", "разобрано"

    club = models.ForeignKey(Club, verbose_name="кружок", on_delete=models.CASCADE, related_name="reports")
    reason = models.CharField("что не так", max_length=10, choices=Reason.choices, default=Reason.ERROR)
    comment = models.TextField("комментарий", max_length=1000, blank=True)
    contact = models.CharField("как связаться", max_length=200, blank=True)
    status = models.CharField("статус", max_length=6, choices=Status.choices, default=Status.NEW, db_index=True)
    ip_hash = models.CharField("IP (хэш)", max_length=32, blank=True, db_index=True)
    created_at = models.DateTimeField("получено", default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "сообщение об ошибке"
        verbose_name_plural = "сообщения об ошибках (кружки)"

    def __str__(self):
        return f"{self.club} · {self.get_reason_display()}"

import re

from django import forms
from django.utils.translation import gettext as _, gettext_lazy, gettext_noop

from core import geo, images

from .models import MAX_PHOTOS, Ad, Category, Report
from .places import is_florida_zip

TELEGRAM_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")

# Ошибки core.images.prepare, которые видит автор, — для перевода в clean_photos.
IMAGE_ERRORS = (gettext_noop("Картинка больше 8 МБ — уменьшите её, пожалуйста."),
                gettext_noop("Слишком большое разрешение картинки."),
                gettext_noop("Не получилось открыть картинку. Подойдёт JPG, PNG или WebP."))


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        return [super(MultipleFileField, self).clean(f, initial) for f in files]


def grouped_categories():
    """Рубрики для выпадающего списка, сгруппированные по разделам."""
    sections = Category.objects.filter(parent=None).prefetch_related("children")
    return [("", _("Выберите рубрику"))] + [
        (s.loc("name"), [(c.pk, c.loc("name")) for c in s.children.all()]) for s in sections
    ]


def normalize_phone(value: str) -> str:
    """«(305) 555-12-34» → «+13055551234». Американские номера без кода страны дополняются +1."""
    raw = value.strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if len(digits) == 10 and not raw.startswith("+"):
        digits = "1" + digits
    if digits.startswith("1") and len(digits) != 11 or not 10 <= len(digits) <= 15:
        raise forms.ValidationError(_("Проверьте номер: например, (305) 555-1234 или +380 67 123 4567."))
    return "+" + digits


def normalize_telegram(value: str) -> str:
    name = value.strip()
    name = re.sub(r"^(https?://)?(t\.me|telegram\.me)/", "", name, flags=re.IGNORECASE).lstrip("@").strip("/")
    if name and not TELEGRAM_RE.match(name):
        raise forms.ValidationError(_("Укажите имя пользователя Telegram, например @ivan_miami."))
    return name


class AdForm(forms.ModelForm):
    """Подача и правка объявления. Контакты видны посетителям только по кнопке «Показать контакты»."""

    photos = MultipleFileField(
        label=gettext_lazy("Фото"), required=False,
    )
    company = forms.CharField(required=False, widget=forms.TextInput(attrs={
        "autocomplete": "off", "tabindex": "-1",
    }))  # ловушка для ботов: поле скрыто, человек его не заполняет
    agree = forms.BooleanField(
        label=gettext_lazy("Объявление моё, данные верны, с правилами согласен. Понимаю, что контакты увидят посетители сайта"),
    )

    class Meta:
        model = Ad
        fields = ["category", "title", "description", "price", "price_unit", "city", "zip_code",
                  "contact_name", "phone", "has_whatsapp", "telegram"]
        labels = {
            "category": gettext_lazy("Рубрика"),
            "title": gettext_lazy("Заголовок"),
            "description": gettext_lazy("Текст объявления"),
            "price": gettext_lazy("Цена, $"),
            "price_unit": gettext_lazy("За что"),
            "city": gettext_lazy("Город во Флориде"),
            "zip_code": gettext_lazy("ZIP-код"),
            "contact_name": gettext_lazy("Ваше имя"),
            "phone": gettext_lazy("Телефон"),
            "has_whatsapp": gettext_lazy("На этом номере есть WhatsApp"),
            "telegram": "Telegram",
        }
        help_texts = {
            "title": gettext_lazy("Коротко и по делу: «Сдам 1-bedroom в Санни-Айлс», «Диван IKEA, как новый»."),
            "description": gettext_lazy("Состояние, размеры, условия, график — всё, что спросил бы покупатель. Без капса."),
            "price": gettext_lazy("Пусто — договорная, 0 — бесплатно."),
            "zip_code": gettext_lazy("Необязательно, но так объявление найдут соседи. Точный адрес не показываем."),
            "phone": gettext_lazy("Укажите телефон или Telegram — хотя бы что-то одно."),
            "telegram": gettext_lazy("Имя пользователя, например @ivan_miami."),
        }
        widgets = {
            "title": forms.TextInput(attrs={"maxlength": 100}),
            "description": forms.Textarea(attrs={"rows": 7, "maxlength": 3000}),
            "price": forms.NumberInput(attrs={"min": 0, "max": 99999999, "inputmode": "numeric"}),
            "city": forms.TextInput(attrs={"maxlength": 80, "autocomplete": "address-level2",
                                           "placeholder": gettext_lazy("Например: Санни-Айлс-Бич")}),
            "zip_code": forms.TextInput(attrs={"maxlength": 5, "inputmode": "numeric", "autocomplete": "postal-code",
                                               "pattern": "[0-9]{5}", "placeholder": "33160"}),
            "contact_name": forms.TextInput(attrs={"maxlength": 60, "autocomplete": "given-name"}),
            "phone": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel", "placeholder": "(305) 555-1234"}),
            "telegram": forms.TextInput(attrs={"placeholder": "@username", "autocapitalize": "off"}),
        }

    def __init__(self, *args, existing_photos=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = grouped_categories()
        self.fields["photos"].help_text = _(
            "До %(n)s фото, JPG, PNG или WebP до 8 МБ каждое. Появятся после автоматической проверки.") % {"n": MAX_PHOTOS}
        self.fields["category"].queryset = Category.objects.exclude(parent=None)
        self.existing_photos = existing_photos
        self.photo_bytes: list[bytes] = []

    def clean_title(self):
        title = " ".join(self.cleaned_data["title"].split())
        if len(title) < 5:
            raise forms.ValidationError(_("Заголовок слишком короткий."))
        return title

    def clean_description(self):
        text = self.cleaned_data["description"].strip()
        if len(text) < 20:
            raise forms.ValidationError(_("Опишите подробнее — хотя бы пару предложений."))
        return text

    def clean_zip_code(self):
        value = self.cleaned_data["zip_code"].strip()
        if value and not is_florida_zip(value):
            raise forms.ValidationError(_("Это не ZIP-код Флориды: они от 32003 до 34997."))
        return value

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])

    def clean_telegram(self):
        return normalize_telegram(self.cleaned_data["telegram"])

    def clean_photos(self):
        uploads = self.cleaned_data.get("photos") or []
        if self.existing_photos + len(uploads) > MAX_PHOTOS:
            left = MAX_PHOTOS - self.existing_photos
            raise forms.ValidationError(_("Можно добавить ещё не больше %(n)s фото.") % {"n": left} if self.existing_photos
                                        else _("Не больше %(n)s фото.") % {"n": MAX_PHOTOS})
        for upload in uploads:
            try:
                self.photo_bytes.append(images.prepare(upload))
            except images.ImageError as exc:
                raise forms.ValidationError(f"{upload.name}: {_(str(exc))}") from exc
        return uploads

    def clean(self):
        data = super().clean()
        if not data.get("phone") and not data.get("telegram") and "phone" not in self.errors \
                and "telegram" not in self.errors:
            self.add_error("phone", _("Укажите телефон или Telegram, иначе с вами не смогут связаться."))
        if data.get("has_whatsapp") and not data.get("phone"):
            data["has_whatsapp"] = False
        if data.get("price") is None or data.get("price") == 0:
            data["price_unit"] = ""
        return data


class ReportForm(forms.Form):
    reason = forms.ChoiceField(label=gettext_lazy("Что не так"), choices=Report.Reason.choices, widget=forms.RadioSelect)
    comment = forms.CharField(label=gettext_lazy("Подробности"), required=False, max_length=500,
                              widget=forms.Textarea(attrs={"rows": 3, "maxlength": 500}))


class FilterForm(forms.Form):
    """Фильтры списка. Ошибочные значения просто игнорируются."""

    SORTS = [("", gettext_lazy("Сначала новые")), ("cheap", gettext_lazy("Сначала дешёвые")),
             ("expensive", gettext_lazy("Сначала дорогие"))]

    q = forms.CharField(required=False, max_length=80)
    region = forms.CharField(required=False, max_length=20)
    zip = forms.CharField(required=False, max_length=5)
    price_min = forms.IntegerField(required=False, min_value=0)
    price_max = forms.IntegerField(required=False, min_value=0)
    photo = forms.BooleanField(required=False)
    sort = forms.ChoiceField(required=False, choices=SORTS)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # «Ближе к Майами»… — на каждый запрос, чтобы подписи были на языке страницы.
        self.fields["sort"].choices = [*self.SORTS, *[(f"near-{slug}", label) for slug, label in geo.hub_choices()]]

    def clean_zip(self):
        value = self.cleaned_data["zip"].strip()
        return value if is_florida_zip(value) else ""

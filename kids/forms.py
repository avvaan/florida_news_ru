from django import forms
from django.utils.translation import gettext_lazy as _

from .models import ESA_PROGRAMS, LANGUAGES, MAX_AGE, Category, City, Club, ClubReport, Esa, Format

OTHER_CITY = "other"


class ClubSubmitForm(forms.ModelForm):
    """«Добавить кружок»: владелец или родитель. Создаёт черновик — публикует только редактор."""

    company = forms.CharField(required=False, widget=forms.TextInput(attrs={"autocomplete": "off", "tabindex": "-1"}))
    city_choice = forms.ChoiceField(label=_("Город"), required=False)
    city_other = forms.CharField(label=_("Другой город"), required=False, max_length=80)
    languages = forms.MultipleChoiceField(
        label=_("Язык занятий"), required=True, widget=forms.CheckboxSelectMultiple,
        choices=[(code, label) for code, _field, label in LANGUAGES],
    )
    esa_programs = forms.MultipleChoiceField(
        label=_("Какие стипендии принимает"), required=False, widget=forms.CheckboxSelectMultiple,
        choices=[(code, label) for code, _field, label in ESA_PROGRAMS],
    )
    agree = forms.BooleanField(
        label=_("Данные верны. Понимаю, что редакция проверит их перед публикацией и может сократить описание"),
    )

    class Meta:
        model = Club
        fields = ["submitter_role", "name", "category", "format", "address", "age_min", "age_max", "description",
                  "schedule_text", "price_text", "esa_status", "esa_note", "phone", "email", "website", "instagram",
                  "telegram", "whatsapp", "photos_link", "submitter_name", "submitter_email"]
        labels = {
            "submitter_role": _("Кто вы"),
            "name": _("Название кружка или имя преподавателя"),
            "category": _("Направление"),
            "format": _("Формат занятий"),
            "address": _("Адрес занятий"),
            "age_min": _("Возраст детей: от"),
            "age_max": _("до"),
            "description": _("Чем занимаются"),
            "schedule_text": _("Расписание"),
            "price_text": _("Стоимость"),
            "esa_status": _("Принимает оплату из стипендий Step Up For Students (PEP, FES, FTC)?"),
            "esa_note": _("Уточнение о стипендии"),
            "phone": _("Телефон"),
            "email": _("E-mail кружка"),
            "website": _("Сайт"),
            "instagram": _("Instagram"),
            "telegram": _("Telegram"),
            "whatsapp": _("WhatsApp"),
            "photos_link": _("Ссылка на фото (Google Диск, Instagram и т. п.)"),
            "submitter_name": _("Ваше имя"),
            "submitter_email": _("Ваш e-mail"),
        }
        help_texts = {
            "description": _("2–5 предложений: что за занятия, для кого, кто ведёт. Без рекламных обещаний."),
            "schedule_text": _("Как есть, например: «вт и чт 17:00–18:00». Не знаете — оставьте пустым."),
            "price_text": _("Как есть, например: «$120 в месяц» или «первое занятие бесплатно». Не знаете — пусто."),
            "photos_link": _("Фото с детьми публикуем только с разрешения владельца кружка."),
            "submitter_email": _("Напишем, если будут вопросы. На сайте не публикуется."),
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5, "maxlength": 1500}),
            "schedule_text": forms.Textarea(attrs={"rows": 2, "maxlength": 500}),
            "price_text": forms.Textarea(attrs={"rows": 2, "maxlength": 500}),
            "submitter_role": forms.RadioSelect,
            "age_min": forms.NumberInput(attrs={"min": 0, "max": MAX_AGE, "inputmode": "numeric"}),
            "age_max": forms.NumberInput(attrs={"min": 0, "max": MAX_AGE, "inputmode": "numeric"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
            "website": forms.URLInput(attrs={"placeholder": "https://"}),
            "instagram": forms.URLInput(attrs={"placeholder": "https://instagram.com/…"}),
            "photos_link": forms.URLInput(attrs={"placeholder": "https://"}),
            "submitter_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "submitter_email": forms.EmailInput(attrs={"autocomplete": "email"}),
        }

    field_order = ["submitter_role", "name", "category", "format", "city_choice", "city_other", "address",
                   "age_min", "age_max", "languages", "description", "schedule_text", "price_text", "esa_status",
                   "esa_programs", "esa_note", "phone", "email", "website", "instagram", "telegram", "whatsapp",
                   "photos_link", "submitter_name", "submitter_email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["submitter_role"].required = True
        self.fields["submitter_role"].choices = list(Club.Role.choices)
        self.fields["submitter_name"].required = True
        self.fields["submitter_email"].required = True
        self.fields["category"].choices = [("", _("— выберите —")), *Category.choices]
        self.fields["format"].choices = list(Format.choices)
        self.fields["esa_status"].choices = list(Esa.choices)
        cities = [(c.slug, c.loc("name")) for c in City.objects.active()]
        self.fields["city_choice"].choices = [("", _("— выберите —")), *cities, (OTHER_CITY, _("Другой город"))]

    def clean_description(self):
        text = self.cleaned_data["description"].strip()
        if len(text) < 30:
            raise forms.ValidationError(_("Опишите занятия чуть подробнее — хотя бы пару предложений."))
        return text

    def clean(self):
        data = super().clean()
        fmt = data.get("format")
        choice = data.get("city_choice")
        if fmt != Format.ONLINE and not choice:
            self.add_error("city_choice", _("Укажите город, где проходят занятия."))
        if choice == OTHER_CITY and not (data.get("city_other") or "").strip():
            self.add_error("city_other", _("Напишите, какой город."))
        a, b = data.get("age_min"), data.get("age_max")
        if a is not None and b is not None and a > b:
            self.add_error("age_max", _("«До» меньше, чем «от»."))
        if not any(data.get(name) for name in ("phone", "email", "website", "instagram", "telegram", "whatsapp")):
            raise forms.ValidationError(_("Укажите хотя бы один способ связи с кружком: телефон, сайт, e-mail или соцсеть."))
        if data.get("esa_status") != Esa.YES:
            data["esa_programs"] = []
        return data

    def save(self, commit=True):
        club = super().save(commit=False)
        data = self.cleaned_data
        club.status, club.origin = Club.Status.DRAFT, Club.Origin.FORM
        choice = data.get("city_choice")
        club.city = City.objects.filter(slug=choice).first() if choice and choice != OTHER_CITY else None
        for code, field, _label in LANGUAGES:
            setattr(club, field, code in data.get("languages", []))
        for code, field, _label in ESA_PROGRAMS:
            setattr(club, field, code in data.get("esa_programs", []))
        if choice == OTHER_CITY:
            club.editor_note = f"Город из формы: {data['city_other'].strip()}"
        if commit:
            club.save()
        return club


class ReportForm(forms.ModelForm):
    company = forms.CharField(required=False, widget=forms.TextInput(attrs={"autocomplete": "off", "tabindex": "-1"}))

    class Meta:
        model = ClubReport
        fields = ["reason", "comment", "contact"]
        labels = {"reason": _("Что не так"), "comment": _("Что исправить"),
                  "contact": _("Как с вами связаться (необязательно)")}
        widgets = {"reason": forms.RadioSelect, "comment": forms.Textarea(attrs={"rows": 3, "maxlength": 1000})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reason"].choices = list(ClubReport.Reason.choices)


class FilterForm(forms.Form):
    """Панель фильтров (GET). Отправляется на /deti/ — вью переводит её на постоянный адрес."""

    cat = forms.ChoiceField(label=_("Направление"), required=False)
    city = forms.ChoiceField(label=_("Город"), required=False)
    age = forms.IntegerField(label=_("Возраст ребёнка"), required=False, min_value=0, max_value=MAX_AGE,
                             widget=forms.NumberInput(attrs={"inputmode": "numeric", "placeholder": _("лет")}))
    lang = forms.ChoiceField(label=_("Язык занятий"), required=False)
    esa = forms.ChoiceField(label=_("Оплата из стипендии"), required=False)
    format = forms.ChoiceField(label=_("Формат"), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        any_ = ("", _("любой"))
        self.fields["cat"].choices = [("", _("все направления")), *Category.choices]
        self.fields["city"].choices = [("", _("все города")), *[(c.slug, c.loc("name")) for c in City.objects.active()]]
        self.fields["lang"].choices = [any_, *[(code, label) for code, _f, label in LANGUAGES]]
        self.fields["esa"].choices = [("", _("неважно")), ("any", _("принимает PEP/FES/FTC")),
                                      *[(code, _("принимает %(p)s") % {"p": label}) for code, _f, label in ESA_PROGRAMS]]
        self.fields["format"].choices = [any_, ("offline", _("очно")), ("online", _("онлайн"))]

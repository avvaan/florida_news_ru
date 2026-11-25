from datetime import timedelta

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core import images

from .models import Event


class EventForm(forms.ModelForm):
    """Заявка в афишу. Контакт организатора не публикуется — он нужен только редакции."""

    image = forms.FileField(
        label=_("Афиша или фото"), required=False,
        help_text=_("JPG, PNG или WebP до 8 МБ. Появится на сайте после автоматической проверки."),
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
    )
    company = forms.CharField(required=False, widget=forms.TextInput(attrs={
        "autocomplete": "off", "tabindex": "-1",
    }))  # ловушка для ботов: поле скрыто, человек его не заполняет
    agree = forms.BooleanField(
        label=_("Подтверждаю, что представляю организатора и данные верны. Согласен с правилами афиши"),
    )

    class Meta:
        model = Event
        fields = ["title", "description", "starts_on", "starts_at", "ends_on", "venue", "address", "city",
                  "price", "url", "organizer", "contact_name", "contact_email"]
        labels = {
            "title": _("Название события"),
            "description": _("Что будет"),
            "starts_on": _("Дата"),
            "starts_at": _("Начало"),
            "ends_on": _("Последний день"),
            "venue": _("Место"),
            "address": _("Адрес"),
            "city": _("Город во Флориде"),
            "price": _("Цена"),
            "url": _("Билеты или подробности"),
            "organizer": _("Организатор"),
            "contact_name": _("Ваше имя"),
            "contact_email": _("Ваш e-mail"),
        }
        help_texts = {
            "description": _("2–5 предложений: программа, для кого, на каком языке. Без капса и рекламных обещаний."),
            "ends_on": _("Только если событие идёт несколько дней"),
            "venue": _("Например: Rachel Thompson Theater, парк Lake Eola"),
            "price": _("Например: бесплатно, $25, от $15"),
            "contact_email": _("Сюда напишем, если будут вопросы. На сайте не публикуется."),
        }
        widgets = {
            "title": forms.TextInput(attrs={"maxlength": 160}),
            "description": forms.Textarea(attrs={"rows": 5, "maxlength": 2000}),
            "starts_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "starts_at": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "ends_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "venue": forms.TextInput(attrs={"maxlength": 160}),
            "address": forms.TextInput(attrs={"maxlength": 200, "autocomplete": "street-address"}),
            "city": forms.TextInput(attrs={"maxlength": 80, "autocomplete": "address-level2"}),
            "price": forms.TextInput(attrs={"maxlength": 80}),
            "url": forms.URLInput(attrs={"placeholder": "https://"}),
            "organizer": forms.TextInput(attrs={"maxlength": 160, "autocomplete": "organization"}),
            "contact_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "contact_email": forms.EmailInput(attrs={"autocomplete": "email"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        for name in ("starts_on", "ends_on"):
            self.fields[name].widget.attrs.update({"min": f"{today:%Y-%m-%d}",
                                                   "max": f"{today + timedelta(days=365):%Y-%m-%d}"})
        self.image_bytes = None

    def clean_description(self):
        text = self.cleaned_data["description"].strip()
        if len(text) < 40:
            raise forms.ValidationError(_("Опишите событие чуть подробнее — хотя бы пару предложений."))
        return text

    def clean_starts_on(self):
        day = self.cleaned_data["starts_on"]
        today = timezone.localdate()
        if day < today:
            raise forms.ValidationError(_("Дата уже прошла."))
        if day > today + timedelta(days=365):
            raise forms.ValidationError(_("Принимаем события не дальше чем на год вперёд."))
        return day

    def clean_image(self):
        upload = self.cleaned_data.get("image")
        if upload:
            try:
                self.image_bytes = images.prepare(upload)
            except images.ImageError as exc:
                raise forms.ValidationError(str(exc)) from exc
        return upload

    def clean(self):
        data = super().clean()
        start, end = data.get("starts_on"), data.get("ends_on")
        if start and end:
            if end < start:
                self.add_error("ends_on", _("Последний день раньше первого."))
            elif end - start > timedelta(days=60):
                self.add_error("ends_on", _("Событие длиннее двух месяцев — это уже не афиша."))
            elif end == start:
                data["ends_on"] = None
        return data

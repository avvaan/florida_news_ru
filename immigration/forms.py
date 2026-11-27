from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Reader

CONSENT_LABEL = _("Понимаю, что это общая информация, а не юридическая консультация")


class LoginForm(forms.Form):
    email = forms.EmailField(label=_("Ваш e-mail"), widget=forms.EmailInput(attrs={
        "autocomplete": "email", "inputmode": "email", "placeholder": "name@example.com"}))
    consent = forms.BooleanField(label=CONSENT_LABEL, error_messages={"required": _("Без этого согласия помощник "
                                                                                    "недоступен.")})
    company = forms.CharField(required=False, widget=forms.TextInput(attrs={"autocomplete": "off", "tabindex": "-1"}))


class CodeForm(forms.Form):
    code = forms.CharField(label=_("Код из письма"), max_length=6, min_length=6, widget=forms.TextInput(attrs={
        "autocomplete": "one-time-code", "inputmode": "numeric", "pattern": "[0-9]{6}", "placeholder": "123456"}))


class AskForm(forms.Form):
    def __init__(self, *args, max_chars: int = 800, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["question"] = forms.CharField(
            label=_("Ваш вопрос"), min_length=8, max_length=max_chars,
            widget=forms.Textarea(attrs={"rows": 3, "maxlength": max_chars, "placeholder": _(
                "Например: что такое форма I-765 и кто её подаёт? Без имён и номеров дел.")}))


class RegionForm(forms.Form):
    region = forms.ChoiceField(label=_("Ваш регион"), choices=Reader.Region.choices)

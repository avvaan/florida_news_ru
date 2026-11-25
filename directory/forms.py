from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Category, Submission


class SubmissionForm(forms.ModelForm):
    """Заявка бизнеса в справочник. Контакт заявителя не публикуется — он нужен только редакции."""

    company = forms.CharField(required=False, widget=forms.TextInput(attrs={
        "autocomplete": "off", "tabindex": "-1",
    }))  # ловушка для ботов: поле скрыто, человек его не заполняет
    agree = forms.BooleanField(
        label=_("Подтверждаю, что представляю этот бизнес и данные верны. Согласен с правилами справочника"),
    )

    class Meta:
        model = Submission
        fields = ["category", "name", "description", "city", "address", "phone", "url", "languages", "hours",
                  "contact_name", "contact_email"]
        labels = {
            "category": _("Категория"),
            "name": _("Название бизнеса или имя специалиста"),
            "description": _("Чем вы занимаетесь"),
            "city": _("Город во Флориде"),
            "address": _("Адрес (если принимаете клиентов)"),
            "phone": _("Телефон для клиентов"),
            "url": _("Сайт или страница в соцсетях"),
            "languages": _("Языки"),
            "hours": _("Часы работы"),
            "contact_name": _("Ваше имя"),
            "contact_email": _("Ваш e-mail"),
        }
        help_texts = {
            "description": _("2–5 предложений: услуги, для кого, опыт, лицензия. Без капса и рекламных обещаний."),
            "languages": _("Например: русский, украинский, английский"),
            "contact_email": _("Сюда напишем, если будут вопросы. На сайте не публикуется."),
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5, "maxlength": 1500}),
            "name": forms.TextInput(attrs={"maxlength": 160, "autocomplete": "organization"}),
            "city": forms.TextInput(attrs={"maxlength": 80, "autocomplete": "address-level2"}),
            "address": forms.TextInput(attrs={"maxlength": 200, "autocomplete": "street-address"}),
            "phone": forms.TextInput(attrs={"maxlength": 40, "autocomplete": "tel", "inputmode": "tel"}),
            "url": forms.URLInput(attrs={"placeholder": "https://"}),
            "contact_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "contact_email": forms.EmailInput(attrs={"autocomplete": "email"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(kind=Category.Kind.BUSINESS).order_by("order", "name")
        self.fields["category"].empty_label = _("— выберите —")
        self.fields["category"].required = True
        self.fields["category"].label_from_instance = lambda category: category.loc("name")

    def clean_description(self):
        text = self.cleaned_data["description"].strip()
        if len(text) < 40:
            raise forms.ValidationError(_("Опишите бизнес чуть подробнее — хотя бы пару предложений."))
        return text

    def clean(self):
        data = super().clean()
        if not data.get("url") and not data.get("phone"):
            raise forms.ValidationError(_("Укажите телефон или сайт — иначе клиенты не смогут с вами связаться."))
        return data


class ListingUpdateForm(forms.ModelForm):
    """«Это ваш бизнес? Обновите данные» — правку смотрит редактор, сама она не публикуется."""

    company = forms.CharField(required=False, widget=forms.TextInput(attrs={"autocomplete": "off", "tabindex": "-1"}))
    agree = forms.BooleanField(label=_("Подтверждаю, что представляю этот бизнес"))

    class Meta:
        from .models import ListingUpdate

        model = ListingUpdate
        fields = ["description", "phone", "url", "address", "city", "hours", "languages", "remove", "comment",
                  "contact_name", "contact_email", "contact_phone"]
        labels = {
            "description": _("Описание"), "phone": _("Телефон для клиентов"), "url": _("Сайт или страница в соцсетях"),
            "address": _("Адрес"), "city": _("Город"), "hours": _("Часы работы"), "languages": _("Языки"),
            "remove": _("Прошу убрать бизнес из справочника"), "comment": _("Что ещё поправить (фото, категория и т. п.)"),
            "contact_name": _("Ваше имя"), "contact_email": _("Ваш e-mail"),
            "contact_phone": _("Телефон для связи с редакцией (необязательно)"),
        }
        help_texts = {
            "description": _("2–5 предложений: услуги, для кого, опыт, лицензия. Без капса и рекламных обещаний."),
            "languages": _("Например: русский, украинский, английский"),
            "contact_email": _("Ответим сюда, если будут вопросы. На сайте не публикуется."),
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5, "maxlength": 1500}),
            "comment": forms.Textarea(attrs={"rows": 3, "maxlength": 1000}),
            "url": forms.URLInput(attrs={"placeholder": "https://"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
            "contact_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "contact_email": forms.EmailInput(attrs={"autocomplete": "email"}),
        }

from django import forms

from .models import Category, Submission


class SubmissionForm(forms.ModelForm):
    """Заявка бизнеса в справочник. Контакт заявителя не публикуется — он нужен только редакции."""

    company = forms.CharField(required=False, widget=forms.TextInput(attrs={
        "autocomplete": "off", "tabindex": "-1",
    }))  # ловушка для ботов: поле скрыто, человек его не заполняет
    agree = forms.BooleanField(
        label="Подтверждаю, что представляю этот бизнес и данные верны. Согласен с правилами справочника",
    )

    class Meta:
        model = Submission
        fields = ["category", "name", "description", "city", "address", "phone", "url", "languages", "hours",
                  "contact_name", "contact_email"]
        labels = {
            "category": "Категория",
            "name": "Название бизнеса или имя специалиста",
            "description": "Чем вы занимаетесь",
            "city": "Город во Флориде",
            "address": "Адрес (если принимаете клиентов)",
            "phone": "Телефон для клиентов",
            "url": "Сайт или страница в соцсетях",
            "languages": "Языки",
            "hours": "Часы работы",
            "contact_name": "Ваше имя",
            "contact_email": "Ваш e-mail",
        }
        help_texts = {
            "description": "2–5 предложений: услуги, для кого, опыт, лицензия. Без капса и рекламных обещаний.",
            "languages": "Например: русский, украинский, английский",
            "contact_email": "Сюда напишем, если будут вопросы. На сайте не публикуется.",
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
        self.fields["category"].empty_label = "— выберите —"
        self.fields["category"].required = True

    def clean_description(self):
        text = self.cleaned_data["description"].strip()
        if len(text) < 40:
            raise forms.ValidationError("Опишите бизнес чуть подробнее — хотя бы пару предложений.")
        return text

    def clean(self):
        data = super().clean()
        if not data.get("url") and not data.get("phone"):
            raise forms.ValidationError("Укажите телефон или сайт — иначе клиенты не смогут с вами связаться.")
        return data

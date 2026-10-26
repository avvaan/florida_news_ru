"""Форма комментария с защитой от ботов без внешних сервисов.

1. Скрытое поле-ловушка: человек его не видит и не заполняет.
2. Подписанная метка формы: к какой странице относится и когда форма открыта. Поддельную метку,
   форму с чужой страницы, отправку быстрее 3 секунд и форму старше суток не принимаем.
3. Лимиты с IP и e-mail (во view) и проверка ИИ (в moderation).
"""

import re
import time

from django import forms
from django.core import signing

from .models import Comment

SALT = "comments.form"
MIN_SECONDS = 3
MAX_SECONDS = 24 * 3600
LINK_RE = re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(com|net|org|ru|io|info|biz|xyz|top|ly|me)\b", re.IGNORECASE)


def make_stamp(kind: str, pk: int, now: float | None = None) -> str:
    return signing.Signer(salt=SALT).sign(f"{kind}:{pk}:{int(now if now is not None else time.time())}")


class CommentForm(forms.ModelForm):
    stamp = forms.CharField(widget=forms.HiddenInput)
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={
        "autocomplete": "off", "tabindex": "-1",
    }))  # ловушка для ботов
    agree = forms.BooleanField(label="Согласен с правилами комментариев")

    class Meta:
        model = Comment
        fields = ["name", "email", "rating", "text"]
        labels = {"name": "Имя", "email": "E-mail", "rating": "Оценка", "text": "Комментарий"}
        help_texts = {"email": "Не публикуется. Нужен, только если редакции понадобится с вами связаться."}
        widgets = {
            "name": forms.TextInput(attrs={"maxlength": 60, "autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "rating": forms.RadioSelect(choices=[(n, str(n)) for n in range(5, 0, -1)]),
            "text": forms.Textarea(attrs={"rows": 4, "maxlength": 2000}),
        }

    def __init__(self, *args, kind: str, pk: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind, self.pk = kind, pk
        self.fields["stamp"].initial = make_stamp(kind, pk)
        if kind == "listing":
            self.fields["rating"].required = True
            self.fields["text"].label = "Отзыв"
            self.fields["text"].help_text = "Расскажите о своём опыте: что понравилось, что нет. Без оскорблений."
        else:
            del self.fields["rating"]

    def clean_stamp(self):
        try:
            kind, pk, ts = signing.Signer(salt=SALT).unsign(self.cleaned_data["stamp"]).split(":")
        except (signing.BadSignature, ValueError) as exc:
            raise forms.ValidationError("Обновите страницу и попробуйте ещё раз.") from exc
        age = time.time() - int(ts)
        if (kind, pk) != (self.kind, str(self.pk)) or age > MAX_SECONDS:
            raise forms.ValidationError("Форма устарела — обновите страницу и отправьте ещё раз.")
        if age < MIN_SECONDS:
            raise forms.ValidationError("Слишком быстро. Подождите пару секунд и отправьте ещё раз.")
        return self.cleaned_data["stamp"]

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if len(name) < 2:
            raise forms.ValidationError("Укажите имя.")
        if LINK_RE.search(name):
            raise forms.ValidationError("В имени не должно быть ссылок.")
        return name

    def clean_text(self):
        text = self.cleaned_data["text"].strip()
        if len(text) < 5:
            raise forms.ValidationError("Комментарий слишком короткий.")
        if LINK_RE.search(text):
            raise forms.ValidationError("Ссылки в комментариях не публикуем — уберите их, пожалуйста.")
        return text

    @property
    def is_bot(self) -> bool:
        return bool(self.cleaned_data.get("website"))

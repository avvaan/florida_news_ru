"""Направления врачей — фильтр «Терапевты, Детские врачи, Гинекологи…» на странице категории.

Поле Listing.specialty задаётся в админке; для записей из таблиц редакции его угадывает guess()
по специальности в названии («Elena Ivanova, MD — семейный врач (Practice)»).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Specialty(models.TextChoices):
    """Порядок — порядок кнопок на странице: сначала то, что ищут чаще всего."""

    THERAPY = "therapy", _("Терапевты и семейные врачи")
    KIDS = "kids", _("Детские врачи")
    WOMEN = "women", _("Гинекологи")
    HEART = "heart", _("Кардиологи")
    NEURO = "neuro", _("Неврологи и нейрохирурги")
    ORTHO = "ortho", _("Ортопеды и реабилитация")
    FOOT = "foot", _("Подиатры (стопа)")
    PSYCH = "psych", _("Психиатры")
    CANCER = "cancer", _("Онкологи и гематологи")
    SURGERY = "surgery", _("Хирурги")
    OTHER = "other", _("Другие специалисты")


# Первое совпадение решает: «педиатр, детский кардиолог» — детский врач, «хирург-ортопед» — ортопед.
KEYWORDS = [
    (Specialty.KIDS, ("педиатр", "детск")),
    (Specialty.WOMEN, ("гинеколог",)),
    (Specialty.CANCER, ("онколог", "гематолог")),
    (Specialty.HEART, ("кардиолог", "кардиоторакальн")),
    (Specialty.NEURO, ("невролог", "нейрохирург")),
    (Specialty.PSYCH, ("психиатр",)),
    (Specialty.FOOT, ("подиатр",)),
    (Specialty.ORTHO, ("ортопед", "спортивн", "физиатр", "физической медицины", "хиропрактик")),
    (Specialty.SURGERY, ("хирург",)),
    (Specialty.THERAPY, ("терапевт", "семейный", "гериатр")),
]


def guess(name: str) -> str:
    """Направление по названию записи: специальность — после « — ». Без неё — пусто (не угадываем)."""
    if " — " not in name:
        return ""
    text = name.split(" — ", 1)[1].lower()
    return str(next((value for value, keys in KEYWORDS if any(k in text for k in keys)), Specialty.OTHER))

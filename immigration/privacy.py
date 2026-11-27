"""Приватность: маскируем номера до сохранения и до отправки в модель, старую переписку удаляем."""

from __future__ import annotations

import re

from django.core.cache import cache
from django.utils import timezone

MASK_RECEIPT = "[номер дела скрыт]"
MASK_A_NUMBER = "[A-номер скрыт]"
MASK_SSN = "[SSN скрыт]"

# Номер дела USCIS: три буквы центра + 10 цифр (IOE0912345678, MSC2190012345, EAC…).
RECEIPT_RE = re.compile(r"\b[A-Z]{3}[-\s]?\d{10}\b", re.I)
# A-number: A + 8–9 цифр, в том числе с дефисами или пробелами (A-123-456-789, A 12345678).
A_NUMBER_RE = re.compile(r"\bA[-\s#]?(?:\d[-\s]?){7,8}\d\b", re.I)
# SSN / ITIN: 123-45-6789, 123 45 6789 или 9 цифр подряд.
SSN_RE = re.compile(r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b|\b\d{9}\b")


def mask(text: str) -> str:
    text = RECEIPT_RE.sub(MASK_RECEIPT, text or "")
    text = A_NUMBER_RE.sub(MASK_A_NUMBER, text)
    return SSN_RE.sub(MASK_SSN, text)


def purge_expired() -> int:
    """Удаляет вопросы и ответы старше срока хранения (настройка «хранить переписку, дней»)."""
    from .models import AssistantSettings, LoginCode, Question

    days = AssistantSettings.load().retention_days
    deleted, _ = Question.objects.expired(days).delete()
    LoginCode.objects.filter(created_at__lt=timezone.now() - LoginCode.LIFETIME * 4).delete()  # старые коды входа
    return deleted


def purge_expired_throttled() -> None:
    """Чистка не чаще раза в час — её можно звать на каждом вопросе."""
    if cache.add("immigration:purge", 1, timeout=3600):
        purge_expired()

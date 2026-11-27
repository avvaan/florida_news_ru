"""Вход читателей без пароля: e-mail → одноразовый код → вход.

Читатель — обычный пользователь Django без is_staff и с непригодным паролем: в админку и API сотрудников
(IsAdminUser) он не попадает. Логин читателя — «r:<e-mail>», поэтому код из письма никогда не открывает учётку
сотрудника, даже с тем же адресом.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import CONSENT_VERSION, LoginCode, Reader

READER_PREFIX = "r:"
CODES_PER_EMAIL_15MIN = 3
CODES_PER_IP_HOUR = 10


def client_ip(request) -> str:
    """Адрес читателя за Cloudflare Tunnel: CF-Connecting-IP, затем X-Forwarded-For, затем REMOTE_ADDR."""
    ip = request.META.get("HTTP_CF_CONNECTING_IP") or \
        request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")
    return ip or ""


def ip_hash(request) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"imm-login:{client_ip(request)}".encode(),
                    hashlib.sha256).hexdigest()[:32]


def code_hash(email: str, code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"{email.lower()}:{code}".encode(), hashlib.sha256).hexdigest()


def normalize(email: str) -> str:
    return (email or "").strip().lower()


def too_many_codes(email: str, request) -> bool:
    now = timezone.now()
    by_email = LoginCode.objects.filter(email=email, created_at__gte=now - timedelta(minutes=15)).count()
    by_ip = LoginCode.objects.filter(ip_hash=ip_hash(request), created_at__gte=now - timedelta(hours=1)).count()
    return by_email >= CODES_PER_EMAIL_15MIN or by_ip >= CODES_PER_IP_HOUR


def is_staff_email(email: str) -> bool:
    User = get_user_model()
    return User.objects.filter(email__iexact=email).filter(is_staff=True).exists() or \
        User.objects.filter(email__iexact=email, is_superuser=True).exists()


def send_code(email: str, request) -> None:
    code = f"{secrets.randbelow(1_000_000):06d}"
    LoginCode.objects.filter(email=email, used=False).update(used=True)  # действует только последний код
    LoginCode.objects.create(email=email, code_hash=code_hash(email, code), ip_hash=ip_hash(request))
    send_mail(
        subject=_("Код входа на TutFlorida: %(code)s") % {"code": code},
        message=_("Ваш код для входа в иммиграционный помощник TutFlorida: %(code)s\n\n"
                  "Код действует 15 минут. Если вы не запрашивали код, просто удалите это письмо.") % {"code": code},
        from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[email], fail_silently=False,
    )


def check_code(email: str, code: str) -> bool:
    login_code = LoginCode.objects.filter(email=email, used=False).order_by("-created_at").first()
    if login_code is None or not login_code.is_valid:
        return False
    login_code.attempts += 1
    ok = hmac.compare_digest(login_code.code_hash, code_hash(email, (code or "").strip()))
    login_code.used = ok or login_code.attempts >= LoginCode.MAX_ATTEMPTS
    login_code.save(update_fields=["attempts", "used"])
    return ok


def reader_for(email: str, request, consent: bool):
    """Учётка читателя по e-mail (создаётся при первом входе) + согласие с датой, версией текста и IP."""
    User = get_user_model()
    username = f"{READER_PREFIX}{email}"[:150]
    user, created = User.objects.get_or_create(username=username, defaults={"email": email})
    if created:
        user.set_unusable_password()
        user.save()
    reader, _ = Reader.objects.get_or_create(user=user)
    if consent and (not reader.has_consent or reader.consent_version != CONSENT_VERSION):
        reader.consent_at, reader.consent_version = timezone.now(), CONSENT_VERSION
        reader.consent_ip = client_ip(request) or None
        reader.save(update_fields=["consent_at", "consent_version", "consent_ip"])
    return user

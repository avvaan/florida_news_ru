"""Подсчёт просмотров. Вызывается из StatsMiddleware после ответа; ошибка подсчёта не ломает страницу."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import DailyStat, PageView, Source, VisitorKey

log = logging.getLogger(__name__)

SKIP_PREFIXES = ("/admin", "/api", "/static", "/media", "/favicon", "/__")
SKIP_PATHS = {"/robots.txt", "/sitemap.xml", "/news-sitemap.xml", "/rss/"}
BOT_RE = re.compile(
    r"bot|crawl|spider|slurp|scrap|fetch|preview|monitor|check|curl|wget|python|httpx|okhttp|java/|go-http|"
    r"headless|lighthouse|pagespeed|uptime|facebookexternalhit|whatsapp|telegrambot|vkshare|embedly|feed",
    re.I,
)
TABLET_RE = re.compile(r"ipad|tablet|kindle|silk|(android(?!.*mobile))", re.I)
MOBILE_RE = re.compile(r"mobi|iphone|ipod|android|opera mini|iemobile", re.I)


def should_count(request, response) -> bool:
    if request.method != "GET" or response.status_code != 200:
        return False
    if not response.get("Content-Type", "").startswith("text/html"):
        return False
    path = request.path
    if path in SKIP_PATHS or path.startswith(SKIP_PREFIXES):
        return False
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_staff:
        return False  # редакция не накручивает статистику
    agent = request.META.get("HTTP_USER_AGENT", "")
    if not agent or BOT_RE.search(agent):
        return False
    if request.META.get("HTTP_PURPOSE") == "prefetch" or request.META.get("HTTP_SEC_PURPOSE", "").startswith("prefetch"):
        return False
    return True


def client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")


def visitor_key(request, day) -> str:
    """Обезличенный код на один день: сам IP и браузер нигде не сохраняются."""
    secret = f"{settings.SECRET_KEY}:{day.isoformat()}".encode()
    raw = f"{client_ip(request)}|{request.META.get('HTTP_USER_AGENT', '')}".encode()
    return hmac.new(secret, raw, hashlib.sha256).hexdigest()[:32]


def device(agent: str) -> str:
    if TABLET_RE.search(agent):
        return "tablet"
    if MOBILE_RE.search(agent):
        return "mobile"
    return "desktop"


def source_of(request) -> str | None:
    """Домен внешнего сайта, «прямой заход» или None, если переход внутри сайта."""
    referer = request.META.get("HTTP_REFERER", "")
    if not referer:
        return Source.DIRECT
    host = (urlsplit(referer).hostname or "").lower().removeprefix("www.").removeprefix("m.")
    own = {h.lower().removeprefix("www.") for h in [request.get_host().split(":")[0], *settings.ALLOWED_HOSTS]}
    if not host or host in own:
        return None
    if host.startswith("google.") or ".google." in host:
        return "google"
    if host in {"t.me", "web.telegram.org", "telegram.org"}:
        return "telegram"
    if host in {"l.facebook.com", "lm.facebook.com", "facebook.com"}:
        return "facebook"
    return host[:120]


def bump(model, lookup: dict, **fields) -> bool:
    """Атомарно прибавляет счётчики; True, если строка создана."""
    updates = {name: F(name) + value for name, value in fields.items()}
    if model.objects.filter(**lookup).update(**updates):
        return False
    try:
        with transaction.atomic():
            model.objects.create(**lookup, **fields)
            return True
    except IntegrityError:  # параллельный запрос успел создать строку
        model.objects.filter(**lookup).update(**updates)
        return False


def record(request) -> None:
    day = timezone.localdate()
    agent = request.META.get("HTTP_USER_AGENT", "")
    created_day = bump(DailyStat, {"date": day}, views=1)
    if created_day:  # первый просмотр дня: старые коды посетителей больше не нужны
        VisitorKey.objects.filter(date__lt=day - timedelta(days=1)).delete()
    try:
        with transaction.atomic():
            VisitorKey.objects.create(date=day, key=visitor_key(request, day))
        new_visitor = True
    except IntegrityError:
        new_visitor = False
    if new_visitor:
        DailyStat.objects.filter(date=day).update(visitors=F("visitors") + 1, **{device(agent): F(device(agent)) + 1})
    bump(PageView, {"date": day, "path": request.path[:300]}, views=1)
    if (source := source_of(request)) is not None:
        bump(Source, {"date": day, "source": source}, visits=1)


class StatsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if should_count(request, response):
                record(request)
        except Exception as exc:  # noqa: BLE001 — статистика не должна ронять сайт
            log.warning("Статистика: %s", exc)
        return response

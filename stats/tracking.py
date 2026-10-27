"""Подсчёт просмотров по сигналу из браузера (navigator.sendBeacon → /stats/hit/).

Сервер сам просмотры больше не считает: скрипт на странице выполняют браузеры людей, а большинство
роботов, сборщиков превью и сканеров — нет. Тех, кто всё же прислал сигнал, помечаем ботами по
User-Agent и признаку автоматизации (navigator.webdriver) — не выбрасываем, а считаем отдельно.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import uuid
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.core.cache import cache
from django.urls import Resolver404, resolve
from django.utils import timezone

from .models import Hit, Source

# Не считаем: служебные адреса и наш собственный трафик.
SKIP_PREFIXES = ("/admin", "/api", "/static", "/media", "/stats", "/favicon", "/__", "/healthz", "/sitemap",
                 "/news-sitemap")
SKIP_PATHS = {"/robots.txt", "/rss/"}

# Роботы по User-Agent (без учёта регистра). Пустой UA — тоже робот. Проверка — tests/test_stats.py.
# yandex(?!search): приложение «Яндекс» (YandexSearch) — человек, а YandexBot, YandexImages — роботы.
BOT_PATTERN = (
    r"bot|crawl|spider|slurp|preview|fetch|python|curl|wget|httpclient|httpx|okhttp|go-http|java/|"
    r"headless|phantom|puppeteer|playwright|selenium|lighthouse|pagespeed|facebookexternalhit|"
    r"meta-externalagent|telegrambot|whatsapp|discordbot|slackbot|twitterbot|linkedinbot|skypeuripreview|"
    r"bingpreview|yandex(?!search)|baiduspider|petalbot|ahrefs|semrush|mj12bot|dotbot|gptbot|claudebot|ccbot|"
    r"bytespider|amazonbot|applebot|mediapartners|uptime|monitor|pingdom|statuscake|scrap|vkshare|embedly"
)
BOT_RE = re.compile(BOT_PATTERN, re.I)
TABLET_RE = re.compile(r"ipad|tablet|kindle|silk|(android(?!.*mobile))", re.I)
MOBILE_RE = re.compile(r"mobi|iphone|ipod|android|opera mini|iemobile", re.I)

RATE_LIMIT = 60  # сигналов в минуту с одного адреса

# Сайты, которые приходят под разными адресами, и метки utm_source — к одному названию.
HOST_ALIASES = {
    "l.facebook.com": "facebook", "lm.facebook.com": "facebook", "m.facebook.com": "facebook",
    "facebook.com": "facebook", "fb.com": "facebook", "com.facebook.katana": "facebook",
    "l.threads.com": "threads", "l.threads.net": "threads", "threads.com": "threads", "threads.net": "threads",
    "t.co": "x", "x.com": "x", "twitter.com": "x",
    "t.me": "telegram", "web.telegram.org": "telegram", "telegram.org": "telegram",
    "org.telegram.messenger": "telegram", "org.telegram.messenger.web": "telegram",
    "wa.me": "whatsapp", "web.whatsapp.com": "whatsapp", "com.whatsapp": "whatsapp",
    "l.instagram.com": "instagram", "instagram.com": "instagram", "com.instagram.android": "instagram",
    "vk.com": "vk", "m.vk.com": "vk", "ok.ru": "ok",
    "bing.com": "bing", "duckduckgo.com": "duckduckgo",
    "com.google.android.googlequicksearchbox": "google", "com.google.android.gm": "gmail",
    "mail.google.com": "gmail",
}
UTM_ALIASES = {"tg": "telegram", "wa": "whatsapp", "fb": "facebook", "ig": "instagram", "twitter": "x"}
SOURCE_NAMES = {
    Source.DIRECT: "прямой заход", "google": "Google", "telegram": "Telegram", "facebook": "Facebook",
    "threads": "Threads", "x": "X (Twitter)", "whatsapp": "WhatsApp", "instagram": "Instagram", "vk": "ВКонтакте",
    "ok": "Одноклассники", "yandex": "Яндекс", "bing": "Bing", "duckduckgo": "DuckDuckGo", "gmail": "Gmail",
}


def bot_reason(agent: str, automation: bool = False) -> str:
    """Почему это робот, или "" для человека."""
    if automation:
        return "webdriver"
    if not agent.strip():
        return "пустой UA"
    if match := BOT_RE.search(agent):
        return f"UA: {match.group(0).lower()}"
    return ""


def device(agent: str) -> str:
    if TABLET_RE.search(agent):
        return "tablet"
    if MOBILE_RE.search(agent):
        return "mobile"
    return "desktop"


def client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")


def own_hosts(request=None) -> set[str]:
    hosts = [urlsplit(settings.SITE_URL).hostname or "", *settings.ALLOWED_HOSTS]
    if request is not None:
        hosts.append(request.get_host().split(":")[0])
    return {h.lower().lstrip(".").removeprefix("www.") for h in hosts if h and h != "*"}


def is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def canonical_host(host: str) -> str:
    """Домен → название источника: google.ru → google, l.facebook.com → facebook; IP-адрес → прямой заход."""
    host = host.lower().strip().removeprefix("www.")
    if not host or is_ip(host):
        return Source.DIRECT
    if host in HOST_ALIASES:
        return HOST_ALIASES[host]
    if host.startswith("google.") or ".google." in host:
        return "google"
    if host.startswith("yandex.") or host == "ya.ru":
        return "yandex"
    return host[:120]


def referrer_origin(referrer: str) -> str:
    """Из адреса, с которого пришли, оставляем только схему и домен — путь и запрос не храним."""
    try:
        parts = urlsplit(referrer.strip())
    except ValueError:
        return ""
    if not parts.scheme or not parts.hostname:
        return ""
    return f"{parts.scheme}://{parts.hostname}"[:200]


def normalize_source(referrer: str, utm_source: str, hosts: set[str]) -> str:
    """Источник входа на сайт. "" — переход внутри сайта (не вход).

    Метка utm_source важнее адреса, с которого пришли. Пустой адрес, IP-адрес — «прямой заход».
    """
    if utm := utm_source.strip().lower():
        return UTM_ALIASES.get(utm, utm)[:60]
    host = (urlsplit(referrer).hostname or "").lower().removeprefix("www.") if referrer else ""
    if not host:
        return Source.DIRECT
    if host in hosts:
        return ""
    return canonical_host(host)


def source_name(source: str) -> str:
    return SOURCE_NAMES.get(source, source)


def skip_path(path: str) -> bool:
    if not path.startswith("/") or path in SKIP_PATHS or path.startswith(SKIP_PREFIXES):
        return True
    try:
        resolve(path)
    except Resolver404:
        return True  # чужие и выдуманные адреса в «Популярные страницы» не пускаем
    return False


def visitor_code(day, visitor: str, request) -> str:
    """Обезличенный код посетителя на один день: случайный код из браузера (или IP + браузер, если
    localStorage недоступен) через HMAC с секретом и датой. Меняется каждые сутки, исходник не храним."""
    try:
        raw = f"v|{uuid.UUID(visitor)}"
    except (ValueError, AttributeError, TypeError):
        raw = f"ip|{client_ip(request)}|{request.META.get('HTTP_USER_AGENT', '')}"
    secret = f"{settings.SECRET_KEY}:{day.isoformat()}".encode()
    return hmac.new(secret, raw.encode(), hashlib.sha256).hexdigest()[:32]


def rate_limited(request) -> bool:
    """Не больше RATE_LIMIT сигналов в минуту с одного адреса. IP в кэше — только как хэш."""
    ip_hash = hashlib.sha256(f"{settings.SECRET_KEY}|{client_ip(request)}".encode()).hexdigest()[:16]
    key = f"stats-hit:{ip_hash}:{int(timezone.now().timestamp() // 60)}"
    cache.add(key, 0, 90)
    try:
        return cache.incr(key) > RATE_LIMIT
    except ValueError:  # ключ успел истечь
        return False


def record_hit(request, data: dict) -> Hit | None:
    """Сохраняет просмотр из сигнала браузера. None — не считаем (служебная страница, чужой адрес)."""
    url = urlsplit(str(data.get("p", ""))[:1000])
    path = url.path[:300]
    if url.scheme or url.netloc or skip_path(path):  # скрипт шлёт только путь — полный адрес подделан
        return None
    utm = {k: v[0] for k, v in parse_qs(url.query).items() if k.startswith("utm_") and v}
    referrer = str(data.get("r", ""))[:1000]
    agent = request.META.get("HTTP_USER_AGENT", "")
    automation = data.get("d") is True
    reason = bot_reason(agent, automation)
    try:
        width = max(0, min(int(data.get("w") or 0), 20000)) or None
    except (TypeError, ValueError):
        width = None
    day = timezone.localdate()
    return Hit.objects.create(
        date=day,
        path=path,
        visitor=visitor_code(day, str(data.get("v", "")), request),
        source=normalize_source(referrer, utm.get("utm_source", ""), own_hosts(request)),
        referrer=referrer_origin(referrer),
        utm_source=utm.get("utm_source", "")[:60],
        utm_medium=utm.get("utm_medium", "")[:60],
        utm_campaign=utm.get("utm_campaign", "")[:100],
        device=device(agent),
        screen_width=width,
        agent=agent[:300],
        automation=automation,
        is_bot=bool(reason),
        bot_reason=reason,
    )


def reclassify(hit: Hit, hosts: set[str]) -> bool:
    """Заново применяет правила к сохранённому просмотру. True, если что-то поменялось."""
    reason = bot_reason(hit.agent, hit.automation)
    source = normalize_source(hit.referrer, hit.utm_source, hosts)
    if (hit.is_bot, hit.bot_reason, hit.source) == (bool(reason), reason, source):
        return False
    hit.is_bot, hit.bot_reason, hit.source = bool(reason), reason, source
    return True

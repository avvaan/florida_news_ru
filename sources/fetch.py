"""Сбор фидов: RSS/Atom и NWS alerts API.

- честный User-Agent, уважение robots.txt;
- условные запросы по ETag / Last-Modified;
- ошибки одного источника не роняют весь сбор;
- повторный запуск не создаёт дублей (уникальность source+guid).
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_timezone
from urllib import robotparser
from urllib.parse import urlsplit

import feedparser
import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import SiteSettings

from .models import FeedItem, Source, WeatherAlert
from .weather import SEVERE_EVENTS, translate_event

log = logging.getLogger(__name__)

SUMMARY_MAX_CHARS = 1000


@dataclass
class FetchResult:
    source: Source
    created: int = 0
    skipped: int = 0
    not_modified: bool = False
    error: str = ""
    alerts: int = 0
    new_items: list[FeedItem] = field(default_factory=list)


class RobotsCache:
    def __init__(self, session: requests.Session):
        self.session = session
        self._parsers: dict[str, robotparser.RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._parsers:
            self._parsers[origin] = self._load(origin)
        parser = self._parsers[origin]
        if parser is None:
            return True  # robots.txt недоступен — по стандарту можно
        return parser.can_fetch(settings.FETCH_USER_AGENT, url)

    def _load(self, origin: str):
        try:
            resp = self.session.get(f"{origin}/robots.txt", timeout=settings.FETCH_TIMEOUT)
        except requests.RequestException:
            return None
        if resp.status_code >= 400:
            return None
        parser = robotparser.RobotFileParser()
        parser.parse(resp.text.splitlines())
        return parser


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": settings.FETCH_USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, application/geo+json;q=0.9, */*;q=0.5",
    })
    return session


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(value: str, limit: int = SUMMARY_MAX_CHARS) -> str:
    """Убирает HTML и лишние пробелы, обрезает до limit символов по слову."""
    text = html.unescape(_TAG_RE.sub(" ", value or ""))
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def _entry_datetime(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=dt_timezone.utc)
    return None


def parse_feed(content: bytes) -> list[dict]:
    """Разбирает RSS/Atom и возвращает нормализованные записи."""
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"не похоже на RSS/Atom: {parsed.get('bozo_exception')!r}")
    if not parsed.get("version") and not parsed.entries:
        raise ValueError("не похоже на RSS/Atom: пустой документ")
    items = []
    for entry in parsed.entries:
        link = entry.get("link") or ""
        title = clean_text(entry.get("title", ""), limit=400)
        if not link or not title:
            continue
        guid = (entry.get("id") or entry.get("guid") or link)[:500]
        summary = entry.get("summary") or entry.get("description") or ""
        items.append({
            "guid": guid,
            "url": link[:1000],
            "title": title,
            "summary": clean_text(summary),
            "published_at": _entry_datetime(entry),
        })
    return items


def looks_like_feed(content: bytes) -> bool:
    head = content[:2000].lower()
    return any(marker in head for marker in (b"<rss", b"<feed", b"<rdf", b"<channel"))


def store_items(source: Source, items: list[dict], limit: int) -> FetchResult:
    result = FetchResult(source=source)
    for data in items[:limit]:
        if FeedItem.objects.filter(source=source, guid=data["guid"]).exists():
            result.skipped += 1
            continue
        try:
            with transaction.atomic():
                item = FeedItem.objects.create(source=source, **data)
        except IntegrityError:
            result.skipped += 1
            continue
        result.created += 1
        result.new_items.append(item)
    return result


def fetch_source(source: Source, session: requests.Session | None = None,
                 robots: RobotsCache | None = None) -> FetchResult:
    session = session or make_session()
    robots = robots or RobotsCache(session)
    try:
        if not robots.allowed(source.url):
            raise PermissionError("robots.txt запрещает этот адрес")
        if source.kind == Source.Kind.NWS_ALERTS:
            result = _fetch_nws(source, session)
        else:
            result = _fetch_rss(source, session)
    except Exception as exc:  # noqa: BLE001 — один источник не должен ронять сбор
        log.warning("Источник %s: %s", source.name, exc)
        source.record_failure(f"{type(exc).__name__}: {exc}")
        return FetchResult(source=source, error=str(exc))
    source.record_success()
    return result


def _fetch_rss(source: Source, session: requests.Session) -> FetchResult:
    headers = {}
    if source.etag:
        headers["If-None-Match"] = source.etag
    if source.last_modified:
        headers["If-Modified-Since"] = source.last_modified
    resp = session.get(source.url, headers=headers, timeout=settings.FETCH_TIMEOUT)
    if resp.status_code == 304:
        return FetchResult(source=source, not_modified=True)
    resp.raise_for_status()
    items = parse_feed(resp.content)
    source.etag = resp.headers.get("ETag", "")[:300]
    source.last_modified = resp.headers.get("Last-Modified", "")[:100]
    limit = SiteSettings.load().max_items_per_source
    return store_items(source, items, limit)


def _fetch_nws(source: Source, session: requests.Session) -> FetchResult:
    """NWS отдаёт GeoJSON. Все алерты — в блок погоды, опасные — ещё и в конвейер."""
    resp = session.get(source.url, timeout=settings.FETCH_TIMEOUT, headers={"Accept": "application/geo+json"})
    resp.raise_for_status()
    features = resp.json().get("features", [])
    return sync_nws_alerts(source, features)


def sync_nws_alerts(source: Source, features: list[dict]) -> FetchResult:
    result = FetchResult(source=source)
    seen = set()
    severe_items = []
    for feature in features:
        props = feature.get("properties") or {}
        ext_id = (props.get("id") or feature.get("id") or "")[:300]
        if not ext_id:
            continue
        seen.add(ext_id)
        event = props.get("event") or ""
        alert, _ = WeatherAlert.objects.update_or_create(
            external_id=ext_id,
            defaults={
                "source": source,
                "event": event[:120],
                "event_ru": translate_event(event),
                "headline": (props.get("headline") or "")[:500],
                "area": props.get("areaDesc") or "",
                "severity": props.get("severity") or WeatherAlert.Severity.UNKNOWN,
                "url": (props.get("@id") or feature.get("id") or "")[:1000],
                "effective": _parse_dt(props.get("effective") or props.get("onset")),
                "expires": _parse_dt(props.get("ends") or props.get("expires")),
                "is_active": True,
            },
        )
        result.alerts += 1
        if event in SEVERE_EVENTS:
            severe_items.append({
                "guid": ext_id,
                "url": alert.url or source.homepage or source.url,
                "title": clean_text(props.get("headline") or event, limit=400),
                "summary": clean_text(
                    f"{props.get('areaDesc', '')}. {props.get('description', '')} "
                    f"{props.get('instruction') or ''}"
                ),
                "published_at": alert.effective,
            })
    WeatherAlert.objects.filter(source=source, is_active=True).exclude(external_id__in=seen).update(is_active=False)
    stored = store_items(source, severe_items, limit=50)
    result.created, result.skipped, result.new_items = stored.created, stored.skipped, stored.new_items
    return result


def _parse_dt(value: str | None):
    if not value:
        return None
    dt = parse_datetime(value)
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, dt_timezone.utc)
    return dt


def expire_weather_alerts():
    """Гасит предупреждения с истёкшим сроком (на случай, если фид упал)."""
    return WeatherAlert.objects.filter(is_active=True, expires__lt=timezone.now()).update(is_active=False)


def fetch_all(sources=None, include_broken: bool = False) -> list[FetchResult]:
    qs = sources if sources is not None else Source.objects.filter(is_active=True)
    if not include_broken:
        qs = qs.filter(is_broken=False)
    session = make_session()
    robots = RobotsCache(session)
    results = [fetch_source(source, session, robots) for source in qs]
    expire_weather_alerts()
    return results


def check_source(source: Source, session: requests.Session | None = None) -> tuple[bool, str]:
    """Проверяет, что адрес реально отдаёт RSS/Atom (или GeoJSON для NWS)."""
    session = session or make_session()
    try:
        resp = session.get(source.url, timeout=settings.FETCH_TIMEOUT)
        resp.raise_for_status()
        if source.kind == Source.Kind.NWS_ALERTS:
            data = resp.json()
            ok = isinstance(data.get("features"), list)
            detail = f"GeoJSON, предупреждений: {len(data.get('features', []))}" if ok else "нет features"
        else:
            if not looks_like_feed(resp.content):
                return False, f"HTTP {resp.status_code}, но это не RSS/Atom ({resp.headers.get('Content-Type')})"
            items = parse_feed(resp.content)
            ok = bool(items)
            detail = f"записей: {len(items)}; первая: {items[0]['title'][:80]}" if ok else "фид пустой"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"[:500]
    return ok, detail

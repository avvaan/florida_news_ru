"""Сборщики сигналов: Perplexity (поиск по сети), Grok (поиск по X), публичные Telegram-каналы.

Сигнал — подсказка «об этом говорят», а не факт. Текст храним коротким и только для
сопоставления с сюжетами: на сайт он не попадает и автору заметок не передаётся.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from core.models import SiteSettings
from pipeline.ai import estimate_cost
from pipeline.budget import current_budget
from pipeline.models import AICall

from .models import Signal, SignalSource

log = logging.getLogger(__name__)

MAX_TEXT = 500
TELEGRAM_MAX_AGE = timedelta(hours=24)


class CollectorError(RuntimeError):
    pass


@dataclass
class Item:
    url: str
    text: str
    author: str = ""
    published_at: datetime | None = None


# --- Бюджет ------------------------------------------------------------------

def budget_allows_signals() -> bool:
    """Сигналы останавливаются раньше заметок: им достаётся только часть дневного бюджета."""
    budget = current_budget()
    return budget.spent_today < budget.budget * Decimal(str(settings.SIGNALS_BUDGET_SHARE))


# --- Общие для Perplexity и Grok ---------------------------------------------

SEARCH_INSTRUCTIONS = """\
Ты помогаешь редакции русскоязычного сайта о Флориде понять, о чём сейчас говорят. Найди свежие \
новости и обсуждения по запросу. Верни только JSON без пояснений и без markdown:
{"items": [{"url": "...", "title": "...", "summary": "...", "author": "...", "published": "..."}]}
url — ссылка на первоисточник из результатов поиска (только настоящие ссылки), title — суть \
в одну строку, summary — 1–2 предложения своими словами, без цитат, author — издание или автор, \
published — дата и время в ISO 8601, если известны, иначе пустая строка. Не больше 10 пунктов."""

X_INSTRUCTIONS = """\
Ты помогаешь редакции русскоязычного сайта о Флориде понять, что обсуждают в X (Twitter). Найди \
свежие посты по запросу: в первую очередь официальные аккаунты, местные СМИ и журналистов. Верни \
только JSON без пояснений и без markdown:
{"items": [{"url": "...", "title": "...", "summary": "...", "author": "...", "published": "..."}]}
url — ссылка на пост в X, title — суть в одну строку, summary — о чём пост, 1–2 предложения \
своими словами, без цитат, author — @имя автора, published — время поста в ISO 8601. \
Не больше 10 пунктов."""


def post_json(url: str, api_key: str, body: dict, timeout: float = 180) -> dict:
    response = requests.post(url, json=body, timeout=timeout,
                             headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    if response.status_code >= 400:
        raise CollectorError(f"HTTP {response.status_code}: {response.text[:300]}")
    return response.json()


def response_text(data: dict) -> str:
    if data.get("output_text"):
        return data["output_text"]
    parts = []
    for item in data.get("output") or []:
        if item.get("type") == "message":
            for block in item.get("content") or []:
                if block.get("type") in ("output_text", "text"):
                    parts.append(block.get("text") or "")
    return "\n".join(parts)


def response_links(data: dict) -> list[dict]:
    """Ссылки из ответа: результаты поиска, цитаты в тексте и общий список citations."""
    links: list[dict] = []
    for item in data.get("output") or []:
        if item.get("type") == "search_results":
            links += [r for r in item.get("results") or [] if isinstance(r, dict)]
        if item.get("type") == "message":
            for block in item.get("content") or []:
                for note in block.get("annotations") or []:
                    if note.get("type") == "url_citation":
                        links.append({"url": note.get("url"), "title": note.get("title", "")})
    for key in ("search_results", "citations"):
        for entry in data.get(key) or []:
            links.append(entry if isinstance(entry, dict) else {"url": entry})
    seen, unique = set(), []
    for link in links:
        if link.get("url") and link["url"] not in seen:
            seen.add(link["url"])
            unique.append(link)
    return unique


def parse_items(text: str) -> list[dict]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        items = json.loads(text[start:end + 1]).get("items") or []
    except (json.JSONDecodeError, AttributeError):
        return []
    return [i for i in items if isinstance(i, dict)]


def parse_when(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    when = parse_datetime(value)
    if when is None and (day := parse_date(value)):
        when = datetime(day.year, day.month, day.day)
    if when is not None and timezone.is_naive(when):
        when = timezone.make_aware(when, timezone.get_current_timezone())
    return when


def author_from_x_url(url: str) -> str:
    match = re.match(r"https?://(?:www\.)?(?:x|twitter)\.com/([^/]+)/status/", url)
    return f"@{match.group(1)}" if match else ""


def to_items(data: dict, *, x_posts: bool = False) -> list[Item]:
    """JSON-список из текста ответа; если модель его не дала — результаты поиска."""
    items = []
    for raw in parse_items(response_text(data)):
        url = (raw.get("url") or "").strip()
        if not url.startswith("http"):
            continue
        text = " — ".join(p for p in (raw.get("title"), raw.get("summary")) if p)
        items.append(Item(url=url, text=text[:MAX_TEXT], author=(raw.get("author") or "")[:200],
                          published_at=parse_when(raw.get("published"))))
    if not items:
        for link in response_links(data):
            text = " — ".join(p for p in (link.get("title"), link.get("snippet")) if p)
            items.append(Item(url=link["url"], text=(text or link["url"])[:MAX_TEXT],
                              author=author_from_x_url(link["url"]) if x_posts else "",
                              published_at=parse_when(link.get("date"))))
    for item in items:
        if x_posts and not item.author:
            item.author = author_from_x_url(item.url)
    return items


def log_call(model: str, data: dict | None, error: str = "") -> AICall:
    usage = (data or {}).get("usage") or {}
    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens") or 0
    return AICall.objects.create(
        purpose=AICall.Purpose.SIGNALS, model=model, input_tokens=input_tokens, output_tokens=output_tokens,
        # Без ответа (сеть, HTTP-ошибка) запрос не считаем платным.
        cost_usd=estimate_cost(model, input_tokens, output_tokens) if data is not None else 0,
        success=not error, error=error[:1000],
    )


def search(*, api_url: str, api_key: str, model: str, instructions: str, query: str, tool: dict,
           key_name: str, x_posts: bool = False) -> list[Item]:
    if not api_key:
        raise CollectorError(f"{key_name} не задан")
    body = {
        "model": model,
        "input": [{"role": "system", "content": instructions}, {"role": "user", "content": query}],
        "tools": [tool],
        "max_output_tokens": 3000,
    }
    try:
        data = post_json(api_url, api_key, body)
    except (requests.RequestException, ValueError, CollectorError) as exc:
        log_call(model, None, str(exc))
        raise CollectorError(str(exc)) from exc
    if data.get("status") in ("failed", "cancelled"):
        error = json.dumps(data.get("error") or data.get("status"), ensure_ascii=False)
        log_call(model, data, error)
        raise CollectorError(f"Ответ со статусом {data['status']}: {error[:300]}")
    log_call(model, data)
    return to_items(data, x_posts=x_posts)


def search_perplexity(query: str) -> list[Item]:
    return search(api_url=settings.PERPLEXITY_API_URL, api_key=settings.PERPLEXITY_API_KEY,
                  model=settings.PERPLEXITY_MODEL, instructions=SEARCH_INSTRUCTIONS, query=query,
                  tool={"type": "web_search"}, key_name="PERPLEXITY_API_KEY")


def search_grok(query: str) -> list[Item]:
    today = timezone.localdate()
    tool = {"type": "x_search", "from_date": (today - timedelta(days=1)).isoformat(), "to_date": today.isoformat()}
    return search(api_url=settings.XAI_API_URL, api_key=settings.XAI_API_KEY, model=settings.XAI_MODEL,
                  instructions=X_INSTRUCTIONS, query=query, tool=tool, key_name="XAI_API_KEY", x_posts=True)


# --- Сохранение --------------------------------------------------------------

def store(source: SignalSource, items: list[Item], limit: int) -> int:
    created = 0
    for item in items[:limit]:
        _, is_new = Signal.objects.get_or_create(url=item.url[:1000], defaults={
            "source": source, "text": item.text[:MAX_TEXT], "author": item.author[:200],
            "published_at": item.published_at, "region": source.region,
        })
        created += is_new
    return created


def collect_search(kind: str, say) -> dict:
    """Все активные запросы одного вида (Perplexity или Grok)."""
    searcher = {SignalSource.Kind.PERPLEXITY: search_perplexity, SignalSource.Kind.GROK: search_grok}[kind]
    limit = SiteSettings.load().signals_max_per_source
    stats = {"created": 0, "failed": 0}
    for source in SignalSource.objects.filter(kind=kind, is_active=True):
        if not budget_allows_signals():
            say("Сигналы: потрачена доля дневного бюджета для соцсетей — дальше не собираем")
            break
        try:
            items = searcher(source.query)
        except CollectorError as exc:
            source.record_failure(str(exc))
            stats["failed"] += 1
            say(f"Сигналы, {source}: ошибка — {str(exc)[:200]}")
            continue
        source.record_success()
        stats["created"] += store(source, items, limit)
    return stats


# --- Telegram ----------------------------------------------------------------

@dataclass
class TgPost:
    id: int
    url: str
    text: str
    author: str
    date: datetime


def channel_username(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^(https?://)?(t\.me|telegram\.me)/(s/)?", "", value)
    return value.lstrip("@").split("/")[0]


def is_public_channel(entity) -> bool:
    """Только открытые каналы-трансляции: не группы, не чаты, не пользователи."""
    return (bool(getattr(entity, "broadcast", False)) and not getattr(entity, "megagroup", False)
            and bool(getattr(entity, "username", None)))


async def read_channel(client, username: str, min_id: int, limit: int) -> list[TgPost]:
    entity = await client.get_entity(username)
    if not is_public_channel(entity):
        raise CollectorError("это не публичный канал: читаем только открытые каналы, без чатов и групп")
    since = timezone.now() - TELEGRAM_MAX_AGE
    posts = []
    async for message in client.iter_messages(entity, limit=limit, min_id=min_id):
        text = (getattr(message, "message", "") or "").strip()
        if not text or (message.date and message.date < since):
            continue
        posts.append(TgPost(id=message.id, url=f"https://t.me/{entity.username}/{message.id}",
                            text=text[:MAX_TEXT], author=getattr(entity, "title", "") or f"@{entity.username}",
                            date=message.date))
    return posts


def make_telegram_client():
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    if not (settings.TG_API_ID and settings.TG_API_HASH):
        raise CollectorError("TG_API_ID и TG_API_HASH не заданы")
    if not settings.TG_SESSION:
        raise CollectorError("TG_SESSION не задан — выполните python manage.py telegram_login")
    return TelegramClient(StringSession(settings.TG_SESSION), int(settings.TG_API_ID), settings.TG_API_HASH)


async def read_channels(jobs: list[tuple[int, str, int]], limit: int) -> dict[int, list[TgPost] | Exception]:
    """Сеть — отдельно от базы: ORM Django нельзя звать внутри цикла asyncio."""
    client = make_telegram_client()
    results: dict[int, list[TgPost] | Exception] = {}
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise CollectorError("сессия Telegram недействительна — выполните python manage.py telegram_login")
        for source_id, username, min_id in jobs:
            try:
                results[source_id] = await read_channel(client, username, min_id, limit)
            except Exception as exc:  # noqa: BLE001 — ошибка одного канала не мешает остальным
                results[source_id] = exc
    finally:
        await client.disconnect()
    return results


def collect_telegram(say) -> dict:
    stats = {"created": 0, "failed": 0}
    sources = {s.pk: s for s in SignalSource.objects.filter(kind=SignalSource.Kind.TELEGRAM, is_active=True)}
    if not sources:
        return stats
    limit = SiteSettings.load().signals_max_per_source
    jobs = [(pk, channel_username(s.query), s.last_message_id) for pk, s in sources.items()]
    try:
        results = asyncio.run(read_channels(jobs, limit))
    except Exception as exc:  # noqa: BLE001
        say(f"Сигналы, Telegram: ошибка — {str(exc)[:200]}")
        stats["failed"] = len(sources)
        return stats
    for pk, result in results.items():
        source = sources[pk]
        if isinstance(result, Exception):
            source.record_failure(str(result))
            stats["failed"] += 1
            say(f"Сигналы, {source}: ошибка — {str(result)[:200]}")
            continue
        items = [Item(url=p.url, text=p.text, author=p.author, published_at=p.date) for p in result]
        stats["created"] += store(source, items, limit)
        source.last_message_id = max([source.last_message_id, *(p.id for p in result)])
        source.record_success()
    return stats

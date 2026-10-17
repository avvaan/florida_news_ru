"""Публикация в Telegram-канал через Bot API (бот — администратор канала)."""

from __future__ import annotations

import html
import logging

import requests
from django.conf import settings
from django.utils import timezone

from core.models import SiteSettings

log = logging.getLogger(__name__)

TELEGRAM_LIMIT = 1024


def article_url(article) -> str:
    return f"{settings.SITE_URL}{article.get_absolute_url()}"


def build_post(article) -> str:
    """Текст поста: заголовок, анонс, ссылка на сайт. HTML-разметка Telegram."""
    prefix = "🚨 " if article.is_urgent else ""
    region = f"📍 {article.region.name}\n" if article.region and not article.region.is_statewide else ""
    text = (
        f"{prefix}<b>{html.escape(article.title)}</b>\n\n"
        f"{html.escape(article.teaser)}\n\n"
        f"{region}"
        f'<a href="{html.escape(article_url(article), quote=True)}">Читать на сайте →</a>'
    )
    return text[:TELEGRAM_LIMIT]


def telegram_ready() -> bool:
    return bool(
        settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHANNEL_ID and SiteSettings.load().telegram_enabled
    )


def post_article(article, *, force_dry_run: bool = False) -> str:
    """Отправляет пост. Пока Telegram выключен в настройках — только пишет в лог.

    Возвращает краткое описание результата.
    """
    if article.telegram_posted_at:
        return "уже отправлено"
    text = build_post(article)
    if force_dry_run or not telegram_ready():
        log.info("[Telegram dry-run] %s", text.replace("\n", " | "))
        return "dry-run"
    resp = requests.post(
        f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": settings.TELEGRAM_CHANNEL_ID,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": False},
        },
        timeout=20,
    )
    data = resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else {}
    if not data.get("ok"):
        raise RuntimeError(f"Telegram: {data.get('description') or resp.status_code}")
    article.telegram_message_id = data["result"]["message_id"]
    article.telegram_posted_at = timezone.now()
    article.save(update_fields=["telegram_message_id", "telegram_posted_at"])
    return "отправлено"

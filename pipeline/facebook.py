"""Публикация заметок на страницу Facebook через Graph API.

Нужны два значения в окружении: FACEBOOK_PAGE_ID (числовой id страницы) и FACEBOOK_PAGE_TOKEN —
бессрочный токен страницы с правом pages_manage_posts (как получить — README, «Facebook»).
Пока хотя бы одного нет, посты только пишутся в лог («dry-run»), как у Telegram.

Пост — заголовок и анонс, ссылка на заметку идёт отдельным полем link: Facebook сам строит
карточку с обложкой и заголовком из og-разметки страницы.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.utils import timezone

from .telegram import article_url

log = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v27.0"  # версия по умолчанию у приложения «TutFlorida Autopost»


def facebook_ready() -> bool:
    return bool(settings.FACEBOOK_PAGE_ID and settings.FACEBOOK_PAGE_TOKEN)


def build_message(article) -> str:
    prefix = "🚨 " if article.is_urgent else ""
    region = f"\n\n📍 {article.region.name}" if article.region and not article.region.is_statewide else ""
    return f"{prefix}{article.title}\n\n{article.teaser}{region}".strip()


def post_article(article, *, force_dry_run: bool = False) -> str:
    """Отправляет пост о заметке — только опубликованной и только один раз."""
    if article.status != "published":
        return "не опубликовано — не отправляем"
    if article.facebook_posted_at:
        return "уже отправлено"
    message, link = build_message(article), article_url(article)
    if force_dry_run or not facebook_ready():
        log.info("[Facebook dry-run] %s | %s", message.replace("\n", " | "), link)
        return "dry-run"
    resp = requests.post(
        f"{GRAPH_URL}/{settings.FACEBOOK_PAGE_ID}/feed",
        data={"message": message, "link": link, "access_token": settings.FACEBOOK_PAGE_TOKEN},
        timeout=20,
    )
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if not resp.ok or "id" not in data:
        error = (data.get("error") or {}).get("message") or resp.status_code
        raise RuntimeError(f"Facebook: {error}")
    article.facebook_post_id = data["id"]
    article.facebook_posted_at = timezone.now()
    article.save(update_fields=["facebook_post_id", "facebook_posted_at"])
    return "отправлено"

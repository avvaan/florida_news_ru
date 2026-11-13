"""Текст статьи-первоисточника для автора и фактчекера.

В RSS есть только заголовок и анонс до 1000 знаков — из этого не написать развёрнутую заметку без
домыслов. Поэтому перед написанием мы читаем саму статью (с уважением к robots.txt) и передаём её
текст ИИ как материал для фактов. Текст нигде не хранится и не публикуется: на сайте — только
наша заметка своими словами и ссылка на первоисточник.
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser

import requests
from django.conf import settings

from .fetch import RobotsCache, make_session
from .models import Source

log = logging.getLogger(__name__)

MAX_CHARS = 8000  # на источник: хватает на факты, не раздувает расходы на ИИ
MIN_PARAGRAPH_CHARS = 40  # короче — подписи, кнопки, «Читайте также»
SKIP_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "figure", "button", "svg"}
_WS_RE = re.compile(r"\s+")


class _Paragraphs(HTMLParser):
    """Собирает текст абзацев <p> и <li> вне меню, подвала, скриптов и врезок."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.current: list[str] | None = None
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip_depth += 1
        elif tag in ("p", "li") and not self.skip_depth:
            self._flush()
            self.current = []

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif tag in ("p", "li"):
            self._flush()

    def handle_data(self, data):
        if self.current is not None and not self.skip_depth:
            self.current.append(data)

    def _flush(self):
        if self.current is not None:
            text = _WS_RE.sub(" ", "".join(self.current)).strip()
            if len(text) >= MIN_PARAGRAPH_CHARS and text not in self.paragraphs:
                self.paragraphs.append(text)
        self.current = None


def extract_text(html: str, limit: int = MAX_CHARS) -> str:
    parser = _Paragraphs()
    parser.feed(html)
    parser.close()
    text = "\n\n".join(parser.paragraphs)
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def fetch_article_text(url: str, session: requests.Session | None = None,
                       robots: RobotsCache | None = None) -> str:
    """Текст статьи по ссылке или "" (запрещено robots.txt, ошибка сети, не HTML)."""
    session = session or make_session()
    robots = robots or RobotsCache(session)
    try:
        if not robots.allowed(url):
            return ""
        resp = session.get(url, headers={"Accept": "text/html,application/xhtml+xml"},
                           timeout=settings.FETCH_TIMEOUT)
        resp.raise_for_status()
        if "html" not in resp.headers.get("Content-Type", "text/html").lower():
            return ""
        return extract_text(resp.text)
    except Exception as exc:  # noqa: BLE001 — без полного текста заметка пишется по анонсу
        log.info("Текст статьи %s: %s", url, exc)
        return ""


def full_texts(items, max_sources: int = 2) -> dict[int, str]:
    """Полные тексты для записей сюжета: {id записи: текст}. Telegram и NWS — анонс уже полный."""
    session = make_session()
    robots = RobotsCache(session)
    texts: dict[int, str] = {}
    for item in items:
        if len(texts) >= max_sources:
            break
        if item.source.kind != Source.Kind.RSS or not item.url.startswith(("http://", "https://")):
            continue
        if text := fetch_article_text(item.url, session, robots):
            texts[item.pk] = text
    return texts

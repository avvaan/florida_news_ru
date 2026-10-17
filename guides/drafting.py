"""Черновик гайда по официальным источникам: факты собирает Perplexity, текст пишет ИИ-автор, проверка
сверяет текст с фактами. Результат — всегда черновик: публикует только редактор вручную."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone

from pipeline import ai
from pipeline.budget import current_budget
from pipeline.models import AICall
from pipeline.prompts import AUDIENCE
from social.collectors import CollectorError, response_text, search_raw

from .models import Guide, GuideSource
from .schemas import GuideCheck, GuideDraft

# Если у гайда не указаны свои официальные сайты.
DEFAULT_DOMAINS = ["myflorida.com", "flhsmv.gov", "floridadisaster.org", "myfloridacfo.com", "floridarevenue.com",
                   "fldoe.org", "fdot.gov", "floir.com"]

FACTS_INSTRUCTIONS = """\
Ты собираешь факты для справочной статьи на русском о жизни во Флориде. Ищи ТОЛЬКО на официальных \
сайтах: {domains} и других сайтах правительства штата Флорида и США (домены .gov и .fl.us). Новостные \
сайты, блоги и форумы не используй. Верни только JSON без пояснений и без markdown:
{{"facts": [{{"fact": "...", "url": "...", "page_title": "..."}}]}}
fact — одно конкретное утверждение по-русски (правило, срок, сумма, документ, адрес услуги), url — точная \
ссылка на страницу официального сайта, где это написано. 10–25 фактов. Ничего без ссылки."""

WRITE_SYSTEM = f"""\
Ты — автор справочных гайдов русскоязычного сайта «Florida RU».
{AUDIENCE}

Напиши постоянный гайд по теме, опираясь ТОЛЬКО на переданный список фактов с официальных сайтов.
1. 500–1100 слов. Структура: короткое вступление → разделы с подзаголовками (строка начинается с «## ») \\
→ раздел «## Коротко» с главными шагами списком в одном абзаце.
2. Только факты из списка: суммы, сроки, названия документов и ведомств — точно как там. Ничего не \\
додумывай. Если важной детали в фактах нет — напиши, что её стоит уточнить на официальном сайте.
3. Простой разговорный русский, без канцелярита. Английские названия ведомств и документов при первом \\
упоминании дай в скобках: «Департамент безопасности дорожного движения (FLHSMV)».
4. Не пиши ссылки в тексте — сайт добавит список источников сам. Не упоминай, что ты ИИ.
5. used_urls — ссылки из фактов, на которые ты опирался."""

CHECK_SYSTEM = """\
Ты — фактчекер справочного сайта. Сверь гайд со списком фактов с официальных сайтов. Найди утверждения, \
которых нет в фактах (суммы, сроки, требования, названия), и искажения. Общие советы («уточните на сайте», \
«запишитесь заранее») — не ошибка. ok = true, только если существенных проблем нет."""


class DraftError(RuntimeError):
    pass


@dataclass
class Fact:
    fact: str
    url: str
    page_title: str = ""


def is_official(url: str, domains: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return (host.endswith(".gov") or host.endswith(".fl.us")
            or any(host == d or host.endswith("." + d) for d in domains))


def parse_facts(text: str, domains: list[str]) -> list[Fact]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    raw = []
    if 0 <= start < end:
        try:
            raw = json.loads(text[start:end + 1]).get("facts") or []
        except (json.JSONDecodeError, AttributeError):
            raw = []
    facts = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url, fact = (item.get("url") or "").strip(), (item.get("fact") or "").strip()
        if fact and url.startswith("http") and is_official(url, domains):
            facts.append(Fact(fact=fact, url=url, page_title=(item.get("page_title") or "")[:400]))
    return facts


def collect_facts(guide: Guide) -> list[Fact]:
    domains = guide.domains or DEFAULT_DOMAINS
    data = search_raw(
        api_url=settings.PERPLEXITY_API_URL, api_key=settings.PERPLEXITY_API_KEY, model=settings.PERPLEXITY_MODEL,
        instructions=FACTS_INSTRUCTIONS.format(domains=", ".join(domains)),
        query=f"Тема: {guide.title}. Что раскрыть: {guide.brief or guide.title}",
        tool={"type": "web_search"}, key_name="PERPLEXITY_API_KEY", purpose=AICall.Purpose.GUIDE,
    )
    return parse_facts(response_text(data), domains)


def facts_brief(facts: list[Fact]) -> str:
    return "\n".join(f"[{n}] {f.fact} ({f.url})" for n, f in enumerate(facts, 1))


def draft_guide(guide: Guide) -> Guide:
    """Пишет черновик. Опубликованный гайд не трогает: правки живого текста — только руками редактора."""
    if guide.is_published:
        raise DraftError("гайд уже опубликован — черновик поверх него не пишем. Снимите с публикации в админке")
    if current_budget().money_exceeded:
        raise DraftError("дневной бюджет на ИИ исчерпан")
    try:
        facts = collect_facts(guide)
    except CollectorError as exc:
        raise DraftError(f"не удалось собрать факты: {exc}") from exc
    if len(facts) < 3:
        raise DraftError(f"с официальных сайтов нашлось фактов: {len(facts)} — мало для гайда")

    brief = facts_brief(facts)
    draft: GuideDraft = ai.ask(
        purpose=AICall.Purpose.GUIDE, model=settings.AI_WRITER_MODEL, system=WRITE_SYSTEM,
        user=f"Тема: {guide.title}\nЧто раскрыть: {guide.brief or '—'}\n\nФакты с официальных сайтов:\n{brief}",
        output=GuideDraft, max_tokens=8000,
    )
    check: GuideCheck = ai.ask(
        purpose=AICall.Purpose.GUIDE, model=settings.AI_VERIFIER_MODEL, system=CHECK_SYSTEM,
        user=f"Факты:\n{brief}\n\n<guide>\n{draft.title}\n{draft.teaser}\n\n{draft.body}\n</guide>",
        output=GuideCheck, max_tokens=2000,
    )

    guide.title = draft.title.strip()[:160] or guide.title
    guide.teaser = draft.teaser.strip()[:300]
    guide.body = draft.body.strip()
    guide.status = Guide.Status.DRAFT
    stamp = timezone.localtime().strftime("%d.%m.%Y %H:%M")
    verdict = "замечаний нет" if check.ok and not check.issues else "; ".join(check.issues) or "проверка сомневается"
    guide.review_notes = f"Черновик от {stamp}. Проверка: {verdict}"[:5000]
    guide.save()

    used = [u for u in draft.used_urls if u in {f.url for f in facts}] or [f.url for f in facts]
    titles = {f.url: f.page_title for f in facts}
    guide.sources.all().delete()
    for order, url in enumerate(dict.fromkeys(used)):
        GuideSource.objects.create(guide=guide, name=(urlparse(url).hostname or url).removeprefix("www."),
                                   url=url, title=titles.get(url, ""), order=order)
    return guide

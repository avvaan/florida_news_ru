"""Обновление базы знаний: официальные страницы по списку, Federal Register API, Visa Bulletin, наши материалы.

Запускается командой `python manage.py immigration_update` раз в неделю (cron на сервере, см. deploy/crontab.example).
Страница перенарезается, только если её текст изменился (хэш), — тогда у источника ставится changed_at.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta

import requests
from django.conf import settings
from django.db import DatabaseError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from . import sources as S
from .extract import Page, Section, chunks, parse_html, parse_markdown
from .models import Chunk, Source

log = logging.getLogger(__name__)
TIMEOUT = 40


@dataclass
class Outcome:
    url: str
    status: str
    chunks: int = 0
    changed: bool = False
    note: str = ""


@dataclass
class Report:
    outcomes: list[Outcome] = field(default_factory=list)

    def add(self, outcome: Outcome) -> Outcome:
        self.outcomes.append(outcome)
        log.info("База знаний: %s — %s %s", outcome.url, outcome.status, outcome.note)
        return outcome

    @property
    def ok(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.status == Source.Status.OK]

    @property
    def failed(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.status != Source.Status.OK]

    def summary(self) -> str:
        changed = sum(o.changed for o in self.ok)
        return (f"источников скачано: {len(self.ok)}, изменилось: {changed}, фрагментов: "
                f"{sum(o.chunks for o in self.ok)}, не скачано: {len(self.failed)}")


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": settings.FETCH_USER_AGENT, "Accept": "text/html,application/json",
                      "Accept-Language": "en-US,en;q=0.8"})
    return s


FORCE = {"on": False}  # --force: перенарезать всё (после правки правил нарезки), даже если текст не изменился


def _clean_page(page: Page) -> Page:
    """Нулевые байты (бывают в полном тексте Federal Register) PostgreSQL в текстовые поля не принимает."""
    page.title = (page.title or "").replace("\x00", "")
    for section in page.sections:
        section.heading = section.heading.replace("\x00", "")
        section.lines = [line.replace("\x00", "") for line in section.lines]
    return page


def store(source: Source, page: Page, *, now=None) -> Outcome:
    """Сохраняет текст источника: перенарезает фрагменты, только если текст изменился (или --force).

    Ошибка базы на одном источнике помечает его «не скачано», а не обрывает всё обновление.
    """
    try:
        return _store(source, _clean_page(page), now=now)
    except (DatabaseError, ValueError) as exc:
        return fail(source, Source.Status.FAILED, f"{type(exc).__name__}: {exc}")


def _store(source: Source, page: Page, *, now=None) -> Outcome:
    now = now or timezone.now()
    new_hash = page.content_hash
    changed = new_hash != source.content_hash
    with transaction.atomic():
        if changed or FORCE["on"]:
            source.chunks.all().delete()
            Chunk.objects.bulk_create([Chunk(source=source, section=heading, text=text, position=n)
                                       for n, (heading, text) in enumerate(chunks(page))])
            source.content_hash = new_hash
            source.changed_at = now
            source.fetched_at = now
        source.title = (source.title or page.title or source.url)[:400]
        source.status, source.last_error, source.checked_at, source.is_active = Source.Status.OK, "", now, True
        source.save()
    return Outcome(source.url, Source.Status.OK, source.chunks.count(), changed)


def fail(source: Source, status: str, note: str) -> Outcome:
    source.status, source.last_error = status, note[:500]
    source.save(update_fields=["status", "last_error"])
    return Outcome(source.url, status, note=note)


def fetch_official(official: S.Official, http: requests.Session) -> Outcome:
    if not S.is_allowed(official.url):
        return Outcome(official.url, Source.Status.FAILED, note="адрес не из списка разрешённых")
    requested = official.url

    def source_for(url: str) -> Source:
        obj, _ = Source.objects.get_or_create(
            url=url, defaults={"agency": official.agency, "kind": official.kind, "title": official.title})
        return obj

    try:
        resp = http.get(official.url, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        return fail(source_for(official.url), Source.Status.FAILED, f"{type(exc).__name__}: {exc}")
    if resp.status_code in (401, 403, 429):
        return fail(source_for(official.url), Source.Status.BLOCKED, f"HTTP {resp.status_code} (защита сайта от ботов)")
    if resp.status_code in (404, 410):
        return fail(source_for(official.url), Source.Status.NOT_FOUND, f"HTTP {resp.status_code}")
    if resp.status_code >= 400:
        return fail(source_for(official.url), Source.Status.FAILED, f"HTTP {resp.status_code}")
    final = getattr(resp, "url", official.url) or official.url
    if not S.is_allowed(final):
        return fail(source_for(official.url), Source.Status.FAILED, f"переадресация на чужой адрес {final}")
    page = parse_html(resp.text)
    if final != official.url:
        # страница переехала: храним её под конечным адресом, чтобы одна страница не попала в базу дважды
        Source.objects.filter(url=official.url).delete()
        official = S.Official(final, official.agency, official.kind, "")
    source = source_for(official.url)
    if official.kind == Source.Kind.POLICY and not source.title:
        source.title = f"USCIS Policy Manual: {page.title}"[:400]
    if page.looks_js_only():
        return fail(source, Source.Status.JS_ONLY,
                    f"текста {page.words} слов — страница из ссылок или собирается JavaScript")
    outcome = store(source, page)
    if final != requested:
        outcome.note = f"переадресация с {requested}"
    return outcome


def update_visa_bulletin(http: requests.Session) -> Outcome:
    """Visa Bulletin: со страницы-оглавления берём ссылку на текущий выпуск."""
    index = Source.objects.get_or_create(url=S.VISA_BULLETIN_INDEX, defaults={
        "agency": Source.Agency.STATE, "kind": Source.Kind.VISA_BULLETIN, "title": "Visa Bulletin"})[0]
    try:
        resp = http.get(S.VISA_BULLETIN_INDEX, timeout=TIMEOUT)
    except requests.RequestException as exc:
        return fail(index, Source.Status.FAILED, f"{type(exc).__name__}: {exc}")
    if resp.status_code != 200:
        status = Source.Status.BLOCKED if resp.status_code in (401, 403, 429) else Source.Status.FAILED
        return fail(index, status, f"HTTP {resp.status_code}")
    links = re.findall(r'href="([^"]*/visa-bulletin/\d{4}/visa-bulletin-for-[a-z]+-\d{4}\.html)"', resp.text)
    if not links:
        return fail(index, Source.Status.FAILED, "на странице нет ссылки на текущий выпуск")
    url = links[0] if links[0].startswith("http") else f"https://travel.state.gov{links[0]}"
    outcome = fetch_official(S.Official(url, Source.Agency.STATE, Source.Kind.VISA_BULLETIN), http)
    if outcome.status == Source.Status.OK:
        # прошлые выпуски из ответов убираем: актуален только текущий
        old = Source.objects.filter(kind=Source.Kind.VISA_BULLETIN).exclude(url__in=[url, S.VISA_BULLETIN_INDEX])
        for prev in old:
            prev.chunks.all().delete()
        old.update(is_active=False)
    return outcome


def update_federal_register(http: requests.Session, report: Report) -> None:
    since = (timezone.localdate() - timedelta(days=S.FR_DAYS)).isoformat()
    params = [("per_page", "100"), ("order", "newest"), ("conditions[publication_date][gte]", since)]
    params += [("conditions[agencies][]", a) for a in S.FR_AGENCIES]
    params += [("fields[]", f) for f in ("title", "abstract", "html_url", "publication_date", "type", "raw_text_url",
                                          "agencies")]
    try:
        resp = http.get(S.FR_API, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        docs = resp.json().get("results", [])
    except (requests.RequestException, ValueError) as exc:
        report.add(Outcome(S.FR_API, Source.Status.FAILED, note=f"{type(exc).__name__}: {exc}"))
        return
    keep = set()
    for doc in docs:
        if doc["title"].startswith(S.FR_SKIP_TITLES):
            continue
        url = doc["html_url"]
        keep.add(url)
        source, _ = Source.objects.get_or_create(url=url, defaults={
            "agency": Source.Agency.FEDERAL_REGISTER, "kind": Source.Kind.FR_DOCUMENT})
        source.title = f"{doc['type']}: {doc['title']}"[:400]
        source.published_on = parse_date(doc.get("publication_date") or "")
        body = ""
        if doc.get("raw_text_url") and S.is_allowed(doc["raw_text_url"]):
            try:
                raw = http.get(doc["raw_text_url"], timeout=TIMEOUT)
                # полный текст FR иногда уводит на капчу (unblock.federalregister.gov) — такое не берём
                plain = "text/plain" in (getattr(raw, "headers", None) or {}).get("content-type", "text/plain")
                if raw.ok and S.is_allowed(getattr(raw, "url", doc["raw_text_url"])) and plain:
                    body = " ".join(raw.text.split()[:S.FR_MAX_WORDS])
            except requests.RequestException:
                pass
        page = Page(title=source.title, sections=[
            s for s in (Section("Summary", [doc.get("abstract") or ""]), Section("Text", _paragraphs(body)))
            if any(s.lines)])
        if not page.sections:
            report.add(fail(source, Source.Status.FAILED, "пустой документ"))
            continue
        report.add(store(source, page))
    stale = Source.objects.filter(kind=Source.Kind.FR_DOCUMENT, is_active=True).exclude(url__in=keep)
    for old in stale:  # старше 90 дней — из ответов убираем
        old.chunks.all().delete()
    stale.update(is_active=False)


def _paragraphs(text: str, size: int = 120) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


def update_ours(report: Report) -> None:
    """Наши опубликованные гайды по иммиграции и заметки за последние NEWS_DAYS дней («что изменилось»)."""
    from django.db.models import Q

    from guides.models import Guide
    from hubs.views import IMMIGRATION_WORDS
    from news.models import Article

    site = settings.SITE_URL
    keep = set()
    for guide in Guide.objects.published().filter(slug__in=S.OUR_GUIDES):
        url = f"{site}{guide.get_absolute_url()}"
        keep.add(url)
        source, _ = Source.objects.get_or_create(url=url, defaults={
            "agency": Source.Agency.TUTFLORIDA, "kind": Source.Kind.GUIDE, "language": "ru"})
        source.title = f"Гайд TutFlorida: {guide.title}"[:400]
        report.add(store(source, parse_markdown(guide.body, guide.title),
                         now=guide.revised_at or guide.published_at or timezone.now()))
    since = timezone.now() - timedelta(days=S.NEWS_DAYS)
    words = Q()
    for word in IMMIGRATION_WORDS:
        words |= Q(title__icontains=word) | Q(teaser__icontains=word)
    for article in Article.objects.published().filter(published_at__gte=since).filter(words):
        url = f"{site}{article.get_absolute_url()}"
        keep.add(url)
        source, _ = Source.objects.get_or_create(url=url, defaults={
            "agency": Source.Agency.TUTFLORIDA, "kind": Source.Kind.ARTICLE, "language": "ru"})
        source.title = f"Новость TutFlorida: {article.title}"[:400]
        source.published_on = timezone.localdate(article.published_at)
        body = f"{article.teaser}\n\n{article.body}"
        report.add(store(source, parse_markdown(body, article.title), now=article.revised_at or article.published_at))
    stale = Source.objects.filter(agency=Source.Agency.TUTFLORIDA, is_active=True).exclude(url__in=keep)
    for old in stale:
        old.chunks.all().delete()
    stale.update(is_active=False)


def update_all(*, only: str = "", official: bool = True, ours: bool = True, force: bool = False) -> Report:
    report = Report()
    FORCE["on"] = force
    http = session()
    if official:
        for item in S.officials():
            if only and only not in item.url:
                continue
            _guard(report, item.url, lambda item=item: report.add(fetch_official(item, http)))
        if not only or "visa-bulletin" in only:
            _guard(report, S.VISA_BULLETIN_INDEX, lambda: report.add(update_visa_bulletin(http)))
        if not only or "federalregister" in only:
            _guard(report, S.FR_API, lambda: update_federal_register(http, report))
    if ours and not only:
        _guard(report, settings.SITE_URL, lambda: update_ours(report))
    return report


def _guard(report: Report, url: str, step) -> None:
    """Сбой одного шага (страница, Federal Register, наши материалы) не обрывает остальные."""
    try:
        step()
    except Exception as exc:  # noqa: BLE001 — записываем в отчёт и идём дальше
        log.exception("База знаний: сбой шага %s", url)
        report.add(Outcome(url, Source.Status.FAILED, note=f"{type(exc).__name__}: {exc}"[:300]))

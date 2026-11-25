"""Поиск по сайту (/poisk/?q=…): справочник, гайды, «Что посетить», афиша, новости.

Без поискового движка: каждое слово запроса — условие icontains по нескольким полям, все слова должны найтись.
Чтобы «стоматолога» находил «стоматолог», у длинных слов отрезаем окончание (грубая основа). Регистр: SQLite
сравнивает без учёта регистра только латиницу, поэтому ищем и строчный, и «Заглавный» вариант основы
(PostgreSQL ILIKE справляется и сам).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.db.models import Q

MAX_QUERY = 80
MIN_TERM = 2
LIMITS = {"listings": 30, "guides": 10, "places": 8, "events": 8, "articles": 20}
ENDINGS = re.compile(
    r"(ами|ями|ого|его|ому|ему|ыми|ими|ах|ях|ов|ев|ей|ой|ий|ый|ая|яя|ое|ее|ам|ям|ом|ем|ую|юю|а|я|ы|и|у|ю|е|о|ь)$"
)


def terms(query: str) -> list[str]:
    """Слова запроса → основы: «русского стоматолога» → ["русск", "стоматолог"]."""
    words = re.findall(r"[\wʼ'’-]+", query.lower())[:6]
    out = []
    for word in words:
        if len(word) < MIN_TERM:
            continue
        stem = ENDINGS.sub("", word) if len(word) > 5 and not word.isascii() else word
        out.append(stem if len(stem) >= 5 else word)  # «майами» не превращаем в «май»
    return out


def match(fields: list[str], query_terms: list[str]) -> Q:
    """Каждое слово — хотя бы в одном из полей (И между словами, ИЛИ между полями)."""
    condition = Q()
    for term in query_terms:
        variants = {term, term.capitalize(), term.upper()}
        any_field = Q()
        for name in fields:
            for variant in variants:
                any_field |= Q(**{f"{name}__icontains": variant})
        condition &= any_field
    return condition


def score(text_title: str, query_terms: list[str]) -> int:
    title = (text_title or "").lower()
    return sum(3 for term in query_terms if term in title)


@dataclass
class Results:
    query: str = ""
    terms: list = field(default_factory=list)
    listings: list = field(default_factory=list)
    guides: list = field(default_factory=list)
    places: list = field(default_factory=list)
    events: list = field(default_factory=list)
    articles: list = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(len(getattr(self, key)) for key in LIMITS)


def search(query: str, lang: str = "ru") -> Results:
    from directory.models import Category, Listing
    from events.models import Event
    from guides.models import Guide
    from news.models import Article
    from places.models import Destination

    query = " ".join(query.split())[:MAX_QUERY]
    found = Results(query=query, terms=terms(query))
    if not found.terms:
        return found
    uk = lang == "uk"
    tr = (lambda *names: [n for name in names for n in (name, f"{name}_uk")]) if uk else (lambda *names: list(names))

    listings = (Listing.objects.active().filter(category__kind=Category.Kind.BUSINESS)
                .filter(match(["name", "city", "address", "category__name", "region__name", "region__name_locative",
                               *tr("description", "languages")],
                              found.terms))
                .select_related("category", "region"))[:200]
    found.listings = sorted(listings, key=lambda i: -score(i.name + " " + i.category.name, found.terms))[
        :LIMITS["listings"]]
    guides = Guide.objects.published().filter(match(tr("title", "teaser", "body"), found.terms))[:100]
    found.guides = sorted(guides, key=lambda g: -score(g.loc("title"), found.terms))[:LIMITS["guides"]]
    places = Destination.objects.published().filter(lang=lang).filter(match(["title", "teaser", "body"], found.terms))
    found.places = sorted(places[:50], key=lambda d: -score(d.title, found.terms))[:LIMITS["places"]]
    found.events = list(Event.objects.upcoming().for_language().filter(match([*tr("title", "description"), "city", "venue"],
                                                              found.terms))[:LIMITS["events"]])
    found.articles = list(Article.objects.published().filter(match(tr("title", "teaser", "body"), found.terms))
                          .order_by("-published_at")[:LIMITS["articles"]])
    return found

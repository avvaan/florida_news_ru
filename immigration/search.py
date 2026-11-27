"""Поиск фрагментов базы знаний без новой инфраструктуры.

PostgreSQL (прод): полнотекстовый поиск — английские источники по словарю english, наши материалы по russian.
Слова запроса объединяются через ИЛИ, порядок — по SearchRank. SQLite (тесты, локально): простой подсчёт
совпадений основ слов. Вопрос читателя на русском или украинском заранее переводит в английский запрос модель
(шаг разбора в assistant.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.db import connection

from .models import Chunk

STOP = {"the", "a", "an", "of", "to", "in", "for", "and", "or", "is", "are", "how", "what", "do", "does", "can",
        "my", "i", "on", "with", "by", "be", "it", "this", "that", "who", "when", "where", "which", "about",
        "как", "что", "это", "для", "или", "по", "на", "в", "и", "с", "о", "об", "ли", "не", "у", "из", "к", "до",
        "як", "що", "це", "та", "чи", "з", "і", "й", "від"}
MIN_SCORE = 0.01
TOP = 6


@dataclass
class Hit:
    chunk: Chunk
    score: float


def terms(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁіїєґІЇЄҐ0-9][\w'-]*", (text or "").lower())
    return [w for w in dict.fromkeys(words) if w not in STOP and len(w) > 1][:16]


def search(query_en: str, query_ru: str = "", limit: int = TOP) -> list[Hit]:
    if connection.vendor == "postgresql":
        return _search_postgres(query_en, query_ru, limit)
    return _search_simple(query_en, query_ru, limit)


def _base():
    return Chunk.objects.filter(source__is_active=True, source__status="ok").select_related("source")


def _search_postgres(query_en: str, query_ru: str, limit: int) -> list[Hit]:
    from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

    hits: list[Hit] = []
    for lang, config, query in (("en", "english", query_en), ("ru", "russian", query_ru or query_en)):
        words = terms(query)
        if not words:
            continue
        tsquery = None
        for word in words:
            part = SearchQuery(word, config=config, search_type="plain")
            tsquery = part if tsquery is None else tsquery | part
        vector = SearchVector("section", weight="A", config=config) + SearchVector("text", weight="B", config=config)
        qs = (_base().filter(source__language=lang).annotate(rank=SearchRank(vector, tsquery, cover_density=True))
              .filter(rank__gt=MIN_SCORE).order_by("-rank")[:limit])
        hits += [Hit(chunk, float(chunk.rank)) for chunk in qs]
    return _top(hits, limit)


def _stem(word: str) -> str:
    return word[:6] if len(word) > 6 else word


def _search_simple(query_en: str, query_ru: str, limit: int) -> list[Hit]:
    stems_en = [_stem(w) for w in terms(query_en)]
    stems_ru = [_stem(w) for w in terms(query_ru or query_en)]
    hits: list[Hit] = []
    for chunk in _base():
        stems = stems_en if chunk.source.language == "en" else stems_ru
        if not stems:
            continue
        body = f"{chunk.section} {chunk.section} {chunk.text}".lower()
        found = sum(1 for s in stems if s in body)
        if found:
            hits.append(Hit(chunk, found / len(stems)))
    return _top([h for h in hits if h.score >= 0.34], limit)


def _top(hits: list[Hit], limit: int) -> list[Hit]:
    """Лучшие фрагменты, не больше двух с одной страницы — чтобы источники были разными."""
    hits.sort(key=lambda h: -h.score)
    out, per_source = [], {}
    for hit in hits:
        n = per_source.get(hit.chunk.source_id, 0)
        if n >= 2:
            continue
        per_source[hit.chunk.source_id] = n + 1
        out.append(hit)
        if len(out) >= limit:
            break
    return out

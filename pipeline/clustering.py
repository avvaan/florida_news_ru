"""Склейка записей разных СМИ в сюжеты по похожести заголовков."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from core.models import SiteSettings
from core.text import jaccard, title_tokens
from news.models import Story
from sources.models import FeedItem


def best_match(tokens: set[str], candidates: list[tuple[Story, set[str]]], threshold: float):
    best, best_score = None, 0.0
    for story, story_tokens in candidates:
        score = jaccard(tokens, story_tokens)
        if score > best_score:
            best, best_score = story, score
    return (best, best_score) if best_score >= threshold else (None, best_score)


def cluster_items(items=None) -> dict:
    """Привязывает записи без сюжета к существующему сюжету или создаёт новый.

    Сравнение идёт с заголовками всех записей сюжета за окно склейки,
    поэтому сюжет «собирает» разные формулировки одной истории.
    """
    conf = SiteSettings.load()
    threshold = float(conf.cluster_similarity)
    window_start = timezone.now() - timedelta(hours=conf.cluster_window_hours)

    if items is None:
        items = FeedItem.objects.filter(story__isnull=True).select_related("source").order_by("fetched_at")

    candidates: dict[int, tuple[Story, set[str]]] = {}
    for item in FeedItem.objects.filter(story__created_at__gte=window_start).select_related("story"):
        story, tokens = candidates.get(item.story_id, (item.story, set()))
        candidates[item.story_id] = (story, tokens | title_tokens(item.title))

    stats = {"attached": 0, "new_stories": 0}
    for item in items:
        tokens = title_tokens(item.title)
        story, _ = best_match(tokens, list(candidates.values()), threshold)
        if story is None:
            story = Story.objects.create(title=item.title[:400])
            stats["new_stories"] += 1
            candidates[story.pk] = (story, tokens)
        else:
            stats["attached"] += 1
            existing = candidates[story.pk][1]
            candidates[story.pk] = (story, existing | tokens)
        item.story = story
        item.save(update_fields=["story"])
    return stats

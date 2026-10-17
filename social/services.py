"""Этап «Сигналы из соцсетей»: сбор → разбор → подтверждение подсказок.

Правило: соцсети — только подсказки. Заметка пишется по сюжету, в котором есть запись от СМИ
или официального источника; текст сигналов автору заметок не передаётся.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from core.models import SiteSettings
from news.models import Region, Story, Topic
from pipeline import ai
from pipeline.models import AICall
from sources.models import Source

from . import prompts
from .collectors import budget_allows_signals, collect_search, collect_telegram
from .models import Hint, Signal, SignalSource
from .schemas import HintMatches, Triage

log = logging.getLogger(__name__)

# Подтверждением считается запись от источника одного из этих типов.
TRUSTED_TYPES = (Source.SourceType.MEDIA, Source.SourceType.OFFICIAL, Source.SourceType.WEATHER)
HINT_TTL = timedelta(hours=48)
STORY_WINDOW = timedelta(hours=48)
TRIAGE_BATCH = 30
MAX_STORIES = 80
MAX_HINTS = 40


def has_trusted_source(items) -> bool:
    return any(item.source.source_type in TRUSTED_TYPES for item in items)


def trusted_stories(since):
    return Story.objects.filter(created_at__gte=since, items__source__source_type__in=TRUSTED_TYPES).distinct()


# --- Разбор сигналов ----------------------------------------------------------

def triage_new(say) -> dict:
    """Шум — в архив, совпавшие — к сюжету, новые интересные темы — в «Подсказки»."""
    stats = {"noise": 0, "to_story": 0, "to_hint": 0, "new_hints": 0}
    now = timezone.now()
    Signal.objects.filter(status=Signal.Status.NEW, fetched_at__lt=now - HINT_TTL).update(status=Signal.Status.NOISE)
    pending = list(Signal.objects.filter(status=Signal.Status.NEW).select_related("source").order_by("fetched_at"))
    for start in range(0, len(pending), TRIAGE_BATCH):
        if not budget_allows_signals():
            say("Сигналы: потрачена доля дневного бюджета для соцсетей — разбор отложен")
            break
        batch = pending[start:start + TRIAGE_BATCH]
        stories = list(Story.objects.filter(created_at__gte=now - STORY_WINDOW).order_by("-created_at")[:MAX_STORIES])
        hints = list(Hint.objects.filter(status=Hint.Status.OPEN)[:MAX_HINTS])
        try:
            result: Triage = ai.ask(
                purpose=AICall.Purpose.TRIAGE,
                model=settings.AI_CLASSIFIER_MODEL,
                system=prompts.TRIAGE_SYSTEM,
                user=(
                    f"Сигналы:\n{prompts.signals_brief(batch)}\n\n"
                    f"Сюжеты за 48 часов:\n{prompts.stories_brief(stories)}\n\n"
                    f"Открытые подсказки:\n{prompts.hints_brief(hints)}"
                ),
                output=Triage,
                max_tokens=6000,
            )
        except ai.AIError as exc:
            say(f"Сигналы: ошибка разбора — {exc}")
            break
        apply_triage(batch, result, stories, hints, stats)
    return stats


def apply_triage(batch, result: Triage, stories, hints, stats: dict) -> None:
    signals = {s.pk: s for s in batch}
    stories = {s.pk: s for s in stories}
    hints = {h.pk: h for h in hints}
    specs = {h.group: h for h in result.new_hints}
    regions = {r.slug: r for r in Region.objects.all()}
    topics = {t.slug: t for t in Topic.objects.all()}
    created: dict[str, Hint] = {}

    for verdict in result.signals:
        signal = signals.get(verdict.id)
        if signal is None or signal.status != Signal.Status.NEW:
            continue
        signal.region = regions.get(verdict.region) or signal.region
        signal.topic = topics.get(verdict.topic)
        if not verdict.interesting or verdict.region == "outside":
            signal.status = Signal.Status.NOISE
            stats["noise"] += 1
        elif verdict.story_id in stories:
            signal.status, signal.story = Signal.Status.STORY, stories[verdict.story_id]
            stats["to_story"] += 1
        elif verdict.hint_id in hints:
            signal.status, signal.hint = Signal.Status.HINT, hints[verdict.hint_id]
            stats["to_hint"] += 1
        else:
            key = verdict.group or f"signal-{signal.pk}"
            if key not in created:
                spec = specs.get(verdict.group or "")
                created[key] = Hint.objects.create(
                    title=(spec.title if spec else signal.text)[:200], summary=spec.summary if spec else "",
                    region=signal.region, topic=signal.topic,
                )
                stats["new_hints"] += 1
            signal.status, signal.hint = Signal.Status.HINT, created[key]
            stats["to_hint"] += 1
        signal.save(update_fields=["region", "topic", "status", "story", "hint"])


# --- Подтверждение подсказок ---------------------------------------------------

def confirm_hint(hint: Hint, story: Story) -> None:
    hint.status, hint.story, hint.confirmed_at = Hint.Status.CONFIRMED, story, timezone.now()
    hint.save(update_fields=["status", "story", "confirmed_at", "updated_at"])
    hint.signals.update(story=story)


def confirm_hints(say) -> dict:
    """Ищет для открытых подсказок сюжет от СМИ или официального источника о том же событии."""
    stats = {"confirmed": 0, "expired": 0}
    now = timezone.now()
    stats["expired"] = Hint.objects.filter(status=Hint.Status.OPEN, created_at__lt=now - HINT_TTL).update(
        status=Hint.Status.EXPIRED)
    hints = list(Hint.objects.filter(status=Hint.Status.OPEN)[:MAX_HINTS])
    if not hints:
        return stats
    stories = list(trusted_stories(now - STORY_WINDOW).order_by("-created_at")[:MAX_STORIES])
    if not stories:
        return stats
    if not budget_allows_signals():
        say("Сигналы: потрачена доля дневного бюджета для соцсетей — подтверждение отложено")
        return stats
    try:
        result: HintMatches = ai.ask(
            purpose=AICall.Purpose.TRIAGE,
            model=settings.AI_CLASSIFIER_MODEL,
            system=prompts.MATCH_SYSTEM,
            user=(f"Подсказки:\n{prompts.hints_brief(hints)}\n\n"
                  f"Сюжеты от СМИ и официальных источников:\n{prompts.stories_brief(stories)}"),
            output=HintMatches,
            max_tokens=2000,
        )
    except ai.AIError as exc:
        say(f"Сигналы: ошибка подтверждения — {exc}")
        return stats
    hints_by_id = {h.pk: h for h in hints}
    stories_by_id = {s.pk: s for s in stories}
    for match in result.matches:
        hint, story = hints_by_id.get(match.hint_id), stories_by_id.get(match.story_id)
        if hint and story and hint.status == Hint.Status.OPEN:
            confirm_hint(hint, story)
            stats["confirmed"] += 1
            say(f"Подсказка «{hint.title[:60]}» подтверждена сюжетом «{story.title[:60]}»")
    return stats


# --- Весь этап ------------------------------------------------------------------

def run_social(say) -> dict:
    """Сбор включённых сборщиков, разбор сигналов, подтверждение подсказок."""
    conf = SiteSettings.load()
    stats = {"signals_new": 0, "signals_failed": 0}
    collectors = [
        (conf.signals_perplexity_enabled, lambda: collect_search(SignalSource.Kind.PERPLEXITY, say)),
        (conf.signals_grok_enabled, lambda: collect_search(SignalSource.Kind.GROK, say)),
        (conf.signals_telegram_enabled, lambda: collect_telegram(say)),
    ]
    for enabled, collect in collectors:
        if enabled:
            result = collect()
            stats["signals_new"] += result["created"]
            stats["signals_failed"] += result["failed"]
    stats.update(triage_new(say))
    stats.update(confirm_hints(say))
    if any(stats.values()):
        say(f"Соцсети: новых сигналов {stats['signals_new']}, к сюжетам {stats['to_story']}, "
            f"новых подсказок {stats['new_hints']}, подтверждено {stats['confirmed']}, шум {stats['noise']}")
    return stats

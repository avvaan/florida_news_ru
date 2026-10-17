"""Конвейер: сбор → склейка → отбор → написание → проверка → публикация."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.models import SiteSettings
from news.covers import candidates_for
from news.models import Article, ArticleSource, Region, Story, Tag, Topic
from sources.fetch import fetch_all
from sources.models import Source

from . import ai, prompts
from .budget import current_budget
from .clustering import cluster_items
from .decisions import decide
from .models import AICall, PipelineRun
from .schemas import Classification, CoverChoice, Draft, Verification
from .telegram import post_article

log = logging.getLogger(__name__)

STALE_AFTER = timedelta(hours=48)
MAX_SOURCES_PER_ARTICLE = 3


class RunLog:
    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, message: str):
        log.info(message)
        stamp = timezone.localtime().strftime("%H:%M:%S")
        self.lines.append(f"{stamp} {message}")

    def text(self) -> str:
        return "\n".join(self.lines)


# --- Отбор -------------------------------------------------------------------

def story_items(story: Story):
    return list(story.items.select_related("source").order_by("-source__trust_weight", "published_at"))


def classify_story(story: Story) -> Story:
    items = story_items(story)
    newest = max((i.published_at or i.fetched_at for i in items), default=story.created_at)
    if timezone.now() - newest > STALE_AFTER:
        story.status = Story.Status.SKIPPED
        story.note = "Устаревшая новость (старше 48 часов)"
        story.save(update_fields=["status", "note", "updated_at"])
        return story

    result: Classification = ai.ask(
        purpose=AICall.Purpose.CLASSIFY,
        model=settings.AI_CLASSIFIER_MODEL,
        system=prompts.CLASSIFY_SYSTEM,
        user=f"Сюжет:\n\n{prompts.story_brief(items)}",
        output=Classification,
        max_tokens=1500,
        story=story,
    )
    story.classification = result.model_dump()
    story.score = max(0, min(10, result.score))
    story.is_urgent = result.is_urgent
    story.is_sensitive = result.is_sensitive
    story.topic = Topic.objects.filter(slug=result.topic).first()
    story.region = Region.objects.filter(slug=result.region).first()

    # Опасные предупреждения NWS — всегда срочно, вне зависимости от оценки модели.
    if any(i.source.kind == Source.Kind.NWS_ALERTS for i in items):
        story.is_urgent = True
        story.score = max(story.score, 9)
        story.topic = story.topic or Topic.objects.filter(slug="weather").first()

    if result.region == "outside":
        story.status = Story.Status.SKIPPED
        story.note = "Не про Флориду"
    else:
        story.status = Story.Status.CLASSIFIED
        story.note = result.reason[:500]
    story.save()
    return story


def classify_new(say: RunLog) -> int:
    count = 0
    for story in Story.objects.filter(status=Story.Status.NEW).order_by("created_at"):
        try:
            classify_story(story)
            count += 1
        except ai.AIError as exc:
            story.status = Story.Status.FAILED
            story.note = f"Классификация: {exc}"[:500]
            story.save(update_fields=["status", "note", "updated_at"])
            say(f"Ошибка классификации «{story.title[:60]}»: {exc}")
    return count


# --- Написание и проверка ---------------------------------------------------

def write_article(story: Story, conf: SiteSettings, say: RunLog) -> Article:
    items = story_items(story)
    brief = prompts.story_brief(items)
    region = story.region.name if story.region else "Флорида"
    topic = story.topic.name if story.topic else "—"

    covers = candidates_for(story.topic.slug if story.topic else None, story.is_urgent)
    draft: Draft = ai.ask(
        purpose=AICall.Purpose.WRITE,
        model=settings.AI_WRITER_MODEL,
        system=prompts.WRITE_SYSTEM,
        user=(
            f"Регион: {region}. Тема: {topic}.\n\nДанные источников:\n\n{brief}\n\n"
            f"Обложки на выбор:\n{prompts.covers_brief(covers, recent_covers(story.topic))}"
        ),
        output=Draft,
        max_tokens=8000,
        story=story,
        effort=settings.AI_WRITER_EFFORT or None,
    )
    verification: Verification = ai.ask(
        purpose=AICall.Purpose.VERIFY,
        model=settings.AI_VERIFIER_MODEL,
        system=prompts.VERIFY_SYSTEM,
        user=(
            f"Данные источников:\n\n{brief}\n\n"
            f"<article>\nЗаголовок: {draft.title}\nАнонс: {draft.teaser}\n\n{draft.body}\n</article>"
        ),
        output=Verification,
        max_tokens=2000,
        story=story,
    )

    decision = decide(
        score=story.score or 0,
        is_urgent=story.is_urgent,
        is_sensitive=story.is_sensitive,
        has_official_source=any(i.source.is_official for i in items),
        verified_ok=verification.ok,
        verifier_confidence=verification.confidence,
        issues=verification.issues,
        insufficient_facts=draft.insufficient_facts,
        auto_publish_enabled=conf.auto_publish_enabled,
        publish_without_review=conf.publish_without_review,
        auto_publish_min_score=conf.auto_publish_min_score,
        min_confidence=conf.min_verifier_confidence,
    )

    with transaction.atomic():
        article = Article.objects.create(
            story=story,
            title=draft.title.strip()[:120],
            teaser=draft.teaser.strip()[:300],
            body=draft.body.strip(),
            region=story.region,
            topic=story.topic,
            is_urgent=story.is_urgent,
            is_sensitive=story.is_sensitive,
            score=story.score,
            cover_image=draft.cover if draft.cover in {c.base for c in covers} else "",
            status=Article.Status.REVIEW,
            review_reason="" if decision.publish else decision.reason,
            verification={**verification.model_dump(), "decision": decision.reason},
        )
        attach_sources(article, items)
        attach_tags(article, draft.tags)
        story.status = Story.Status.WRITTEN
        story.save(update_fields=["status", "updated_at"])

    if decision.publish:
        publish_article(article, say=say)
    else:
        say(f"На проверку: «{article.title}» — {decision.reason}")
    return article


def recent_covers(topic, limit: int = 5) -> set[str]:
    """Обложки последних заметок рубрики — чтобы ИИ не ставил одну и ту же подряд."""
    qs = Article.objects.exclude(cover_image="")
    if topic:
        qs = qs.filter(topic=topic)
    return set(qs.order_by("-created_at").values_list("cover_image", flat=True)[:limit])


def choose_cover(article: Article) -> str:
    """Заново подбирает обложку уже написанной заметке по её тексту. Возвращает id или ""."""
    covers = candidates_for(article.topic.slug if article.topic else None, article.is_urgent)
    recent = recent_covers(article.topic) - {article.cover_image}
    choice: CoverChoice = ai.ask(
        purpose=AICall.Purpose.COVER,
        model=settings.AI_CLASSIFIER_MODEL,
        system=prompts.COVER_SYSTEM,
        user=(
            f"<article>\nЗаголовок: {article.title}\nАнонс: {article.teaser}\n\n{article.body}\n</article>\n\n"
            f"Обложки на выбор:\n{prompts.covers_brief(covers, recent)}"
        ),
        output=CoverChoice,
        max_tokens=500,
        story=article.story,
    )
    if choice.cover not in {c.base for c in covers}:
        return ""
    article.cover_image = choice.cover
    article.save(update_fields=["cover_image", "updated_at"])
    return choice.cover


def rechoose_covers(articles, *, run: PipelineRun | None = None) -> PipelineRun:
    """Подбор обложек пачке заметок. Журнал и итоги — в запуске конвейера, как у обычного прохода."""
    run = run or PipelineRun.objects.create(stats={"task": "covers"})
    say = RunLog()
    stats = {"task": "covers", "covers_changed": 0, "covers_failed": 0}
    try:
        for article in articles:
            budget = current_budget()
            if budget.money_exceeded:
                say(f"Лимит ИИ на сегодня исчерпан (${budget.spent_today:.2f}/${budget.budget}) — остановились")
                break
            try:
                cover = choose_cover(article)
            except ai.AIError as exc:
                stats["covers_failed"] += 1
                say(f"«{article.title[:60]}»: ошибка — {exc}")
                continue
            if cover:
                stats["covers_changed"] += 1
                say(f"«{article.title[:60]}» → {cover}")
            else:
                stats["covers_failed"] += 1
                say(f"«{article.title[:60]}»: ИИ вернул неизвестную обложку, оставили прежнюю")
        say(f"Обложки: подобрано {stats['covers_changed']}, не вышло {stats['covers_failed']}")
    except Exception as exc:  # noqa: BLE001
        run.success = False
        say(f"Сбой: {type(exc).__name__}: {exc}")
        log.exception("Сбой подбора обложек")
    run.finished_at = timezone.now()
    run.stats = {**run.stats, **stats}
    run.log = say.text()
    run.save()
    return run


def attach_sources(article: Article, items) -> None:
    seen_sources = set()
    order = 0
    for item in items:
        if item.source_id in seen_sources:
            continue
        seen_sources.add(item.source_id)
        ArticleSource.objects.create(
            article=article, source=item.source, name=item.source.name,
            url=item.url, title=item.title, order=order,
        )
        order += 1
        if order >= MAX_SOURCES_PER_ARTICLE:
            break


def attach_tags(article: Article, names: list[str]) -> None:
    for name in names[:4]:
        name = name.strip().strip("#")[:60]
        if not name:
            continue
        tag = Tag.objects.filter(name__iexact=name).first() or Tag.objects.create(name=name)
        article.tags.add(tag)


def write_pending(say: RunLog) -> int:
    conf = SiteSettings.load()
    queue = (
        Story.objects.filter(status=Story.Status.CLASSIFIED, article__isnull=True)
        .order_by("-is_urgent", "-score", "created_at")
    )
    written = 0
    for story in queue:
        if not story.is_urgent and (story.score or 0) < conf.min_score_to_write:
            story.status = Story.Status.SKIPPED
            story.note = story.note or f"Важность {story.score} ниже порога {conf.min_score_to_write}"
            story.save(update_fields=["status", "note", "updated_at"])
            continue
        budget = current_budget(conf)
        if not budget.allows(story.is_urgent):
            say(
                f"Лимит: заметок {budget.articles_today}/{budget.max_articles}, "
                f"ИИ ${budget.spent_today:.2f}/${budget.budget} — пишем только срочное"
            )
            continue  # сюжет остаётся в очереди и может пойти завтра, если не устареет
        try:
            write_article(story, conf, say)
            written += 1
        except ai.AIError as exc:
            story.status = Story.Status.FAILED
            story.note = f"Написание: {exc}"[:500]
            story.save(update_fields=["status", "note", "updated_at"])
            say(f"Ошибка написания «{story.title[:60]}»: {exc}")
    return written


# --- Публикация --------------------------------------------------------------

def publish_article(article: Article, *, say=log.info) -> Article:
    article.status = Article.Status.PUBLISHED
    article.published_at = article.published_at or timezone.now()
    article.review_reason = ""
    article.save(update_fields=["status", "published_at", "review_reason", "updated_at"])
    say(f"Опубликовано: «{article.title}»")
    try:
        result = post_article(article)
        say(f"Telegram: {result}")
    except Exception as exc:  # noqa: BLE001 — сбой Telegram не отменяет публикацию на сайте
        say(f"Telegram: ошибка — {exc}")
    return article


def reject_article(article: Article) -> Article:
    article.status = Article.Status.REJECTED
    article.save(update_fields=["status", "updated_at"])
    return article


# --- Полный проход -----------------------------------------------------------

def run_pipeline(*, fetch: bool = True, write: bool = True, run: PipelineRun | None = None) -> PipelineRun:
    run = run or PipelineRun.objects.create()
    say = RunLog()
    stats: dict = {}
    try:
        if fetch:
            results = fetch_all()
            stats["sources_ok"] = sum(1 for r in results if not r.error)
            stats["sources_failed"] = sum(1 for r in results if r.error)
            stats["items_new"] = sum(r.created for r in results)
            for r in results:
                if r.error:
                    say(f"Источник «{r.source.name}»: ошибка — {r.error[:200]}")
            say(f"Сбор: новых записей {stats['items_new']}, ошибок источников {stats['sources_failed']}")
        stats.update(cluster_items())
        say(f"Склейка: новых сюжетов {stats['new_stories']}, присоединено {stats['attached']}")
        if write:
            stats["classified"] = classify_new(say)
            stats["written"] = write_pending(say)
            say(f"Отбор: {stats['classified']}, написано заметок: {stats['written']}")
        stats["ai_cost_today"] = str(AICall.objects.today().total_cost())
    except Exception as exc:  # noqa: BLE001
        run.success = False
        say(f"Сбой конвейера: {type(exc).__name__}: {exc}")
        log.exception("Сбой конвейера")
    run.finished_at = timezone.now()
    run.stats = {**run.stats, **stats}
    run.log = say.text()
    run.save()
    return run

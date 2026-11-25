"""Лимиты расходов: заметок в день и долларов на ИИ в день."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from core.models import SiteSettings
from news.models import BUSINESS, Article

from .models import AICall


@dataclass
class BudgetState:
    articles_today: int
    max_articles: int
    spent_today: Decimal
    budget: Decimal

    @property
    def articles_exceeded(self) -> bool:
        return self.articles_today >= self.max_articles

    @property
    def money_exceeded(self) -> bool:
        return self.spent_today >= self.budget

    @property
    def urgent_only(self) -> bool:
        """При превышении любого лимита пишем только срочное."""
        return self.articles_exceeded or self.money_exceeded

    def allows(self, is_urgent: bool) -> bool:
        return is_urgent or not self.urgent_only


def counted_articles_today(business: bool = False) -> int:
    """Заметки, которые идут в дневной лимит: несрочные, не отклонённые и не черновики.

    У раздела «Бизнес» свой лимит, поэтому его заметки считаются отдельно.
    """
    day_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    qs = (Article.objects.filter(created_at__gte=day_start, is_urgent=False)
          .exclude(status__in=[Article.Status.REJECTED, Article.Status.DRAFT]))
    qs = qs.filter(topic__slug=BUSINESS) if business else qs.exclude(topic__slug=BUSINESS)
    return qs.count()


# Наводнение модель относит то к погоде, то к ЧП: для разнообразия ленты это одна тема.
TOPIC_GROUPS = {"safety": "weather"}
URGENT_WINDOW = timedelta(hours=12)


def topic_group(slug: str | None) -> str:
    return TOPIC_GROUPS.get(slug or "other", slug or "other")


def _counted():
    return Article.objects.exclude(status__in=[Article.Status.REJECTED, Article.Status.DRAFT])


def articles_by_group_today() -> Counter:
    """Несрочные заметки за сегодня по темам (без бизнеса — у него свой лимит)."""
    day_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    slugs = (_counted().filter(created_at__gte=day_start, is_urgent=False).exclude(topic__slug=BUSINESS)
             .values_list("topic__slug", flat=True))
    return Counter(topic_group(s) for s in slugs)


def urgent_by_group() -> Counter:
    """Срочные заметки за последние 12 часов по темам."""
    slugs = (_counted().filter(created_at__gte=timezone.now() - URGENT_WINDOW, is_urgent=True)
             .values_list("topic__slug", flat=True))
    return Counter(topic_group(s) for s in slugs)


def current_budget(conf: SiteSettings | None = None) -> BudgetState:
    conf = conf or SiteSettings.load()
    return BudgetState(
        articles_today=counted_articles_today(),
        max_articles=conf.max_articles_per_day,
        spent_today=AICall.objects.today().total_cost(),
        budget=conf.ai_budget_per_day_usd,
    )

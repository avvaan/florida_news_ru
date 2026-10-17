from decimal import Decimal

import pytest

from django.test import override_settings

from core.models import SiteSettings
from news.models import Article
from pipeline.ai import estimate_cost
from pipeline.budget import current_budget
from pipeline.models import AICall

pytestmark = pytest.mark.django_db


@override_settings(AI_PRICING={"m": {"input": "0.30", "cache_read": "0.03", "output": "1.20"},
                                "a": {"input": "1.00", "cache_read": "0.10", "cache_write": "1.25", "output": "5.00"}})
def test_estimate_cost_with_cache():
    assert estimate_cost("m", 1_000_000, 0) == Decimal("0.300000")
    assert estimate_cost("m", 0, 1_000_000) == Decimal("1.200000")
    assert estimate_cost("m", 0, 0, cache_read=1_000_000) == Decimal("0.030000")
    assert estimate_cost("a", 0, 0, cache_write=1_000_000) == Decimal("1.250000")


def test_unknown_model_uses_expensive_fallback():
    # неизвестная модель не должна обнулять расходы и обходить лимит бюджета
    assert estimate_cost("unknown-model", 1_000_000, 1_000_000) == Decimal("18.000000")


def test_budget_money_limit_allows_only_urgent():
    conf = SiteSettings.load()
    conf.ai_budget_per_day_usd = Decimal("1.00")
    conf.save()
    AICall.objects.create(purpose="write", model="deepseek-v4-pro", cost_usd=Decimal("0.60"))
    assert not current_budget().urgent_only
    AICall.objects.create(purpose="write", model="deepseek-v4-pro", cost_usd=Decimal("0.40"))
    budget = current_budget()
    assert budget.money_exceeded and budget.urgent_only
    assert budget.allows(is_urgent=True) and not budget.allows(is_urgent=False)


def test_budget_article_limit():
    conf = SiteSettings.load()
    conf.max_articles_per_day = 2
    conf.save()
    for i in range(2):
        Article.objects.create(title=f"Заметка {i}", teaser="t", body="b")
    budget = current_budget()
    assert budget.articles_exceeded and not budget.allows(is_urgent=False)

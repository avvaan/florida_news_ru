"""Раздел «Бизнес: акции и сделки»: отдельная страница, свой дневной лимит, без смешения с общей лентой."""

from unittest import mock

import pytest
from django.test import override_settings
from django.utils import timezone

from core.models import SiteSettings
from news.models import Article, Story, Topic
from pipeline import ai, services
from pipeline.schemas import Classification, Draft
from pipeline.services import RunLog, classify_story, write_pending
from sources.models import Source

from .test_social import FakeDeepSeek
from .test_value_seo import BODY, answers, make_story

pytestmark = pytest.mark.django_db


def business_article(title, kind, **kw):
    return Article.objects.create(title=title, teaser="Анонс", body=BODY, status=Article.Status.PUBLISHED,
                                  published_at=timezone.now(), topic=Topic.objects.get(slug="business"),
                                  business_kind=kind, **kw)


def test_business_topic_and_sources_are_seeded():
    topic = Topic.objects.get(slug="business")
    assert topic.short_name == "Бизнес" and topic.get_absolute_url() == "/business/"
    sources = Source.objects.filter(notes__startswith="Бизнес")
    assert sources.count() == 7 and all(s.url.startswith("https://www.bing.com/news/search?") for s in sources)
    assert all(s.source_type == "media" and not s.is_active and not s.is_verified for s in sources)


def test_business_page_blocks_filters_and_redirect(client):
    business_article("NextEra отчиталась о росте прибыли", "stocks")
    business_article("Застройщик купил участок в Брикелле за $300 млн", "deals")
    business_article("Сеть магазинов закрывает склад в Орландо", "other")
    html = client.get("/business/").content.decode()
    assert "Бизнес: акции и сделки" in html and "не инвестиционная рекомендация" in html
    assert 'id="biz-stocks-h"' in html and 'id="biz-deals-h"' in html and "Сеть магазинов закрывает" in html

    stocks = client.get("/business/stocks/").content.decode()
    assert "NextEra отчиталась" in stocks and "Застройщик купил" not in stocks
    deals = client.get("/business/deals/").content.decode()
    assert "Застройщик купил" in deals and "NextEra" not in deals
    assert client.get("/business/crypto/").status_code == 404

    resp = client.get("/topic/business/")
    assert resp.status_code == 301 and resp["Location"] == "/business/"


def test_business_stays_out_of_general_feeds_but_has_home_block(client):
    business_article("Lennar купила застройщика в Тампе", "deals")
    Article.objects.create(title="Обычная новость про дороги", teaser="t", body=BODY, status="published",
                           published_at=timezone.now(), topic=Topic.objects.get(slug="roads"))
    home = client.get("/").content.decode()
    assert "Обычная новость про дороги" in home
    assert 'id="biz-h"' in home and "Lennar купила застройщика" in home  # только в блоке «Бизнес» сбоку
    assert home.count("Lennar купила застройщика") == 1
    assert "Lennar купила" not in client.get("/region/tampa/").content.decode()
    assert 'href="/business/"' in home  # в меню тем


@override_settings(AI_PROVIDER="deepseek")
def test_classifier_kind_is_stored_on_article():
    story = make_story("Royal Caribbean shares jump after record quarter", status=Story.Status.NEW)
    classification = Classification(score=6, topic="business", region="miami", is_urgent=False,
                                    is_sensitive=False, reason="отчёт компании", business_kind="stocks")
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek(answers(classification=classification))):
        classify_story(story)
        write_pending(RunLog())
    article = Article.objects.get(story=story)
    assert article.topic.slug == "business" and article.business_kind == "stocks"


@override_settings(AI_PROVIDER="deepseek")
def test_business_has_its_own_daily_limit(monkeypatch):
    monkeypatch.setattr(services, "MORNING_UNTIL_HOUR", 0)  # вечер: весь лимит
    SiteSettings.objects.update(max_articles_per_day=1, max_business_per_day=2, min_score_to_write=1)
    business = Topic.objects.get(slug="business")
    biz = [make_story(f"Business deal number {n}", score=s) for n, s in ((1, 7), (2, 6), (3, 5))]
    general = [make_story(f"General news number {n}", score=s) for n, s in ((1, 8), (2, 4))]
    Story.objects.filter(pk__in=[s.pk for s in biz]).update(topic=business, classification={"business_kind": "deals"})
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek(answers())):
        write_pending(RunLog())
    written = set(Article.objects.values_list("story_id", flat=True))
    assert written == {biz[0].pk, biz[1].pk, general[0].pk}  # 2 бизнес + 1 общая, лимиты не мешают друг другу
    biz[2].refresh_from_db()
    general[1].refresh_from_db()
    assert "Лимит бизнес-заметок" in biz[2].note and "Лимит публикаций" in general[1].note
    assert Article.objects.filter(topic=business, business_kind="deals").count() == 2


def test_writer_prompt_forbids_investment_advice():
    from pipeline import prompts
    assert "не инвестиционная рекомендация" in prompts.WRITE_SYSTEM
    assert "business_kind" in prompts.CLASSIFY_SYSTEM


def test_business_pages_in_sitemap(client):
    from django.core.cache import cache
    cache.clear()
    xml = client.get("/sitemap.xml").content.decode()
    cache.clear()
    assert "/business/</loc>" in xml and "/business/stocks/</loc>" in xml and "/business/deals/</loc>" in xml
    assert "/topic/business/" not in xml

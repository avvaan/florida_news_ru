"""Разноплановая лента: лимит одной темы в день, срочное по затяжному событию не забивает ленту;
главная тема видна и на следующих страницах ленты."""

from datetime import timedelta
from unittest import mock

import pytest
from django.test import override_settings
from django.utils import timezone

from core.models import SiteSettings
from news.models import Article, Story, Topic
from pipeline import ai, prompts, services
from pipeline.services import RunLog, write_pending

from .test_social import FakeDeepSeek
from .test_value_seo import BODY, answers, make_story

pytestmark = pytest.mark.django_db


def topic_stories(slug, scores, urgent=False):
    stories = [make_story(f"{slug} story number {n} {s}", score=s, urgent=urgent) for n, s in enumerate(scores)]
    Story.objects.filter(pk__in=[s.pk for s in stories]).update(topic=Topic.objects.get(slug=slug))
    return stories


def written_ids():
    return set(Article.objects.filter(story__isnull=False).values_list("story_id", flat=True))


def run():
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek(answers())):
        write_pending(RunLog())


@pytest.fixture
def evening(monkeypatch):
    monkeypatch.setattr(services, "MORNING_UNTIL_HOUR", 0)  # вечерний проход: весь дневной лимит


@override_settings(AI_PROVIDER="deepseek")
def test_one_topic_cannot_take_the_whole_day(evening):
    SiteSettings.objects.update(max_articles_per_day=8, max_per_topic_per_day=3, min_score_to_write=4)
    weather, safety = topic_stories("weather", [9, 9, 8]), topic_stories("safety", [9, 8])  # одна тема
    laws = topic_stories("laws", [6, 5])
    health = topic_stories("health", [5])
    run()
    top_floods = weather[:2] + safety[:1]  # три самых важных из погоды и ЧП
    assert written_ids() == {s.pk for s in top_floods + laws + health}
    for story in (weather[2], safety[1]):
        story.refresh_from_db()
        assert story.status == Story.Status.SKIPPED and "оставляем место другим темам" in story.note


@override_settings(AI_PROVIDER="deepseek")
def test_topic_limit_counts_articles_written_earlier_today(evening):
    SiteSettings.objects.update(max_per_topic_per_day=2, min_score_to_write=1)
    weather = Topic.objects.get(slug="weather")
    for n in range(2):
        Article.objects.create(title=f"Ранняя заметка {n}", teaser="t", body=BODY, topic=weather,
                               status=Article.Status.PUBLISHED, published_at=timezone.now())
    late = topic_stories("weather", [9])
    events = topic_stories("events", [5])
    run()
    assert written_ids() == {events[0].pk}
    late[0].refresh_from_db()
    assert late[0].status == Story.Status.SKIPPED


@override_settings(AI_PROVIDER="deepseek")
def test_repeated_urgent_on_same_topic_goes_into_normal_limits(evening):
    SiteSettings.objects.update(urgent_per_topic_12h=2, max_per_topic_per_day=1, min_score_to_write=1)
    safety = Topic.objects.get(slug="safety")
    for n in range(2):
        Article.objects.create(title=f"Срочно {n}", teaser="t", body=BODY, topic=safety, is_urgent=True,
                               status=Article.Status.PUBLISHED, published_at=timezone.now())
    old = Article.objects.create(title="Срочно вчера", teaser="t", body=BODY, topic=safety, is_urgent=True,
                                 status=Article.Status.PUBLISHED, published_at=timezone.now())
    Article.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=13))
    first, second = topic_stories("weather", [10, 9], urgent=True)
    run()
    first.refresh_from_db()
    second.refresh_from_db()
    assert not first.is_urgent and "идёт как обычная" in first.note
    assert written_ids() == {first.pk}  # одна обычная заметка в рамках лимита темы, вторая — нет
    assert not Article.objects.get(story=first).is_urgent
    assert second.status == Story.Status.SKIPPED


@override_settings(AI_PROVIDER="deepseek")
def test_first_urgent_stories_still_go_beyond_limits(evening):
    SiteSettings.objects.update(max_articles_per_day=1, max_per_topic_per_day=1, urgent_per_topic_12h=2)
    urgent = topic_stories("weather", [10, 10, 9], urgent=True)
    run()
    assert {s.pk for s in urgent[:2]} <= written_ids()
    assert Article.objects.filter(is_urgent=True).count() == 2
    assert Article.objects.filter(story=urgent[2], is_urgent=False).exists()  # третья — как обычная, в лимит


def test_prompts_ask_for_variety_and_merge_ongoing_events():
    assert "разноплановой" in prompts.CLASSIFY_SYSTEM
    assert "Затяжное событие" in prompts.CLASSIFY_SYSTEM and "Затяжное событие" in prompts.DEDUP_SYSTEM


def test_lead_is_shown_on_later_feed_pages(client):
    weather = Topic.objects.get(slug="roads")
    now = timezone.now()
    for n in range(40):
        Article.objects.create(title=f"Заметка номер {n}", teaser="t", body=BODY, topic=weather, score=5,
                               status=Article.Status.PUBLISHED, published_at=now - timedelta(minutes=n))
    Article.objects.filter(title="Заметка номер 3").update(score=9)
    first = client.get("/").content.decode()
    second = client.get("/?page=2").content.decode()
    assert "Лента · страница 2" in second
    for html in (first, second):
        lead = html.split('class="lead', 1)[1].split("</article>", 1)[0]
        assert "Заметка номер 3<" in lead
    assert second.count("Заметка номер 3<") == 1  # главная не повторяется в ленте второй страницы
    assert 'class="tiles"' not in second

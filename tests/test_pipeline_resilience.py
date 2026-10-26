"""Конвейер переживает поломки: сбой одной заметки не останавливает остальные, старая сборка пишет в новую базу."""

import pytest
from django.db import IntegrityError, connection

from news.models import Article, Story
from pipeline import services
from pipeline.services import RunLog, write_pending

from .test_value_seo import make_story, published

pytestmark = pytest.mark.django_db


def test_old_build_can_insert_article_without_cover_manual():
    """Задача по расписанию на старой сборке не знает про cover_manual — база подставит false сама."""
    article = published()
    table = Article._meta.db_table
    columns = [f.column for f in Article._meta.local_concrete_fields
               if f.column not in {"id", "cover_manual", "slug", "story_id"}]
    cols = ", ".join(connection.ops.quote_name(c) for c in columns)
    with connection.cursor() as cursor:
        cursor.execute(f"INSERT INTO {table} ({cols}, slug) SELECT {cols}, slug || '-old' FROM {table} WHERE id = %s",
                       [article.pk])
    copy = Article.objects.get(slug=f"{article.slug}-old")
    assert copy.cover_manual is False


def fake_writer(broken: set[int]):
    def write(story, conf, say):
        if story.pk in broken:
            raise IntegrityError('null value in column "cover_manual"')
        story.status = Story.Status.WRITTEN
        story.save(update_fields=["status", "updated_at"])
    return write


def test_one_broken_story_does_not_stop_the_rest(monkeypatch):
    first, second, third = (make_story(f"Story {n}", score=9 - n) for n in range(3))
    monkeypatch.setattr(services, "write_article", fake_writer({first.pk}))
    say = RunLog()
    assert write_pending(say) == 2
    first.refresh_from_db()
    assert first.status == Story.Status.FAILED and "IntegrityError" in first.note
    assert Story.objects.filter(pk__in=[second.pk, third.pk], status=Story.Status.WRITTEN).count() == 2
    assert "Сбой записи «Story 0»" in say.text()


def test_repeated_failures_stop_writing_and_keep_the_queue(monkeypatch):
    stories = [make_story(f"Story {n}", score=9 - n) for n in range(4)]
    monkeypatch.setattr(services, "write_article", fake_writer({s.pk for s in stories}))
    say = RunLog()
    assert write_pending(say) == 0
    statuses = [Story.objects.get(pk=s.pk).status for s in stories]
    assert statuses == [Story.Status.FAILED, Story.Status.FAILED, Story.Status.CLASSIFIED, Story.Status.CLASSIFIED]
    assert "остальные сюжеты ждут следующего запуска" in say.text()

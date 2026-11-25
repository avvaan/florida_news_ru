"""Автопостинг заметок на страницу Facebook (pipeline/facebook.py)."""
from unittest import mock

import pytest
from django.utils import timezone

from news.models import Article, Region, Topic
from pipeline import facebook
from pipeline.services import publish_article

pytestmark = pytest.mark.django_db


@pytest.fixture
def article():
    return Article.objects.create(
        title="Шторм перед Днём благодарения", teaser="Ливни и задержки рейсов",
        body="Первый абзац.\n\nВторой абзац.", region=Region.objects.get(slug="miami"),
        topic=Topic.objects.get(slug="weather"), status=Article.Status.PUBLISHED, published_at=timezone.now(),
    )


def test_without_page_token_only_logs(article):
    assert facebook.post_article(article) == "dry-run"
    article.refresh_from_db()
    assert article.facebook_posted_at is None


def test_posts_once_with_link_and_saves_id(article, settings):
    settings.FACEBOOK_PAGE_ID, settings.FACEBOOK_PAGE_TOKEN = "123", "page-token"
    resp = mock.Mock(ok=True, json=lambda: {"id": "123_456"})
    with mock.patch("pipeline.facebook.requests.post", return_value=resp) as post:
        assert facebook.post_article(article) == "отправлено"
        assert facebook.post_article(article) == "уже отправлено"
    post.assert_called_once()
    url, data = post.call_args.args[0], post.call_args.kwargs["data"]
    assert url.endswith("/123/feed") and data["access_token"] == "page-token"
    assert data["link"].endswith(article.get_absolute_url()) and article.title in data["message"]
    article.refresh_from_db()
    assert article.facebook_post_id == "123_456" and article.facebook_posted_at


def test_publish_posts_to_facebook_and_survives_errors(article, settings):
    settings.FACEBOOK_PAGE_ID, settings.FACEBOOK_PAGE_TOKEN = "123", "page-token"
    article.status = Article.Status.REVIEW
    article.save()
    err = mock.Mock(ok=False, status_code=400, json=lambda: {"error": {"message": "Invalid token"}})
    log = []
    with mock.patch("pipeline.facebook.requests.post", return_value=err):
        publish_article(article, say=log.append)
    article.refresh_from_db()
    assert article.status == Article.Status.PUBLISHED and article.facebook_posted_at is None
    assert "Facebook: ошибка — Facebook: Invalid token" in log

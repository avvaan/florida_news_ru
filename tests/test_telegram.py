from unittest import mock

import pytest
from django.test import override_settings

from core.models import SiteSettings
from news.models import Article, Region
from pipeline.telegram import build_post, post_article

pytestmark = pytest.mark.django_db


def make_article(**kw):
    defaults = dict(title="Шторм <идёт> к Тампе", teaser="Эвакуация зоны A & убежища", body="Текст",
                    region=Region.objects.get(slug="tampa"), status=Article.Status.PUBLISHED)
    defaults.update(kw)
    return Article.objects.create(**defaults)


@override_settings(SITE_URL="https://floridasegodnya.test")
def test_post_format_urgent_and_escaped():
    article = make_article(is_urgent=True)
    text = build_post(article)
    assert text.startswith("🚨 <b>Шторм &lt;идёт&gt; к Тампе</b>")
    assert "Эвакуация зоны A &amp; убежища" in text
    assert "📍 Тампа" in text
    assert f'href="https://floridasegodnya.test/news/{article.slug}/"' in text


def test_regular_post_has_no_siren_and_statewide_has_no_pin():
    article = make_article(region=Region.objects.get(slug="florida"))
    text = build_post(article)
    assert not text.startswith("🚨") and "📍" not in text


def test_dry_run_when_disabled():
    article = make_article()
    with mock.patch("pipeline.telegram.requests.post") as post:
        assert post_article(article) == "dry-run"
        post.assert_not_called()


@override_settings(TELEGRAM_BOT_TOKEN="123:abc", TELEGRAM_CHANNEL_ID="@test_channel")
def test_sends_when_enabled():
    conf = SiteSettings.load()
    conf.telegram_enabled = True
    conf.save()
    article = make_article()
    response = mock.Mock(headers={"Content-Type": "application/json"})
    response.json.return_value = {"ok": True, "result": {"message_id": 42}}
    with mock.patch("pipeline.telegram.requests.post", return_value=response) as post:
        assert post_article(article) == "отправлено"
        payload = post.call_args.kwargs["json"]
        assert payload["chat_id"] == "@test_channel" and payload["parse_mode"] == "HTML"
        # повторно не отправляем
        assert post_article(article) == "уже отправлено"
        assert post.call_count == 1
    article.refresh_from_db()
    assert article.telegram_message_id == 42

from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Page, SiteSettings
from news.models import Article
from pipeline.models import AICall, PipelineRun
from sources.models import Source

pytestmark = pytest.mark.django_db


@pytest.fixture
def api():
    staff = User.objects.create_user("editor", password="x", is_staff=True)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=staff).key}")
    return client


@pytest.fixture
def article():
    return Article.objects.create(title="Тест", teaser="Анонс", body="Текст", status=Article.Status.REVIEW)


def test_requires_staff_token():
    anon = APIClient()
    assert anon.get("/api/v1/articles/").status_code == 401
    user = User.objects.create_user("reader", password="x")
    anon.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
    assert anon.get("/api/v1/articles/").status_code == 403
    assert anon.get("/api/docs/").status_code == 403


def test_list_and_filter_articles(api, article):
    Article.objects.create(title="Другая", teaser="t", body="b", status=Article.Status.PUBLISHED,
                           published_at=timezone.now())
    data = api.get("/api/v1/articles/?status=review").json()
    assert data["count"] == 1 and data["results"][0]["title"] == "Тест"
    assert api.get("/api/v1/articles/?q=Друг").json()["count"] == 1


def test_create_article_with_sources_tags_and_cover(api):
    resp = api.post("/api/v1/articles/", {
        "title": "Ураган приближается к Тампе", "teaser": "Эвакуация зоны A", "body": "Текст.\n\nЕщё абзац.",
        "region": "tampa", "topic": "weather", "is_urgent": True, "tags": ["ураган", "Тампа"],
        "sources": [{"name": "NHC", "url": "https://www.nhc.noaa.gov/", "title": "Advisory"}],
        "cover_image": "covers/hurricane-photo-1", "status": "published",
    }, format="json")
    assert resp.status_code == 201, resp.json()
    data = resp.json()
    assert data["slug"].startswith("uragan-priblizhaetsya")
    assert sorted(data["tags"]) == ["Тампа", "ураган"] and data["sources"][0]["name"] == "NHC"
    assert data["cover_url"].endswith(".webp") and "hurricane-photo-1" in data["cover_url"]
    assert data["published_at"] is not None


def test_bad_cover_is_rejected(api, article):
    resp = api.patch(f"/api/v1/articles/{article.pk}/", {"cover_image": "covers/nope"}, format="json")
    assert resp.status_code == 400 and "cover_image" in resp.json()


def test_publish_reject_and_delete(api, article):
    assert api.post(f"/api/v1/articles/{article.pk}/publish/").json()["status"] == "published"
    assert api.post(f"/api/v1/articles/{article.pk}/telegram/").json()["result"] == "dry-run"
    assert api.post(f"/api/v1/articles/{article.pk}/reject/").json()["status"] == "rejected"
    assert api.delete(f"/api/v1/articles/{article.pk}/").status_code == 204
    assert not Article.objects.exists()


def test_settings_get_and_patch(api):
    assert api.get("/api/v1/settings/").json()["publish_without_review"] is True
    resp = api.patch("/api/v1/settings/", {"min_score_to_write": 5, "ai_budget_per_day_usd": "1.50"}, format="json")
    assert resp.status_code == 200
    conf = SiteSettings.load()
    assert conf.min_score_to_write == 5 and str(conf.ai_budget_per_day_usd) == "1.50"


def test_sources_toggle_and_check(api):
    source = Source.objects.first()
    resp = api.patch(f"/api/v1/sources/{source.pk}/", {"is_active": True, "trust_weight": 9}, format="json")
    assert resp.status_code == 200 and resp.json()["is_active"] is True
    with mock.patch("api.views.check_source", return_value=(True, "записей: 5")):
        data = api.post(f"/api/v1/sources/{source.pk}/check/?activate=1").json()
    assert data["ok"] and data["source"]["is_verified"]


def test_pages_by_slug(api):
    resp = api.patch("/api/v1/pages/contacts/", {"body": "Пишите нам."}, format="json")
    assert resp.status_code == 200 and Page.objects.get(slug="contacts").body == "Пишите нам."


def test_pipeline_run_in_background_and_conflict(api):
    class InlineThread:
        def __init__(self, target, args, daemon):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    with mock.patch("api.runner.threading.Thread", InlineThread), \
            mock.patch("pipeline.services.fetch_all", return_value=[]):
        resp = api.post("/api/v1/pipeline/run/", {"fetch": True, "write": False}, format="json")
    assert resp.status_code == 202
    run = PipelineRun.objects.get(pk=resp.json()["id"])
    assert run.finished_at is not None and run.stats["source"] == "api"
    assert api.get(f"/api/v1/pipeline/{run.pk}/").json()["running"] is False

    PipelineRun.objects.create()  # незавершённый запуск
    assert api.post("/api/v1/pipeline/run/", {}, format="json").status_code == 409


def test_stats_and_covers(api, article):
    AICall.objects.create(purpose="write", model="deepseek-v4-pro", cost_usd="0.010000")
    stats = api.get("/api/v1/stats/").json()
    assert stats["articles"]["by_status"]["review"] == 1
    assert stats["ai"]["today"]["calls"] == 1 and stats["ai"]["provider"]
    covers = api.get("/api/v1/covers/").json()
    assert "weather" in covers and covers["weather"][0]["description"]


def test_schema_and_docs(api):
    assert api.get("/api/schema/").status_code == 200
    assert api.get("/api/docs/").status_code == 200


def test_privacy_owner_migration_updates_only_untouched_page():
    from django.apps import apps

    from core import seed
    page = Page.objects.get(slug="privacy")
    page.body = seed.PRIVACY_V1
    page.save()
    seed.update_privacy_owner(apps, None)
    page.refresh_from_db()
    assert "CITRUSTACK LLC" in page.body

    page.body = "Своя политика"
    page.save()
    seed.update_privacy_owner(apps, None)
    page.refresh_from_db()
    assert page.body == "Своя политика"


def test_footer_shows_owner(client):
    assert "© " in client.get("/").content.decode() and "CITRUSTACK LLC" in client.get("/").content.decode()

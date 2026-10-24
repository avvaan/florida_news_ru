import io

import pytest
from django.utils import timezone

from news.covers import cover_pools, pick_cover
from news.models import Article, Topic

pytestmark = pytest.mark.django_db


def test_every_topic_has_several_covers_with_all_files():
    from django.conf import settings
    pools = cover_pools()
    for topic in Topic.objects.all():
        assert len(pools[topic.slug]) >= 3, topic.slug
    for covers in pools.values():
        for cover in covers:
            for suffix in (".webp", "-640.webp", ".jpg"):
                assert (settings.BASE_DIR / "static" / f"{cover.base}{suffix}").exists(), cover.base


def test_pick_is_stable_and_rotates():
    assert pick_cover("weather", 7) == pick_cover("weather", 7)
    assert len({pick_cover("weather", n).base for n in range(4)}) == 4
    assert pick_cover("no-such-topic", 1) in cover_pools()["florida"]


def test_illustrations_and_photos_alternate():
    pool = cover_pools()["weather"]
    assert not pool[0].is_photo and pool[1].is_photo
    assert pool[1].credit.startswith("Фото: Freepik")
    assert pool[0].credit == ""


def test_neighbouring_articles_get_different_covers(client):
    topic = Topic.objects.get(slug="roads")
    a1, a2 = (Article.objects.create(title=f"Дорога {i}", teaser="t", body="b", topic=topic,
                                     status=Article.Status.PUBLISHED, published_at=timezone.now())
              for i in range(2))
    assert a1.cover != a2.cover
    html = client.get(a2.get_absolute_url()).content.decode()
    assert a2.cover in html


def test_urgent_weather_uses_hurricane_pool():
    article = Article.objects.create(title="Ураган", teaser="t", body="b", is_urgent=True,
                                     topic=Topic.objects.get(slug="weather"))
    assert article.cover.startswith("covers/hurricane")


def test_photo_cover_has_stock_credit_in_caption(client):
    topic = Topic.objects.get(slug="roads")
    article = None
    for i in range(6):
        candidate = Article.objects.create(title=f"Трасса {i}", teaser="t", body="b", topic=topic,
                                           status=Article.Status.PUBLISHED, published_at=timezone.now())
        if candidate.cover_info.is_photo:
            article = candidate
            break
    assert article is not None
    html = client.get(article.get_absolute_url()).content.decode()
    assert "Фото: Freepik (иллюстративное)" in html


# --- Соседи в ленте не повторяют картинку -------------------------------------

def published(title, topic, minutes_ago, **kw):
    from datetime import timedelta
    return Article.objects.create(title=title, teaser="t", body="b", topic=topic, status=Article.Status.PUBLISHED,
                                  published_at=timezone.now() - timedelta(minutes=minutes_ago), **kw)


def test_fresh_choices_skip_neighbours_and_keep_topic_pool():
    from news.covers import candidates_for, fresh_choices
    candidates = candidates_for("incidents")
    incidents = [c.base for c in cover_pools()["incidents"]]
    fresh = fresh_choices(candidates, incidents[:3], "incidents")
    assert [c.base for c in fresh if c.pool == "incidents"] == [incidents[3]]
    assert not {c.base for c in fresh} & set(incidents[:3])
    # набор рубрики исчерпан — забываем самого дальнего соседа, но не ближайшего
    fresh = fresh_choices(candidates, incidents + ["covers/florida"], "incidents")
    assert incidents[0] not in {c.base for c in fresh}
    assert [c.base for c in fresh if c.pool == "incidents"] == [incidents[3]]


def test_fresh_choices_with_single_cover_pool_still_differs_from_nearest():
    from news.covers import Cover, fresh_choices
    only, other = Cover("covers/x", False), Cover("covers/florida", False)
    assert fresh_choices([only, other], ["covers/x"], "x") == [other]
    assert fresh_choices([only], ["covers/x"], "x") == [only]  # больше ставить нечего


def test_neighbour_covers_nearest_first_same_topic_and_feed():
    from news.models import neighbour_covers
    incidents, roads = Topic.objects.get(slug="incidents"), Topic.objects.get(slug="roads")
    published("ЧП старое", incidents, 50, cover_image="covers/incidents-2")
    published("Дорога", roads, 5, cover_image="covers/roads-2")
    published("ЧП свежее", incidents, 10, cover_image="covers/incidents-photo-1")
    Article.objects.create(title="На проверке", teaser="t", body="b", topic=incidents,
                           cover_image="covers/incidents-3")
    assert neighbour_covers(incidents) == ["covers/roads-2", "covers/incidents-photo-1", "covers/incidents-2"]


def test_writer_is_offered_only_covers_not_used_by_neighbours():
    from unittest import mock

    from pipeline.schemas import CoverChoice
    from pipeline.services import choose_cover
    incidents = Topic.objects.get(slug="incidents")
    published("Перестрелка", incidents, 10, cover_image="covers/incidents-photo-1")
    article = Article.objects.create(title="Авария", teaser="t", body="b", topic=incidents)
    with mock.patch("pipeline.services.ai.ask", return_value=CoverChoice(cover="covers/incidents-photo-1")) as ask:
        assert choose_cover(article) == ""  # повтор соседа не принимаем, даже если ИИ его вернул
    offered = ask.call_args.kwargs["user"]
    assert "covers/incidents-photo-1 —" not in offered and "covers/incidents-3 —" in offered


def test_feed_of_one_topic_has_no_repeats_in_a_row():
    from pipeline.services import publish_article
    for topic, window in (("incidents", 4), ("weather", 5)):
        topic = Topic.objects.get(slug=topic)
        # ИИ каждый раз выбирает одну и ту же «лучшую» картинку — публикация её всё равно заменит
        best = cover_pools()[topic.slug][-1].base
        for i in range(12):
            publish_article(Article.objects.create(title=f"{topic.slug} {i}", teaser="t", body="b", topic=topic,
                                                   cover_image=best if i % 2 else ""))
        feed = [a.cover for a in Article.objects.filter(topic=topic).order_by("published_at")]
        for i in range(len(feed) - window + 1):
            assert len(set(feed[i:i + window])) == window, (topic.slug, feed)


def test_publish_keeps_manual_cover():
    from pipeline.services import publish_article
    incidents = Topic.objects.get(slug="incidents")
    published("Перестрелка", incidents, 10, cover_image="covers/incidents-photo-1")
    article = Article.objects.create(title="Авария", teaser="t", body="b", topic=incidents,
                                     cover_image="covers/incidents-photo-1", cover_manual=True)
    publish_article(article)
    article.refresh_from_db()
    assert article.cover_image == "covers/incidents-photo-1"


def test_fix_repeats_for_published_articles_skips_manual():
    from django.core.management import call_command
    incidents = Topic.objects.get(slug="incidents")
    same = "covers/incidents-photo-1"
    old = [published(f"ЧП {i}", incidents, 100 - i * 10, cover_image=same) for i in range(5)]
    manual = published("Вручную", incidents, 40, cover_image=same, cover_manual=True)
    call_command("pick_covers", "--fix-repeats", "--no-ai", stdout=io.StringIO())
    feed = [a.cover for a in Article.objects.filter(topic=incidents).order_by("published_at")]
    assert all(a != b for a, b in zip(feed, feed[1:])), feed
    old[0].refresh_from_db()
    manual.refresh_from_db()
    assert old[0].cover_image == same  # самой первой повторять некого
    assert manual.cover_image == same and manual.cover_manual


def test_fix_repeats_asks_ai_first():
    from unittest import mock

    from pipeline.services import fix_repeated_covers
    incidents = Topic.objects.get(slug="incidents")
    first = published("ЧП 1", incidents, 20, cover_image="covers/incidents-photo-1")
    second = published("ЧП 2", incidents, 10, cover_image="covers/incidents-photo-1")
    with mock.patch("pipeline.services.choose_cover", return_value="covers/incidents-3") as choose:
        run = fix_repeated_covers([second, first])
    choose.assert_called_once_with(second)
    assert run.stats["covers_changed"] == 1 and "incidents-photo-1 → covers/incidents-3" in run.log


def test_cover_set_by_hand_via_api_is_marked_manual():
    from django.contrib.auth.models import User
    from rest_framework.authtoken.models import Token
    from rest_framework.test import APIClient
    client = APIClient()
    staff = User.objects.create_user("editor", password="x", is_staff=True)
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=staff).key}")
    data = client.post("/api/v1/articles/", {"title": "З", "teaser": "a", "body": "b",
                                             "cover_image": "covers/florida-2"}, format="json").json()
    assert data["cover_manual"] is True
    data = client.patch(f"/api/v1/articles/{data['id']}/", {"cover_image": ""}, format="json").json()
    assert data["cover_manual"] is False


def test_cover_picked_in_admin_is_marked_manual(admin_client):
    article = published("Дорога", Topic.objects.get(slug="roads"), 5, slug="doroga")
    resp = admin_client.post(f"/admin/news/article/{article.pk}/change/", {
        "title": article.title, "teaser": article.teaser, "body": article.body, "for_you": "",
        "status": "published", "slug": article.slug, "published_at_0": "17.10.2026", "published_at_1": "10:00:00",
        "cover_image": "covers/roads-2", "score": "", "review_reason": "",
        "sources-TOTAL_FORMS": "0", "sources-INITIAL_FORMS": "0", "sources-MIN_NUM_FORMS": "0",
        "sources-MAX_NUM_FORMS": "1000",
    })
    assert resp.status_code == 302, resp.content.decode()[:2000]
    article.refresh_from_db()
    assert article.cover_image == "covers/roads-2" and article.cover_manual
    assert 'name="cover_manual"' in admin_client.get(f"/admin/news/article/{article.pk}/change/").content.decode()


def test_migration_marks_covers_picked_by_people(admin_user):
    import importlib

    from django.apps import apps
    from django.contrib.admin.models import CHANGE, LogEntry

    from news.models import Story
    migration = importlib.import_module("news.migrations.0012_article_cover_manual")
    by_ai, in_admin = (Article.objects.create(title=f"ИИ {n}", teaser="t", body="b", cover_image="covers/roads-2",
                                              story=Story.objects.create(title=f"Сюжет {n}")) for n in range(2))
    via_api = Article.objects.create(title="API", teaser="t", body="b", cover_image="covers/florida-2")
    LogEntry.objects.log_actions(admin_user.pk, [in_admin], CHANGE, single_object=True,
                                 change_message=[{"changed": {"fields": ["обложка"]}}])
    migration.mark_manual_covers(apps, None)
    for article, manual in ((by_ai, False), (in_admin, True), (via_api, True)):
        article.refresh_from_db()
        assert article.cover_manual is manual, article.title

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

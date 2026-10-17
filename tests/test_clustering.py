import pytest

from core.text import jaccard, make_slug, title_tokens
from news.models import Story
from pipeline.clustering import cluster_items
from sources.fetch import parse_feed, store_items

from .helpers import fixture_bytes, make_source

pytestmark = pytest.mark.django_db


def test_title_tokens_stem_and_stopwords():
    assert title_tokens("Evacuations ordered in Pinellas") == title_tokens("Evacuation ordered for Pinellas")
    assert "the" not in title_tokens("The storm")


def test_same_story_from_two_outlets_is_merged():
    orlando = make_source()
    state = make_source(name="State", url="https://example-state.test/feed")
    store_items(orlando, parse_feed(fixture_bytes("orlando_rss.xml")), limit=30)
    store_items(state, parse_feed(fixture_bytes("state_atom.xml")), limit=30)

    stats = cluster_items()
    assert stats == {"attached": 1, "new_stories": 2}
    boil = Story.objects.get(items__guid="orl-1001")
    assert sorted(boil.items.values_list("source__name", flat=True)) == ["State", "Test Orlando"]


def test_clustering_is_idempotent():
    source = make_source()
    store_items(source, parse_feed(fixture_bytes("orlando_rss.xml")), limit=30)
    cluster_items()
    assert cluster_items() == {"attached": 0, "new_stories": 0}
    assert Story.objects.count() == 2


def test_slug_transliteration():
    assert make_slug("Ураган «Милтон» идёт на Тампу!") == "uragan-milton-idyot-na-tampu"
    assert make_slug("Їжак і ґанок") == "yizhak-i-ganok"


def test_jaccard_bounds():
    assert jaccard(set(), {"a"}) == 0
    assert jaccard({"a", "b"}, {"a", "b"}) == 1

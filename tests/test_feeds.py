import pytest
import requests

from sources.fetch import clean_text, fetch_all, fetch_source, parse_feed, store_items, sync_nws_alerts, check_source
from sources.models import FeedItem, Source, WeatherAlert

from .helpers import FakeResponse, FakeSession, fixture_bytes, make_source

pytestmark = pytest.mark.django_db


def test_parse_rss_fixture():
    items = parse_feed(fixture_bytes("orlando_rss.xml"))
    assert [i["guid"] for i in items] == ["orl-1001", "orl-1002"]  # запись без заголовка пропущена
    first = items[0]
    assert first["title"] == "Orange County issues boil water notice after main break"
    assert first["summary"] == "Residents east of Semoran Blvd should boil water for at least one minute."
    assert first["published_at"].isoformat() == "2026-10-17T12:00:00+00:00"


def test_parse_atom_fixture():
    items = parse_feed(fixture_bytes("state_atom.xml"))
    assert len(items) == 1
    assert items[0]["url"] == "https://example-state.test/boil-water"
    assert items[0]["guid"] == "urn:test:state:1"


def test_parse_rejects_html():
    with pytest.raises(ValueError):
        parse_feed(b"<html><body>Not a feed</body></html>")


def test_clean_text_truncates_on_word():
    text = clean_text("<p>" + "слово " * 400 + "</p>", limit=50)
    assert len(text) <= 51 and text.endswith("…")


def test_store_items_is_idempotent():
    source = make_source()
    items = parse_feed(fixture_bytes("orlando_rss.xml"))
    first = store_items(source, items, limit=30)
    second = store_items(source, items, limit=30)
    assert first.created == 2 and second.created == 0 and second.skipped == 2
    assert FeedItem.objects.count() == 2


def test_fetch_source_uses_conditional_headers_and_304():
    source = make_source()
    session = FakeSession({source.url: FakeResponse(
        fixture_bytes("orlando_rss.xml"), headers={"ETag": '"abc"', "Last-Modified": "Fri, 17 Oct 2026 12:00:00 GMT"},
    )})
    result = fetch_source(source, session)
    assert result.created == 2
    source.refresh_from_db()
    assert source.etag == '"abc"' and source.last_success_at is not None

    session.routes[source.url] = FakeResponse(status=304)
    result = fetch_source(source, session)
    assert result.not_modified
    assert session.calls[-1][1]["If-None-Match"] == '"abc"'


def test_failing_source_marked_broken_after_three_errors_and_others_continue():
    bad = make_source(name="Bad", url="https://bad.test/rss")
    good = make_source(name="Good", url="https://good.test/rss")
    session = FakeSession({
        bad.url: requests.ConnectionError("boom"),
        good.url: FakeResponse(fixture_bytes("orlando_rss.xml")),
    })
    for _ in range(3):
        results = fetch_source(bad, session), fetch_source(good, session)
        assert results[0].error and not results[1].error
    bad.refresh_from_db()
    assert bad.is_broken and bad.consecutive_failures == 3
    # сломанный источник не опрашивается в общем сборе
    import sources.fetch as fetch_module
    original = fetch_module.make_session
    fetch_module.make_session = lambda: session
    try:
        names = [r.source.name for r in fetch_all()]
    finally:
        fetch_module.make_session = original
    assert "Good" in names and "Bad" not in names


def test_success_resets_failure_counter():
    source = make_source()
    source.record_failure("x")
    session = FakeSession({source.url: FakeResponse(fixture_bytes("orlando_rss.xml"))})
    fetch_source(source, session)
    source.refresh_from_db()
    assert source.consecutive_failures == 0 and source.last_error == ""


def test_nws_alerts_go_to_weather_block_and_severe_to_pipeline():
    import json
    source = make_source(name="NWS", url="https://api.weather.gov/alerts/test",
                         kind=Source.Kind.NWS_ALERTS, source_type=Source.SourceType.WEATHER)
    features = json.loads(fixture_bytes("nws_alerts.json"))["features"]
    result = sync_nws_alerts(source, features)
    assert result.alerts == 2
    assert WeatherAlert.objects.filter(is_active=True).count() == 2
    hurricane = WeatherAlert.objects.get(event="Hurricane Warning")
    assert hurricane.event_ru == "Предупреждение об урагане"
    # только опасное событие становится записью для конвейера
    assert list(FeedItem.objects.values_list("title", flat=True)) == ["Hurricane Warning issued for Pinellas"]

    # предупреждение пропало из фида — гасим его
    sync_nws_alerts(source, features[:1])
    assert not WeatherAlert.objects.get(event="Rip Current Statement").is_active
    assert FeedItem.objects.count() == 1  # повтор не создаёт дублей


def test_check_source_detects_non_feed():
    source = make_source()
    session = FakeSession({source.url: FakeResponse(b"<html>hello</html>", headers={"Content-Type": "text/html"})})
    ok, detail = check_source(source, session)
    assert not ok and "не RSS" in detail
    session.routes[source.url] = FakeResponse(fixture_bytes("orlando_rss.xml"))
    ok, detail = check_source(source, session)
    assert ok and "записей: 2" in detail


def test_seeded_sources_are_inactive_until_verified():
    # включён сразу только IRS: его ленту проверили при добавлении (миграция sources 0003)
    assert list(Source.objects.filter(is_active=True).values_list("name", flat=True)) == ["IRS (налоговая служба США)"]
    assert Source.objects.filter(is_verified=False).count() >= 15


def test_bing_news_redirect_unwrapped_to_original():
    from sources.fetch import unwrap_link

    bing = ("http://www.bing.com/news/apiclick.aspx?ref=FexRss&aid=&tid=abc"
            "&url=https%3a%2f%2fwww.irs.gov%2fnewsroom%2firs-relief&c=1")
    assert unwrap_link(bing) == "https://www.irs.gov/newsroom/irs-relief"
    assert unwrap_link("https://www.wfla.com/a") == "https://www.wfla.com/a"
    assert unwrap_link("http://www.bing.com/news/apiclick.aspx?url=javascript%3aalert(1)").startswith("http://www.bing")

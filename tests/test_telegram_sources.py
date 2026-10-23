"""Публичные Telegram-каналы как полноценные источники: посты → записи ленты → обычный конвейер."""

from types import SimpleNamespace
from unittest import mock

import pytest
from django.utils import timezone

from social import collectors
from social.collectors import TgPost
from sources.fetch import check_source, fetch_all, telegram_item
from sources.models import FeedItem, Source

pytestmark = pytest.mark.django_db

CHANNELS = {"GolosAmeriki", "news_about_USA", "kontinentusa", "icemlaw1", "expatfm", "usaonenews"}


def post(n, text, username="GolosAmeriki"):
    return TgPost(id=n, url=f"https://t.me/{username}/{n}", text=text, author="Голос Америки", date=timezone.now())


def test_six_channels_are_seeded_active_and_verified():
    channels = Source.objects.filter(kind=Source.Kind.TELEGRAM)
    assert {s.url.removeprefix("https://t.me/") for s in channels} == CHANNELS
    assert all(s.is_active and s.is_verified and s.source_type == Source.SourceType.MEDIA for s in channels)


def test_post_becomes_feed_item_with_first_line_as_title():
    item = telegram_item(post(7, "\n❗️ Суд разрешил содержать мигрантов под стражей\n\nПодробности решения…"))
    assert item["title"] == "❗️ Суд разрешил содержать мигрантов под стражей"
    assert item["url"] == item["guid"] == "https://t.me/GolosAmeriki/7"
    assert "Подробности решения" in item["summary"]


def test_fetch_all_reads_channels_in_one_session_and_dedupes():
    golos = Source.objects.get(url="https://t.me/GolosAmeriki")
    expat = Source.objects.get(url="https://t.me/expatfm")
    calls = []

    async def fake_read(jobs, limit, max_text):
        calls.append({j[1] for j in jobs})
        return {golos.pk: [post(1, "Около 20 млн избирателей уже проголосовали"), post(2, "Новые правила для виз")],
                expat.pk: collectors.CollectorError("канал недоступен")}

    with mock.patch.object(collectors, "read_channels", fake_read), \
            mock.patch("sources.fetch.make_session"):
        results = fetch_all(Source.objects.filter(pk__in=[golos.pk, expat.pk]))
        fetch_all(Source.objects.filter(pk__in=[golos.pk, expat.pk]))  # повторный сбор — без дублей
    assert calls[0] == {"GolosAmeriki", "expatfm"}  # одно подключение на все каналы
    assert FeedItem.objects.filter(source=golos).count() == 2
    golos.refresh_from_db()
    expat.refresh_from_db()
    assert golos.last_success_at and expat.consecutive_failures == 2 and "недоступен" in expat.last_error
    assert {r.source.pk: r.created for r in results} == {golos.pk: 2, expat.pk: 0}


def test_missing_session_does_not_break_other_sources():
    golos = Source.objects.get(url="https://t.me/GolosAmeriki")

    async def no_session(jobs, limit, max_text):
        raise collectors.CollectorError("TG_SESSION не задан")

    with mock.patch.object(collectors, "read_channels", no_session):
        [result] = fetch_all(Source.objects.filter(pk=golos.pk))
    assert "TG_SESSION" in result.error and not FeedItem.objects.exists()


def test_check_source_for_channel():
    golos = Source.objects.get(url="https://t.me/GolosAmeriki")

    async def fake_read(jobs, limit, max_text):
        return {golos.pk: [post(3, "Выборы: явка рекордная")]}

    with mock.patch.object(collectors, "read_channels", fake_read):
        ok, detail = check_source(golos)
    assert ok and "публичный канал" in detail and "Выборы" in detail

    async def private(jobs, limit, max_text):
        return {golos.pk: collectors.CollectorError("это не публичный канал")}

    with mock.patch.object(collectors, "read_channels", private):
        assert check_source(golos)[0] is False


def test_long_posts_keep_full_summary():
    channel = SimpleNamespace(broadcast=True, megagroup=False, username="GolosAmeriki", title="Голос Америки")
    long_text = "Заголовок поста\n" + "слово " * 400

    class Client:
        async def get_entity(self, username):
            return channel

        async def iter_messages(self, entity, limit, min_id):
            yield SimpleNamespace(id=9, message=long_text, date=timezone.now())

    import asyncio
    [p] = asyncio.run(collectors.read_channel(Client(), "GolosAmeriki", 0, 10, max_text=1000))
    assert len(p.text) == 1000  # для источников — до 1000 знаков, для сигналов по-прежнему 500

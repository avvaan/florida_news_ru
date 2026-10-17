"""Этап «Сигналы из соцсетей»: все внешние API заменены заглушками."""

import asyncio
import io
import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from core.models import SiteSettings
from news.models import Article, Region, Story
from pipeline import ai
from pipeline.decisions import decide
from pipeline.models import AICall
from pipeline.schemas import Classification, Draft, Verification
from pipeline.services import RunLog, run_pipeline
from social import collectors
from social.models import Hint, Signal, SignalSource
from social.schemas import HintMatch, HintMatches, NewHint, SignalVerdict, Triage
from social.services import confirm_hints, run_social, triage_new
from sources.models import FeedItem, Source

from .helpers import fake_deepseek_response, make_source

pytestmark = pytest.mark.django_db

BODY = " ".join(["слово"] * 100)
KEYS = dict(PERPLEXITY_API_KEY="pk", XAI_API_KEY="xk", AI_PROVIDER="deepseek")


class FakeDeepSeek:
    """DeepSeek-заглушка: отвечает по схеме из системного промпта."""

    def __init__(self, answers):
        self.answers = answers  # схема -> ответ (модель или функция от текста запроса)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        system, user = kwargs["messages"][0]["content"], kwargs["messages"][1]["content"]
        schema = next(s for s in self.answers if json.dumps(s.model_json_schema(), ensure_ascii=False) in system)
        self.calls.append({"schema": schema, "system": system, "user": user})
        answer = self.answers[schema]
        answer = answer(user) if callable(answer) else answer
        return fake_deepseek_response(answer.model_dump_json())


def responses_api(items=None, *, links=(), text=None, usage=(800, 400)):
    """Ответ в форме Responses API (Perplexity Agent API / xAI)."""
    output_text = text if text is not None else json.dumps({"items": items or []}, ensure_ascii=False)
    return {
        "status": "completed",
        "output": [
            {"type": "search_results", "results": [dict(link) for link in links]},
            {"type": "message", "content": [{"type": "output_text", "text": output_text, "annotations": []}]},
        ],
        "usage": {"input_tokens": usage[0], "output_tokens": usage[1]},
    }


def trusted_story(title="Miami-Dade issues boil water notice for Little Havana", source_type=Source.SourceType.MEDIA):
    source = make_source(name=f"S {source_type}", url=f"https://{source_type}.test/rss", source_type=source_type)
    story = Story.objects.create(title=title)
    FeedItem.objects.create(source=source, guid=title, url="https://local10.test/a", title=title, story=story,
                            published_at=timezone.now())
    return story


def make_signal(text="Во Флориде обсуждают новость", url="https://x.com/someone/status/1", kind="grok"):
    source = SignalSource.objects.filter(kind=kind).first()
    return Signal.objects.create(source=source, url=url, text=text)


# --- Сборщики --------------------------------------------------------------------

@override_settings(**KEYS)
def test_perplexity_saves_items_links_and_cost():
    data = responses_api([
        {"url": "https://www.local10.test/news/boil", "title": "Кипятите воду в Литл-Гаване",
         "summary": "Округ ввёл предписание.", "author": "Local 10", "published": "2026-10-17T08:00:00-04:00"},
        {"url": "not-a-link", "title": "без ссылки"},
    ])
    with mock.patch.object(collectors, "post_json", return_value=data) as post:
        stats = collectors.collect_search(SignalSource.Kind.PERPLEXITY, RunLog())
    assert stats == {"created": 1, "failed": 0}  # все 5 запросов вернули одну и ту же ссылку — дубль не сохраняется
    body = post.call_args.args[2]
    assert post.call_args.args[0] == "https://api.perplexity.ai/v1/responses"
    assert body["model"] == "perplexity/sonar" and body["tools"] == [{"type": "web_search"}]
    signal = Signal.objects.get()
    assert signal.text.startswith("Кипятите воду") and signal.author == "Local 10" and signal.published_at
    assert signal.region == signal.source.region and signal.status == Signal.Status.NEW  # регион запроса
    calls = AICall.objects.filter(purpose="signals")
    assert calls.count() == 5
    # токены + плата за запрос: (800 * 1.00 + 400 * 1.00) / 1e6 + 0.012
    assert calls.first().cost_usd == Decimal("0.013200")


@override_settings(**KEYS)
def test_perplexity_falls_back_to_search_results_when_text_is_not_json():
    data = responses_api(text="Вот что происходит во Флориде…", links=[
        {"url": "https://wesh.test/orlando-fair", "title": "Orlando fair opens", "snippet": "Free entry", "date": "2026-10-17"},
    ])
    with mock.patch.object(collectors, "post_json", return_value=data):
        collectors.collect_search(SignalSource.Kind.PERPLEXITY, RunLog())
    signal = Signal.objects.get()
    assert signal.url == "https://wesh.test/orlando-fair" and signal.text == "Orlando fair opens — Free entry"


@override_settings(**KEYS)
def test_grok_uses_x_search_and_takes_author_from_post_url():
    data = responses_api(text="", links=[{"url": "https://x.com/MiamiDadeCounty/status/123", "title": "Boil water"}])
    with mock.patch.object(collectors, "post_json", return_value=data) as post:
        collectors.collect_search(SignalSource.Kind.GROK, RunLog())
    tool = post.call_args.args[2]["tools"][0]
    assert post.call_args.args[0] == "https://api.x.ai/v1/responses" and tool["type"] == "x_search"
    assert tool["from_date"] < tool["to_date"]
    assert Signal.objects.get().author == "@MiamiDadeCounty"


@override_settings(**KEYS)
def test_failed_search_is_recorded_and_not_billed():
    with mock.patch.object(collectors, "post_json", side_effect=collectors.CollectorError("HTTP 401: bad key")):
        stats = collectors.collect_search(SignalSource.Kind.PERPLEXITY, RunLog())
    assert stats["failed"] == 5 and not Signal.objects.exists()
    source = SignalSource.objects.filter(kind="perplexity").first()
    assert source.consecutive_failures == 1 and "401" in source.last_error
    assert AICall.objects.filter(success=False, cost_usd=0).count() == 5


@override_settings(**KEYS, SIGNALS_BUDGET_SHARE=0.5)
def test_signals_stop_at_their_share_of_daily_budget():
    SiteSettings.objects.update(ai_budget_per_day_usd=Decimal("1.00"))
    AICall.objects.create(purpose="write", model="x", cost_usd=Decimal("0.60"))
    with mock.patch.object(collectors, "post_json") as post:
        say = RunLog()
        collectors.collect_search(SignalSource.Kind.PERPLEXITY, say)
    assert not post.called and "доля дневного бюджета" in say.text()


@override_settings(**KEYS)
def test_disabled_collectors_make_no_requests():
    with mock.patch.object(collectors, "post_json") as post, \
            mock.patch.object(collectors, "read_channels") as tg:
        run_social(RunLog())
        call_command("collect_perplexity", stdout=io.StringIO())
    assert not post.called and not tg.called


def test_telegram_reads_only_public_broadcast_channels():
    now = timezone.now()

    class Client:
        def __init__(self, entity):
            self.entity = entity

        async def get_entity(self, username):
            return self.entity

        async def iter_messages(self, entity, limit, min_id):
            for msg in (SimpleNamespace(id=11, message="Пробки на I-4 после аварии", date=now),
                        SimpleNamespace(id=10, message="", date=now),  # только фото — пропускаем
                        SimpleNamespace(id=9, message="старое", date=now - timedelta(days=3))):
                yield msg

    channel = SimpleNamespace(broadcast=True, megagroup=False, username="orlando_ru", title="Орландо по-русски")
    posts = asyncio.run(collectors.read_channel(Client(channel), "orlando_ru", 0, 20))
    assert [(p.id, p.url) for p in posts] == [(11, "https://t.me/orlando_ru/11")]

    for entity in (SimpleNamespace(broadcast=False, megagroup=True, username="chat"),  # группа
                   SimpleNamespace(first_name="Иван", username="ivan"),  # пользователь
                   SimpleNamespace(broadcast=True, megagroup=False, username=None)):  # закрытый канал
        with pytest.raises(collectors.CollectorError, match="не публичный канал"):
            asyncio.run(collectors.read_channel(Client(entity), "x", 0, 20))


def test_collect_telegram_stores_posts_and_remembers_last_id():
    source = SignalSource.objects.create(name="Орландо RU", kind="telegram", query="https://t.me/orlando_ru",
                                         region=Region.objects.get(slug="orlando"))
    broken = SignalSource.objects.create(name="Чат", kind="telegram", query="@some_chat")
    post = collectors.TgPost(id=42, url="https://t.me/orlando_ru/42", text="Пробки на I-4",
                             author="Орландо по-русски", date=timezone.now())

    async def fake_read(jobs, limit):
        assert (source.pk, "orlando_ru", 0) in jobs
        return {source.pk: [post], broken.pk: collectors.CollectorError("это не публичный канал")}

    with mock.patch.object(collectors, "read_channels", fake_read):
        stats = collectors.collect_telegram(RunLog())
    assert stats == {"created": 1, "failed": 1}
    source.refresh_from_db()
    broken.refresh_from_db()
    assert source.last_message_id == 42 and Signal.objects.get().region.slug == "orlando"
    assert "не публичный" in broken.last_error


# --- Разбор и подтверждение --------------------------------------------------------

@override_settings(AI_PROVIDER="deepseek")
def test_triage_sorts_noise_story_and_new_hint():
    story = trusted_story()
    ad = make_signal("Скидки на окна!", "https://x.com/shop/status/1")
    same = make_signal("В Литл-Гаване просят кипятить воду", "https://x.com/a/status/2")
    new1 = make_signal("Жители Тампы жалуются на запах с залива", "https://x.com/b/status/3")
    new2 = make_signal("Странный запах в Тампе второй день", "https://x.com/c/status/4")
    triage = Triage(
        signals=[
            SignalVerdict(id=ad.pk, interesting=False, story_id=None, hint_id=None, group=None, region="florida", topic="other"),
            SignalVerdict(id=same.pk, interesting=True, story_id=story.pk, hint_id=None, group=None, region="miami", topic="safety"),
            SignalVerdict(id=new1.pk, interesting=True, story_id=None, hint_id=None, group="tampa-smell", region="tampa", topic="health"),
            SignalVerdict(id=new2.pk, interesting=True, story_id=None, hint_id=None, group="tampa-smell", region="tampa", topic="health"),
            SignalVerdict(id=999, interesting=True, story_id=None, hint_id=None, group="ghost", region="tampa", topic="other"),
        ],
        new_hints=[NewHint(group="tampa-smell", title="Запах в районе Тампа-Бэй",
                           summary="Жители обсуждают неприятный запах у залива; причины официально не названы.")],
    )
    fake = FakeDeepSeek({Triage: triage})
    with mock.patch.object(ai, "get_client", return_value=fake):
        stats = triage_new(RunLog())
    assert stats == {"noise": 1, "to_story": 1, "to_hint": 2, "new_hints": 1}
    for s in (ad, same, new1, new2):
        s.refresh_from_db()
    assert ad.status == "noise" and same.story == story
    assert new1.hint == new2.hint and new1.hint.title == "Запах в районе Тампа-Бэй" and new1.region.slug == "tampa"
    assert f"[{story.pk}] Miami-Dade issues boil water notice" in fake.calls[0]["user"]
    assert AICall.objects.get().purpose == "triage"


@override_settings(AI_PROVIDER="deepseek")
def test_hint_is_confirmed_only_by_media_or_official_story():
    hint = Hint.objects.create(title="Запах в районе Тампа-Бэй", summary="Жители обсуждают запах.")
    signal = make_signal()
    signal.hint, signal.status = hint, Signal.Status.HINT
    signal.save()
    story = trusted_story("Red tide causes odor along Tampa Bay beaches", Source.SourceType.OFFICIAL)
    other = Story.objects.create(title="Story without any items")  # не от СМИ — не кандидат

    def matches(user):
        assert story.title in user and other.title not in user
        return HintMatches(matches=[HintMatch(hint_id=hint.pk, story_id=story.pk)])

    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({HintMatches: matches})):
        stats = confirm_hints(RunLog())
    hint.refresh_from_db()
    signal.refresh_from_db()
    assert stats["confirmed"] == 1 and hint.status == "confirmed" and hint.story == story
    assert signal.story == story  # сюжет получает пометку «обсуждают в соцсетях»


def test_old_hints_expire_without_ai_call():
    Hint.objects.create(title="Старое", created_at=timezone.now() - timedelta(hours=49))
    with mock.patch.object(ai, "get_client") as client:
        stats = confirm_hints(RunLog())
    assert stats["expired"] == 1 and not client.called


# --- Правило публикации ------------------------------------------------------------

def test_no_publication_without_media_or_official_source_even_without_review():
    decision = decide(score=10, is_urgent=True, is_sensitive=False, has_official_source=False, verified_ok=True,
                      verifier_confidence=1.0, issues=[], insufficient_facts=False, auto_publish_enabled=True,
                      auto_publish_min_score=1, min_confidence=0.5, publish_without_review=True,
                      has_trusted_source=False)
    assert not decision.publish and "СМИ или официального" in decision.reason


@override_settings(AI_PROVIDER="deepseek")
def test_confirmed_hint_story_is_written_from_sources_with_social_context():
    story = trusted_story()
    hint = Hint.objects.create(title="Кипятите воду", summary="В соцсетях обсуждают предписание кипятить воду.",
                               status=Hint.Status.CONFIRMED, story=story)
    signal = make_signal()
    Signal.objects.filter(pk=signal.pk).update(story=story, hint=hint, status=Signal.Status.HINT)
    fake = FakeDeepSeek({
        Classification: Classification(score=8, topic="safety", region="miami", is_urgent=False,
                                        is_sensitive=False, reason="ЖКХ"),
        Draft: Draft(title="В Литл-Гаване кипятите воду", teaser="Предписание округа", body=BODY,
                     tags=["ЖКХ"], insufficient_facts=False, cover="covers/safety-3"),
        Verification: Verification(ok=True, confidence=0.95, issues=[]),
    })
    with mock.patch.object(ai, "get_client", return_value=fake):
        run = run_pipeline(fetch=False)
    assert run.success and Article.objects.get(story=story).status == Article.Status.PUBLISHED
    classify = next(c for c in fake.calls if c["schema"] is Classification)
    write = next(c for c in fake.calls if c["schema"] is Draft)
    verify = next(c for c in fake.calls if c["schema"] is Verification)
    assert "Обсуждают в соцсетях: сообщений — 1." in classify["user"]
    assert "НЕ источник фактов" in write["user"] and "обсуждают предписание" in write["user"]
    assert "обсуждают предписание" not in verify["user"]  # проверка сверяет только с источниками
    assert "Во Флориде обсуждают новость" not in write["user"]  # текст постов автору не передаётся


@override_settings(**KEYS)
def test_pipeline_runs_social_stage_when_enabled():
    SiteSettings.objects.update(signals_perplexity_enabled=True)
    data = responses_api([{"url": "https://local10.test/x", "title": "Новость", "summary": "Суть."}])
    triage = lambda user: Triage(  # noqa: E731
        signals=[SignalVerdict(id=s.pk, interesting=False, story_id=None, hint_id=None, group=None,
                               region="florida", topic="other") for s in Signal.objects.all()],
        new_hints=[])
    with mock.patch.object(collectors, "post_json", return_value=data), \
            mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({Triage: triage})):
        run = run_pipeline(fetch=False)
    assert run.success and run.stats["signals_new"] == 1 and run.stats["noise"] == 1
    assert "Соцсети: новых сигналов 1" in run.log


def test_social_admin_pages_open(admin_client):
    hint = Hint.objects.create(title="Тема")
    signal = make_signal()
    for url in ("/admin/social/signalsource/", "/admin/social/signal/", "/admin/social/hint/",
                f"/admin/social/hint/{hint.pk}/change/", f"/admin/social/signal/{signal.pk}/change/",
                "/admin/core/sitesettings/1/change/"):
        assert admin_client.get(url, follow=True).status_code == 200, url

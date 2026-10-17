import json
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest

from django.test import override_settings

from core.models import SiteSettings
from news.models import Article, Story
from pipeline import ai
from pipeline.clustering import cluster_items
from pipeline.models import AICall
from pipeline.schemas import Classification, Draft, Verification
from pipeline.services import RunLog, classify_new, run_pipeline, write_pending
from sources.fetch import parse_feed, store_items
from sources.models import Source

from .helpers import fake_ai_response, fake_deepseek_response, fixture_bytes, make_source

pytestmark = pytest.mark.django_db

BODY = " ".join(["слово"] * 100)


class FakeAI:
    """Отвечает по типу запрошенной схемы в форме DeepSeek или Anthropic. Ничего не шлёт в сеть."""

    def __init__(self, classification=None, draft=None, verification=None):
        self.classification = classification or Classification(
            score=8, topic="safety", region="orlando", is_urgent=False, is_sensitive=False, reason="ЖКХ")
        self.draft = draft or Draft(title="В Орландо кипятите воду", teaser="Предписание для части округа",
                                    body=BODY, tags=["ЖКХ", "Орландо"], insufficient_facts=False)
        self.verification = verification or Verification(ok=True, confidence=0.95, issues=[])
        self.calls = []
        self.messages = self  # Anthropic: client.messages.parse
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))  # DeepSeek

    def answer_for(self, schema):
        return {Classification: self.classification, Draft: self.draft, Verification: self.verification}[schema]

    @staticmethod
    def schema_from_prompt(system: str):
        for schema in (Classification, Draft, Verification):
            if json.dumps(schema.model_json_schema(), ensure_ascii=False) in system:
                return schema
        raise AssertionError("в системном промпте нет JSON-схемы")

    def create(self, **kwargs):
        self.calls.append(kwargs)
        schema = self.schema_from_prompt(kwargs["messages"][0]["content"])
        kwargs["schema"] = schema
        return fake_deepseek_response(self.answer_for(schema).model_dump_json())

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        kwargs["schema"] = kwargs["output_format"]
        return fake_ai_response(self.answer_for(kwargs["output_format"]))


@pytest.fixture
def stories():
    source = make_source()
    store_items(source, parse_feed(fixture_bytes("orlando_rss.xml")), limit=30)
    FeedItemTime = source.items.model
    from django.utils import timezone
    FeedItemTime.objects.update(published_at=timezone.now())  # свежие, чтобы не отсеялись как устаревшие
    cluster_items()
    return source


def run_with(fake):
    with mock.patch.object(ai, "get_client", return_value=fake):
        say = RunLog()
        classify_new(say)
        write_pending(say)
    return say


@override_settings(AI_PROVIDER="deepseek", AI_CLASSIFIER_MODEL="deepseek-flash",
                   AI_VERIFIER_MODEL="deepseek-flash", AI_WRITER_MODEL="deepseek-v4-pro")
def test_full_flow_publishes_and_logs_costs(stories):
    fake = FakeAI()
    run_with(fake)
    assert Article.objects.filter(status=Article.Status.PUBLISHED).count() == 2
    article = Article.objects.first()
    assert article.sources.count() == 1 and article.tags.count() == 2
    assert article.slug.startswith("v-orlando-kipyatite-vodu")
    # 2 сюжета × (отбор + написание + проверка)
    assert AICall.objects.count() == 6
    assert AICall.objects.filter(purpose="write", model="deepseek-v4-pro").count() == 2
    call = AICall.objects.filter(purpose="classify").first()
    assert (call.input_tokens, call.cache_read_tokens, call.output_tokens) == (300, 1200, 300)
    # flash: 300×0.30 + 1200×0.03 + 300×1.20 = 486 / 1e6
    assert call.cost_usd == Decimal("0.000486")
    assert AICall.objects.today().total_cost() > Decimal("0")
    first = fake.calls[0]
    assert first["response_format"] == {"type": "json_object"}
    assert first["model"] == "deepseek-flash"
    assert "JSON-схема" in first["messages"][0]["content"]


@override_settings(AI_PROVIDER="anthropic", AI_CLASSIFIER_MODEL="claude-haiku-4-5",
                   AI_VERIFIER_MODEL="claude-haiku-4-5", AI_WRITER_MODEL="claude-sonnet-5")
def test_anthropic_provider_still_works(stories):
    fake = FakeAI()
    run_with(fake)
    assert Article.objects.filter(status=Article.Status.PUBLISHED).count() == 2
    assert AICall.objects.filter(purpose="write", model="claude-sonnet-5").count() == 2
    # системный промпт помечен для кэширования
    assert fake.calls[0]["system"][0]["cache_control"] == {"type": "ephemeral"}
    # у Haiku 4.5 не передаём effort, у автора — передаём
    classify_call = next(c for c in fake.calls if c["schema"] is Classification)
    write_call = next(c for c in fake.calls if c["schema"] is Draft)
    assert "output_config" not in classify_call and write_call["output_config"] == {"effort": "medium"}


def review_mode():
    conf = SiteSettings.load()
    conf.publish_without_review = False
    conf.save()


def test_sensitive_story_goes_to_review(stories):
    review_mode()
    fake = FakeAI(classification=Classification(
        score=9, topic="incidents", region="orlando", is_urgent=False, is_sensitive=True, reason="криминал"))
    run_with(fake)
    assert Article.objects.filter(status=Article.Status.REVIEW).count() == 2
    assert "Чувствительная" in Article.objects.first().review_reason


def test_verifier_doubt_goes_to_review(stories):
    review_mode()
    fake = FakeAI(verification=Verification(ok=False, confidence=0.9, issues=["Выдуманная дата"]))
    run_with(fake)
    article = Article.objects.first()
    assert article.status == Article.Status.REVIEW and "Выдуманная дата" in article.review_reason


def test_publish_without_review_publishes_everything(stories):
    # по умолчанию включено: даже чувствительное и сомнительное идёт на сайт
    fake = FakeAI(
        classification=Classification(score=6, topic="incidents", region="orlando", is_urgent=False,
                                      is_sensitive=True, reason="криминал"),
        verification=Verification(ok=False, confidence=0.5, issues=["Неточная дата"]),
    )
    run_with(fake)
    assert Article.objects.filter(status=Article.Status.PUBLISHED).count() == 2
    article = Article.objects.first()
    assert article.review_reason == ""
    assert article.verification["decision"].startswith("Опубликовано без проверки")
    assert "Чувствительная" in article.verification["decision"]


def test_low_score_is_skipped_without_writing(stories):
    fake = FakeAI(classification=Classification(
        score=3, topic="other", region="orlando", is_urgent=False, is_sensitive=False, reason="мелочь"))
    run_with(fake)
    assert Article.objects.count() == 0
    assert Story.objects.filter(status=Story.Status.SKIPPED).count() == 2
    assert not any(c["schema"] is Draft for c in fake.calls)


def test_outside_florida_is_skipped(stories):
    fake = FakeAI(classification=Classification(
        score=9, topic="other", region="outside", is_urgent=False, is_sensitive=False, reason="не Флорида"))
    run_with(fake)
    assert Article.objects.count() == 0


def test_budget_exceeded_writes_only_urgent(stories):
    conf = SiteSettings.load()
    conf.ai_budget_per_day_usd = Decimal("0.00")
    conf.save()
    run_with(FakeAI())
    assert Article.objects.count() == 0
    assert Story.objects.filter(status=Story.Status.CLASSIFIED).count() == 2  # ждут в очереди

    urgent = FakeAI(classification=Classification(
        score=9, topic="safety", region="orlando", is_urgent=True, is_sensitive=False, reason="ЧП"))
    Story.objects.update(status=Story.Status.NEW)
    run_with(urgent)
    assert Article.objects.count() == 2


def test_nws_story_forced_urgent(stories):
    nws = make_source(name="NWS", url="https://api.weather.gov/alerts/test",
                      kind=Source.Kind.NWS_ALERTS, source_type=Source.SourceType.WEATHER)
    story = Story.objects.first()
    story.items.update(source=nws)
    fake = FakeAI(classification=Classification(
        score=4, topic="weather", region="tampa", is_urgent=False, is_sensitive=False, reason="погода"))
    run_with(fake)
    story.refresh_from_db()
    assert story.is_urgent and story.score >= 9
    assert story.article.status == Article.Status.PUBLISHED  # срочно + официальный источник


@override_settings(AI_PROVIDER="deepseek")
def test_ai_error_marks_story_failed_and_logs(stories):
    import httpx2 as httpx  # openai 3.x работает поверх httpx2
    import openai

    class Broken:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
            raise openai.APIConnectionError(request=request)

    run_with(Broken())
    assert Story.objects.filter(status=Story.Status.FAILED).count() == 2
    assert AICall.objects.filter(success=False).count() == 2


@override_settings(AI_PROVIDER="deepseek")
def test_invalid_json_is_retried_once(stories):
    fake = FakeAI()
    original = fake.create
    state = {"broken": 0}

    def flaky(**kwargs):
        if state["broken"] == 0:  # первый ответ — пустой, как иногда бывает у DeepSeek
            state["broken"] += 1
            fake.calls.append(kwargs)
            return fake_deepseek_response("")
        return original(**kwargs)

    fake.chat.completions.create = flaky
    run_with(fake)
    assert Article.objects.count() == 2
    assert AICall.objects.filter(success=False, error__icontains="JSON").count() == 1


@override_settings(AI_PROVIDER="deepseek")
def test_truncated_answer_is_not_used(stories):
    fake = FakeAI()
    original = fake.create

    def truncated(**kwargs):
        response = original(**kwargs)
        response.choices[0].finish_reason = "length"
        return response

    fake.chat.completions.create = truncated
    run_with(fake)
    assert Article.objects.count() == 0
    assert AICall.objects.filter(success=False, error__icontains="max_tokens").count() == 2


def test_run_pipeline_without_network_records_run(stories):
    with mock.patch.object(ai, "get_client", return_value=FakeAI()):
        run = run_pipeline(fetch=False)
    assert run.success and run.stats["written"] == 2 and "Опубликовано" in run.log

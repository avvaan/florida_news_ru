from decimal import Decimal
from unittest import mock

import pytest

from core.models import SiteSettings
from news.models import Article, Story
from pipeline import ai
from pipeline.clustering import cluster_items
from pipeline.models import AICall
from pipeline.schemas import Classification, Draft, Verification
from pipeline.services import RunLog, classify_new, run_pipeline, write_pending
from sources.fetch import parse_feed, store_items
from sources.models import Source

from .helpers import fake_ai_response, fixture_bytes, make_source

pytestmark = pytest.mark.django_db

BODY = " ".join(["слово"] * 100)


class FakeClaude:
    """Отвечает по типу запрошенной схемы. Ничего не отправляет в сеть."""

    def __init__(self, classification=None, draft=None, verification=None):
        self.classification = classification or Classification(
            score=8, topic="safety", region="orlando", is_urgent=False, is_sensitive=False, reason="ЖКХ")
        self.draft = draft or Draft(title="В Орландо кипятите воду", teaser="Предписание для части округа",
                                    body=BODY, tags=["ЖКХ", "Орландо"], insufficient_facts=False)
        self.verification = verification or Verification(ok=True, confidence=0.95, issues=[])
        self.calls = []
        self.messages = self

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        schema = kwargs["output_format"]
        parsed = {Classification: self.classification, Draft: self.draft, Verification: self.verification}[schema]
        return fake_ai_response(parsed)


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


def test_full_flow_publishes_and_logs_costs(stories):
    fake = FakeClaude()
    run_with(fake)
    assert Article.objects.filter(status=Article.Status.PUBLISHED).count() == 2
    article = Article.objects.first()
    assert article.sources.count() == 1 and article.tags.count() == 2
    assert article.slug.startswith("v-orlando-kipyatite-vodu")
    # 2 сюжета × (отбор + написание + проверка)
    assert AICall.objects.count() == 6
    assert AICall.objects.filter(purpose="write", model="claude-sonnet-5").count() == 2
    assert AICall.objects.today().total_cost() > Decimal("0")
    # системный промпт помечен для кэширования
    assert fake.calls[0]["system"][0]["cache_control"] == {"type": "ephemeral"}
    # у Haiku 4.5 не передаём effort, у автора — передаём
    classify_call = next(c for c in fake.calls if c["output_format"] is Classification)
    write_call = next(c for c in fake.calls if c["output_format"] is Draft)
    assert "output_config" not in classify_call and write_call["output_config"] == {"effort": "medium"}


def test_sensitive_story_goes_to_review(stories):
    fake = FakeClaude(classification=Classification(
        score=9, topic="incidents", region="orlando", is_urgent=False, is_sensitive=True, reason="криминал"))
    run_with(fake)
    assert Article.objects.filter(status=Article.Status.REVIEW).count() == 2
    assert "Чувствительная" in Article.objects.first().review_reason


def test_verifier_doubt_goes_to_review(stories):
    fake = FakeClaude(verification=Verification(ok=False, confidence=0.9, issues=["Выдуманная дата"]))
    run_with(fake)
    article = Article.objects.first()
    assert article.status == Article.Status.REVIEW and "Выдуманная дата" in article.review_reason


def test_low_score_is_skipped_without_writing(stories):
    fake = FakeClaude(classification=Classification(
        score=3, topic="other", region="orlando", is_urgent=False, is_sensitive=False, reason="мелочь"))
    run_with(fake)
    assert Article.objects.count() == 0
    assert Story.objects.filter(status=Story.Status.SKIPPED).count() == 2
    assert not any(c["output_format"] is Draft for c in fake.calls)


def test_outside_florida_is_skipped(stories):
    fake = FakeClaude(classification=Classification(
        score=9, topic="other", region="outside", is_urgent=False, is_sensitive=False, reason="не Флорида"))
    run_with(fake)
    assert Article.objects.count() == 0


def test_budget_exceeded_writes_only_urgent(stories):
    conf = SiteSettings.load()
    conf.ai_budget_per_day_usd = Decimal("0.00")
    conf.save()
    run_with(FakeClaude())
    assert Article.objects.count() == 0
    assert Story.objects.filter(status=Story.Status.CLASSIFIED).count() == 2  # ждут в очереди

    urgent = FakeClaude(classification=Classification(
        score=9, topic="safety", region="orlando", is_urgent=True, is_sensitive=False, reason="ЧП"))
    Story.objects.update(status=Story.Status.NEW)
    run_with(urgent)
    assert Article.objects.count() == 2


def test_nws_story_forced_urgent(stories):
    nws = make_source(name="NWS", url="https://api.weather.gov/alerts/test",
                      kind=Source.Kind.NWS_ALERTS, source_type=Source.SourceType.WEATHER)
    story = Story.objects.first()
    story.items.update(source=nws)
    fake = FakeClaude(classification=Classification(
        score=4, topic="weather", region="tampa", is_urgent=False, is_sensitive=False, reason="погода"))
    run_with(fake)
    story.refresh_from_db()
    assert story.is_urgent and story.score >= 9
    assert story.article.status == Article.Status.PUBLISHED  # срочно + официальный источник


def test_ai_error_marks_story_failed_and_logs(stories):
    import anthropic
    import httpx2 as httpx_mod  # anthropic 1.x работает поверх httpx2

    class Broken:
        messages = None

        def __init__(self):
            self.messages = self

        def parse(self, **kwargs):
            request = httpx_mod.Request("POST", "https://api.anthropic.com/v1/messages")
            raise anthropic.APIConnectionError(request=request)

    run_with(Broken())
    assert Story.objects.filter(status=Story.Status.FAILED).count() == 2
    assert AICall.objects.filter(success=False).count() == 2


def test_refusal_is_not_used(stories):
    fake = FakeClaude()
    original = fake.parse

    def refusing(**kwargs):
        response = original(**kwargs)
        response.stop_reason = "refusal"
        return response

    fake.parse = refusing
    run_with(fake)
    assert Article.objects.count() == 0
    assert AICall.objects.filter(success=False, error__icontains="refusal").count() == 2


def test_run_pipeline_without_network_records_run(stories):
    with mock.patch.object(ai, "get_client", return_value=FakeClaude()):
        run = run_pipeline(fetch=False)
    assert run.success and run.stats["written"] == 2 and "Опубликовано" in run.log

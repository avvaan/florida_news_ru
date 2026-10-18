"""Афиша: форма организатора, ИИ-модерация текста и картинки, ImageKit, страницы и разметка."""

import base64
import io
import json
import re
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image

from core import images
from events import moderation
from events.models import Event
from pipeline import ai
from pipeline.models import AICall

from .test_social import FakeDeepSeek

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("sync_moderation")]


@pytest.fixture(autouse=True)
def no_seeded_events():
    """Миграция добавляет фестивали от редакции; тесты формы и модерации начинают с пустой афиши."""
    Event.objects.all().delete()

WITH_IMAGES = {"AI_VISION_MODEL": "claude-haiku-5-5", "ANTHROPIC_API_KEY": "test", "IMAGEKIT_PRIVATE_KEY": "private_x"}


@pytest.fixture
def sync_moderation():
    with override_settings(DIRECTORY_MODERATION_SYNC=True):
        yield


def png(size=(1200, 800), color="orange") -> SimpleUploadedFile:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return SimpleUploadedFile("poster.png", out.getvalue(), content_type="image/png")


def verdict(**kw):
    data = {"decision": "approve", "violation": "none", "reason": "Обычный концерт", "public_reason": "",
            "title": "Концерт русского романса", "description": "Вечер романсов в Санни-Айлс-Бич.",
            "city": "Санни-Айлс-Бич", "region": "miami"}
    data.update(kw)
    return moderation.EventVerdict(**data)


def seen(ok=True, violation="none", reason="Афиша концерта"):
    return images.ImageVerdict(ok=ok, violation=violation, reason=reason, text_on_image="Романсы")


def form_data(**kw):
    day = timezone.localdate() + timedelta(days=10)
    data = {"title": "КОНЦЕРТ русского романса!!!", "starts_on": f"{day:%Y-%m-%d}", "starts_at": "19:00",
            "ends_on": "", "description": "Вечер романсов и песен из кино: поёт Анна Иванова, за роялем Пётр Сидоров.",
            "venue": "Gwen Margolis Center", "address": "17011 NE 19th Ave", "city": "North Miami Beach",
            "price": "$25", "url": "https://tickets.example/romance", "organizer": "Клуб «Романс»",
            "contact_name": "Анна", "contact_email": "anna@example.com", "agree": "on"}
    data.update(kw)
    return data


def post(client, ip="198.51.100.1", image=None, **kw):
    data = form_data(**kw)
    if image is not None:
        data["image"] = image
    return client.post("/afisha/add/", data, REMOTE_ADDR=ip)


def ld_types(html: str) -> dict:
    return {d["@type"]: d for d in (json.loads(b) for b in
            re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S))}


def test_pages_and_nav(client):
    html = client.get("/afisha/").content.decode()
    assert "Куда сходить" in html and 'href="/afisha/add/"' in html and 'content="noindex, follow"' in html
    assert 'href="/afisha/"' in client.get("/").content.decode()  # пункт меню
    form = client.get("/afisha/add/").content.decode()
    assert 'enctype="multipart/form-data"' in form and 'content="noindex, follow"' in form


@override_settings(**WITH_IMAGES)
def test_approved_event_with_image_is_published(client):
    fake = FakeDeepSeek({moderation.EventVerdict: verdict()})
    with mock.patch.object(ai, "get_client", return_value=fake), \
         mock.patch.object(images, "check", return_value=seen()) as check, \
         mock.patch.object(images, "upload", return_value=("https://ik.imagekit.io/x/afisha/p.jpg", "file1")) as up:
        resp = post(client, image=png())
    event = Event.objects.get()
    assert resp.status_code == 302 and resp["Location"] == f"/afisha/add/{event.token}/"
    assert event.status == Event.Status.APPROVED and event.title == "Концерт русского романса"
    assert event.region.slug == "miami" and event.image_status == Event.ImageStatus.PUBLISHED
    assert event.image_url.endswith("p.jpg") and event.image_file_id == "file1" and event.image_data is None
    data, folder = up.call_args.args[0], up.call_args.args[2]
    assert data[:2] == b"\xff\xd8" and folder == "afisha"  # в ImageKit уходит ужатый JPEG
    assert "Gwen Margolis" in check.call_args.args[1]
    assert "<заявка>" in fake.calls[0]["user"] and AICall.objects.filter(purpose="moderate_event").exists()

    assert "Готово, событие в афише" in client.get(resp["Location"]).content.decode()
    listing = client.get("/afisha/").content.decode()
    assert "Концерт русского романса" in listing and "p.jpg?tr=w-640" in listing
    detail = client.get(event.get_absolute_url()).content.decode()
    item = ld_types(detail)["Event"]
    assert item["startDate"].endswith("T19:00") and item["location"]["name"] == "Gwen Margolis Center"
    assert item["image"] == [event.image_url] and "anna@example.com" not in detail
    cache.clear()  # sitemap кэшируется на 10 минут — не оставляем свой ответ другим тестам
    assert event.get_absolute_url() in client.get("/sitemap.xml").content.decode()
    cache.clear()


@override_settings(**WITH_IMAGES)
def test_indecent_image_rejects_whole_event(client):
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({moderation.EventVerdict: verdict()})), \
         mock.patch.object(images, "check", return_value=seen(False, "adult", "Откровенное фото")), \
         mock.patch.object(images, "upload") as up:
        post(client, image=png())
    event = Event.objects.get()
    assert event.status == Event.Status.REJECTED and event.violation == "adult"
    assert event.image_status == Event.ImageStatus.REJECTED and event.image_data is None and not up.called
    assert client.get(f"/afisha/{event.slug}/").status_code == 404


@override_settings(**WITH_IMAGES)
def test_unsuitable_image_is_dropped_but_event_published(client):
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({moderation.EventVerdict: verdict()})), \
         mock.patch.object(images, "check", return_value=seen(False, "mismatch", "Другая дата на афише")), \
         mock.patch.object(images, "upload") as up:
        post(client, image=png())
    event = Event.objects.get()
    assert event.status == Event.Status.APPROVED and event.image_status == Event.ImageStatus.REJECTED
    assert not event.image_url and not up.called
    assert "Картинку мы не опубликовали" in client.get(f"/afisha/add/{event.token}/").content.decode()


def test_without_vision_image_is_skipped(client):
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({moderation.EventVerdict: verdict()})), \
         mock.patch.object(images, "upload") as up:
        post(client, image=png())
    event = Event.objects.get()
    assert event.status == Event.Status.APPROVED and event.image_status == Event.ImageStatus.SKIPPED
    assert event.image_data is None and not up.called


@override_settings(**WITH_IMAGES)
def test_imagekit_failure_retries_upload_later(client):
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({moderation.EventVerdict: verdict()})), \
         mock.patch.object(images, "check", return_value=seen()), \
         mock.patch.object(images, "upload", side_effect=images.ImageError("ImageKit: 503")):
        post(client, image=png())
    event = Event.objects.get()
    assert event.status == Event.Status.APPROVED and event.image_status == Event.ImageStatus.PENDING
    assert event.image_data and "503" in event.image_note
    with mock.patch.object(images, "upload", return_value=("https://ik.imagekit.io/x/p.jpg", "f2")):
        moderation.moderate_pending()
    event.refresh_from_db()
    assert event.image_status == Event.ImageStatus.PUBLISHED and event.image_data is None


def test_stop_words_reject_without_ai(client):
    with mock.patch.object(ai, "get_client") as client_factory:
        post(client, title="Женский ретрит", description="Расклады таро, астрология и работа с энергиями рода для женщин.")
    event = Event.objects.get()
    assert event.status == Event.Status.REJECTED and event.violation == "spiritual" and not client_factory.called


def test_ai_rejection(client):
    fake = FakeDeepSeek({moderation.EventVerdict: verdict(decision="reject", violation="fraud",
                                                          reason="Презентация MLM", public_reason="Похоже на презентацию.")})
    with mock.patch.object(ai, "get_client", return_value=fake):
        post(client, title="Бизнес-завтрак", description="Расскажем о возможностях нашей компании и партнёрской программе.")
    event = Event.objects.get()
    assert event.status == Event.Status.REJECTED and event.public_reason == "Похоже на презентацию."
    assert "Бизнес-завтрак" not in client.get("/afisha/").content.decode()


def test_validation_dates_and_image(client):
    past = timezone.localdate() - timedelta(days=1)
    assert "Дата уже прошла" in post(client, starts_on=f"{past:%Y-%m-%d}").content.decode()
    start = timezone.localdate() + timedelta(days=5)
    resp = post(client, starts_on=f"{start:%Y-%m-%d}", ends_on=f"{start - timedelta(days=1):%Y-%m-%d}")
    assert "Последний день раньше первого" in resp.content.decode()
    bad = SimpleUploadedFile("poster.jpg", b"not an image", content_type="image/jpeg")
    assert "Не получилось открыть картинку" in post(client, image=bad).content.decode()
    assert post(client, company="spam").status_code == 200
    assert not Event.objects.exists()


def test_past_events_leave_the_list(client):
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({moderation.EventVerdict: verdict()})):
        post(client)
    event = Event.objects.get()
    Event.objects.filter(pk=event.pk).update(starts_on=timezone.localdate() - timedelta(days=3))
    assert "Концерт русского романса" not in client.get("/afisha/").content.decode()
    detail = client.get(event.get_absolute_url()).content.decode()
    assert "Событие прошло" in detail and 'content="noindex, follow"' in detail


def test_duplicate_event_is_rejected(client):
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({moderation.EventVerdict: verdict()})):
        post(client)
    first = Event.objects.get()
    with mock.patch.object(ai, "get_client") as client_factory:
        post(client, ip="198.51.100.9", title=first.title, city=first.city)
    second = Event.objects.exclude(pk=first.pk).get()
    assert second.violation == "duplicate" and not client_factory.called and second.slug != first.slug


def test_ip_limit(client):
    with mock.patch.object(moderation, "start_moderation"):
        for n in range(moderation.MAX_PER_IP_PER_DAY):
            post(client, title=f"Событие {n}")
        resp = post(client, title="Ещё одно")
    assert "несколько заявок за сутки" in resp.content.decode()
    assert Event.objects.count() == moderation.MAX_PER_IP_PER_DAY


@override_settings(**WITH_IMAGES)
def test_image_check_sends_picture_to_claude():
    parsed = seen()
    fake = SimpleNamespace(messages=SimpleNamespace(parse=mock.Mock(return_value=SimpleNamespace(
        usage=SimpleNamespace(input_tokens=900, output_tokens=60, cache_read_input_tokens=0,
                              cache_creation_input_tokens=0),
        stop_reason="end_turn", parsed_output=parsed, _request_id="req_1"))))
    with mock.patch.object(ai, "get_client", return_value=fake) as get_client:
        assert images.check(images.prepare(png((3000, 2000))), "Название: концерт", purpose="moderate_event") == parsed
    assert get_client.call_args.args == ("anthropic",)
    content = fake.messages.parse.call_args.kwargs["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/jpeg"
    sent = Image.open(io.BytesIO(base64.b64decode(content[0]["source"]["data"])))
    assert max(sent.size) == images.CHECK_SIDE and "<заявка>" in content[1]["text"]


def test_images_only_go_to_anthropic():
    with pytest.raises(ai.AIError):
        ai.ask(purpose="moderate_event", model="deepseek-flash", system="s", user=[{"type": "text", "text": "x"}],
               output=images.ImageVerdict, provider="deepseek")


def test_pipeline_runs_event_moderation():
    from pipeline.services import run_pipeline

    with mock.patch("events.moderation.moderate_pending", return_value=2) as pending, \
         mock.patch("directory.moderation.moderate_pending", return_value=0), \
         mock.patch("pipeline.services.classify_new", return_value=0), \
         mock.patch("pipeline.services.write_pending", return_value=0), \
         mock.patch("pipeline.services.run_social", return_value={}):
        run = run_pipeline(fetch=False)
    assert pending.called and run.stats["events_moderated"] == 2

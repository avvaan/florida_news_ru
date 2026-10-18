"""Заявки бизнесов в справочник: форма, стоп-слова, ИИ-модерация, публикация, лимиты."""

from datetime import timedelta
from unittest import mock

import pytest
from django.test import override_settings
from django.utils import timezone

from core.models import SiteSettings
from directory import moderation
from directory.models import Category, Listing, Submission
from pipeline import ai
from pipeline.models import AICall

from .test_social import FakeDeepSeek

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("sync_moderation")]


@pytest.fixture
def sync_moderation():
    with override_settings(DIRECTORY_MODERATION_SYNC=True):
        yield


def verdict(**kw):
    data = {"decision": "approve", "violation": "none", "reason": "Обычная стоматология",
            "public_reason": "", "category": "stomatologi", "name": "Smile Dental",
            "description": "Семейная стоматология в Авентуре: лечение и профгигиена.",
            "city": "Авентура", "region": "miami"}
    data.update(kw)
    return moderation.Verdict(**data)


def form_data(**kw):
    data = {"category": Category.objects.get(slug="stomatologi").pk, "name": "Smile Dental!!!",
            "description": "Лучшая стоматология в Авентуре, лечим зубы всей семьёй, говорим по-русски.",
            "city": "Aventura", "address": "1 Test Blvd, Aventura, FL 33180", "phone": "(305) 555-0101",
            "url": "https://smile.example/", "languages": "русский, английский", "hours": "",
            "contact_name": "Анна", "contact_email": "anna@example.com", "agree": "on"}
    data.update(kw)
    return data


def post(client, ip="198.51.100.1", **kw):
    return client.post("/links/add/", form_data(**kw), REMOTE_ADDR=ip)


def test_form_page_lists_only_business_categories(client):
    html = client.get("/links/add/").content.decode()
    assert "Добавить бизнес" in html and "Стоматологи" in html and "Документы и иммиграция" not in html
    assert 'content="noindex, follow"' in html
    assert 'href="/links/add/' in client.get("/links/vrachi/").content.decode()  # кнопка в справочнике


def test_approved_submission_is_published_with_owner_label(client):
    fake = FakeDeepSeek({moderation.Verdict: verdict()})
    with mock.patch.object(ai, "get_client", return_value=fake):
        resp = post(client)
    sub = Submission.objects.get()
    assert resp.status_code == 302 and resp["Location"] == f"/links/add/{sub.token}/"
    assert sub.status == Submission.Status.APPROVED and sub.attempts == 1
    listing = sub.listing
    assert listing.from_owner and listing.is_active and listing.name == "Smile Dental"
    assert listing.region.slug == "miami" and listing.phone == "(305) 555-0101"
    assert "anna@example.com" in listing.editor_note  # контакт — только для редакции
    assert "<заявка>" in fake.calls[0]["user"] and AICall.objects.filter(purpose="moderate").exists()

    status = client.get(resp["Location"]).content.decode()
    assert "Готово, бизнес в справочнике" in status
    page = client.get("/links/stomatologi/").content.decode()
    assert "Smile Dental" in page and "Данные от владельца" in page and "anna@example.com" not in page


def test_stop_words_reject_without_ai(client):
    with mock.patch.object(ai, "get_client") as client_factory:
        post(client, name="Гадание на таро", description="Расклад таро, снятие порчи и приворот онлайн и очно.")
    sub = Submission.objects.get()
    assert sub.status == Submission.Status.REJECTED and sub.violation == "spiritual"
    assert "эзотерик" in sub.public_reason and not client_factory.called and sub.listing is None
    assert "Заявка не прошла проверку" in client.get(f"/links/add/{sub.token}/").content.decode()


def test_ai_rejection_keeps_listing_unpublished(client):
    fake = FakeDeepSeek({moderation.Verdict: verdict(decision="reject", violation="fraud",
                                                     reason="Обещает доход", public_reason="Похоже на финансовую схему.")})
    with mock.patch.object(ai, "get_client", return_value=fake):
        post(client, name="Инвест-клуб", description="Помогаем приумножить сбережения с помощью нашей стратегии вложений.")
    sub = Submission.objects.get()
    assert sub.status == Submission.Status.REJECTED and sub.violation == "fraud"
    assert sub.public_reason == "Похоже на финансовую схему." and not Listing.objects.filter(from_owner=True).exists()


def test_approve_with_violation_is_still_rejected(client):
    fake = FakeDeepSeek({moderation.Verdict: verdict(decision="approve", violation="adult")})
    with mock.patch.object(ai, "get_client", return_value=fake):
        post(client)
    assert Submission.objects.get().status == Submission.Status.REJECTED


def test_duplicate_by_phone_is_rejected(client):
    existing = Listing.objects.filter(category__kind="business", is_active=True).exclude(phone="").first()
    with mock.patch.object(ai, "get_client") as client_factory:
        post(client, phone=existing.phone, url="")
    sub = Submission.objects.get()
    assert sub.violation == "duplicate" and not client_factory.called


def test_honeypot_and_validation(client):
    resp = post(client, company="spam inc")
    assert resp.status_code == 200 and not Submission.objects.exists()
    resp = post(client, phone="", url="")
    assert "Укажите телефон или сайт" in resp.content.decode() and not Submission.objects.exists()
    resp = post(client, agree="")
    assert resp.status_code == 200 and not Submission.objects.exists()


def test_ip_limit(client):
    with mock.patch.object(moderation, "start_moderation"):
        for n in range(moderation.MAX_PER_IP_PER_DAY):
            post(client, name=f"Бизнес {n}")
        resp = post(client, name="Ещё один")
        post(client, ip="198.51.100.2", name="С другого адреса")
    assert "несколько заявок за сутки" in resp.content.decode()
    assert Submission.objects.count() == moderation.MAX_PER_IP_PER_DAY + 1
    assert "198.51.100" not in Submission.objects.first().ip_hash


def test_ai_failure_waits_then_pipeline_retries(client):
    with mock.patch.object(ai, "get_client", side_effect=ai.AIError("нет связи")):
        post(client)
    sub = Submission.objects.get()
    assert sub.status == Submission.Status.PENDING and sub.attempts == 1
    assert "Заявка на проверке" in client.get(f"/links/add/{sub.token}/").content.decode()

    Submission.objects.update(created_at=timezone.now() - timedelta(minutes=10))
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({moderation.Verdict: verdict()})):
        assert moderation.moderate_pending() == 1
    assert Submission.objects.get().status == Submission.Status.APPROVED


def test_gives_up_after_max_attempts(client):
    with mock.patch.object(moderation, "start_moderation"):
        post(client)
    sub = Submission.objects.get()
    with mock.patch.object(ai, "get_client", side_effect=ai.AIError("нет связи")):
        for _ in range(moderation.MAX_ATTEMPTS):
            sub = moderation.moderate(sub)
    assert sub.status == Submission.Status.REJECTED and sub.attempts == moderation.MAX_ATTEMPTS


def test_budget_exceeded_keeps_submission_pending(client):
    SiteSettings.objects.update(ai_budget_per_day_usd=0)
    with mock.patch.object(ai, "get_client") as client_factory:
        post(client)
    assert Submission.objects.get().status == Submission.Status.PENDING and not client_factory.called

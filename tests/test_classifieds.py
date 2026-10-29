"""Объявления: форма с фото, ИИ-модерация текста и фото, управление по ссылке, жалобы, фильтры, страницы."""

import importlib
import io
from datetime import timedelta
from unittest import mock

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image

from classifieds import moderation
from classifieds.forms import normalize_phone, normalize_telegram
from classifieds.models import Ad, Category, Photo, Report
from classifieds.places import region_slug_for_zip
from core import images
from news.models import Region
from pipeline import ai
from pipeline.models import AICall

from .test_social import FakeDeepSeek

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("sync_moderation")]

WITH_IMAGES = {"AI_VISION_MODEL": "claude-haiku-5-5", "ANTHROPIC_API_KEY": "test", "IMAGEKIT_PRIVATE_KEY": "private_x"}


@pytest.fixture
def sync_moderation():
    cache.clear()
    with override_settings(DIRECTORY_MODERATION_SYNC=True):
        yield
    cache.clear()


@pytest.fixture(autouse=True)
def without_seeded_ads():
    """Тесты считают объявления с нуля, а миграция 0005 заливает объявления редакции."""
    Ad.objects.all().delete()


def png(color="orange", name="photo.png") -> SimpleUploadedFile:
    out = io.BytesIO()
    Image.new("RGB", (1200, 900), color).save(out, "PNG")
    return SimpleUploadedFile(name, out.getvalue(), content_type="image/png")


def verdict(**kw):
    data = {"decision": "approve", "violation": "none", "reason": "Обычная продажа мебели", "public_reason": "",
            "category": "mebel", "title": "Диван IKEA, как новый", "description": "Трёхместный диван, 2 года.",
            "city": "Санни-Айлс-Бич", "region": "other"}
    data.update(kw)
    return moderation.AdVerdict(**data)


def seen(ok=True, violation="none", reason="Фото дивана"):
    return images.ImageVerdict(ok=ok, violation=violation, reason=reason, text_on_image="")


def form_data(**kw):
    data = {"category": Category.objects.get(slug="bytovaya-tehnika").pk, "title": "ДИВАН IKEA!!! КАК НОВЫЙ",
            "description": "Трёхместный диван Kivik, 2 года, без пятен и животных. Самовывоз.",
            "price": "250", "price_unit": "", "city": "Sunny Isles Beach", "zip_code": "33160",
            "contact_name": "Анна", "phone": "(305) 555-1234", "has_whatsapp": "on", "telegram": "@anna_miami",
            "agree": "on"}
    data.update(kw)
    return data


def post(client, ip="198.51.100.1", photos=(), **kw):
    data = form_data(**kw)
    if photos:
        data["photos"] = list(photos)
    return client.post("/obyavleniya/add/", data, REMOTE_ADDR=ip)


def submit(client, answer=None, **kw):
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({moderation.AdVerdict: answer or verdict()})):
        return post(client, **kw)


def make_ad(**kw) -> Ad:
    now = timezone.now()
    data = {"category": Category.objects.get(slug="mebel"), "title": "Стол обеденный", "description": "Дубовый стол.",
            "price": 100, "city": "Майами", "zip_code": "33139", "contact_name": "Иван", "phone": "+13055550000",
            "status": Ad.Status.APPROVED, "published_at": now, "expires_at": now + timedelta(days=30),
            "moderated_at": now, "region": Region.objects.get(slug="miami")}
    data.update(kw)
    return Ad.objects.create(**data)


def test_rubricator_is_seeded():
    sections = Category.objects.filter(parent=None)
    assert sections.count() >= 8 and Category.objects.exclude(parent=None).count() >= 60
    assert {"nedvizhimost", "rabota", "uslugi", "transport", "veshchi", "zhivotnye"} <= set(
        sections.values_list("slug", flat=True))
    assert Category.objects.get(slug="vakansii").price_label == "Зарплата"


def test_editorial_ads_from_orlando_groups(client):
    from django.apps import apps

    seed = importlib.import_module("classifieds.migrations.0005_orlando_ads_2026_10")
    seed.add_ads(apps, None)
    seed.add_ads(apps, None)  # повторный прогон ничего не дублирует
    assert Ad.objects.filter(status=Ad.Status.APPROVED).count() == len(seed.ADS) == 6
    ad = Ad.objects.get(phone="+14076771101")
    assert ad.category.slug == "vakansii" and ad.region.slug == "orlando" and ad.point
    assert ad.slug and "лакомка" in ad.search
    assert "добавила редакция" in client.get(ad.get_absolute_url()).content.decode()
    truck = Ad.objects.get(category__slug="pereezdy")
    assert truck.expires_at.date().isoformat() == "2026-11-08"


def test_pages_and_nav(client):
    html = client.get("/obyavleniya/").content.decode()
    assert "Объявления" in html and "Сдам квартиру или дом" in html and 'href="/obyavleniya/add/"' in html
    assert 'content="noindex, follow"' in html  # пока нет ни одного объявления
    assert 'href="/obyavleniya/"' in client.get("/").content.decode()  # пункт меню
    form = client.get("/obyavleniya/add/?category=mebel").content.decode()
    assert 'enctype="multipart/form-data"' in form and 'content="noindex, follow"' in form and "multiple" in form
    assert f'value="{Category.objects.get(slug="mebel").pk}" selected' in form
    assert client.get("/obyavleniya/nedvizhimost/").status_code == 200
    assert client.get("/obyavleniya/net-takoy/").status_code == 404


@override_settings(**WITH_IMAGES)
def test_approved_ad_with_photos_is_published(client):
    fake = FakeDeepSeek({moderation.AdVerdict: verdict()})
    uploads = iter([("https://ik.imagekit.io/x/obyavleniya/1.jpg", "f1")])
    with mock.patch.object(ai, "get_client", return_value=fake), \
         mock.patch.object(images, "check_many", return_value=[seen(), seen(False, "mismatch", "Машина, а не диван")]) \
            as check, \
         mock.patch.object(images, "upload", side_effect=lambda *a: next(uploads)) as up:
        resp = post(client, photos=[png(), png("blue", "b.png")])
    ad = Ad.objects.get()
    assert resp.status_code == 302 and resp["Location"] == f"/obyavleniya/my/{ad.token}/"
    assert ad.status == Ad.Status.APPROVED and ad.title == "Диван IKEA, как новый"
    assert ad.category.slug == "mebel"  # ИИ переложил из «Бытовой техники»
    assert ad.region.slug == "miami"  # регион по ZIP точнее догадки ИИ
    assert ad.phone == "+13055551234" and ad.telegram == "anna_miami" and ad.has_whatsapp
    assert timedelta(days=29) < ad.expires_at - timezone.now() <= timedelta(days=30)
    statuses = list(ad.photos.values_list("status", flat=True))
    assert statuses == [Photo.Status.PUBLISHED, Photo.Status.REJECTED] and up.call_count == 1
    assert up.call_args.args[2] == "obyavleniya" and up.call_args.args[0][:2] == b"\xff\xd8"
    assert len(check.call_args.args[0]) == 2 and "Kivik" in check.call_args.args[1]
    assert "<объявление>" in fake.calls[0]["user"] and "mebel — Мебель" in fake.calls[0]["user"]
    assert AICall.objects.filter(purpose="moderate_ad").exists()

    manage = client.get(resp["Location"]).content.decode()
    assert "Объявление опубликовано" in manage and "не опубликовано: не похоже на то, что в объявлении" in manage
    listing = client.get("/obyavleniya/").content.decode()
    assert "Диван IKEA, как новый" in listing and "1.jpg?tr=w-480" in listing and "$250" in listing
    assert "Диван IKEA" in client.get("/obyavleniya/veshchi/").content.decode()
    assert "Диван IKEA" in client.get("/obyavleniya/mebel/").content.decode()
    assert "Диван IKEA" not in client.get("/obyavleniya/bytovaya-tehnika/").content.decode()

    detail = client.get(ad.get_absolute_url()).content.decode()
    assert "Показать контакты" in detail and "555-1234" not in detail and "anna_miami" not in detail
    assert "maps.google.com/maps?q=33160%20FL" in detail
    shown = client.post(f"/obyavleniya/{ad.pk}/contacts/").content.decode()
    assert "(305) 555-1234" in shown and 'href="tel:+13055551234"' in shown
    assert "https://wa.me/13055551234" in shown and "https://t.me/anna_miami" in shown
    ad.refresh_from_db()
    assert ad.views == 1 and ad.contact_views == 1
    assert client.get(f"/obyavleniya/{ad.pk}-wrong-slug/").status_code == 301
    cache.clear()
    assert ad.get_absolute_url() in client.get("/sitemap.xml").content.decode()
    cache.clear()


def test_too_many_photos(client):
    resp = submit(client, photos=[png(name=f"{n}.png") for n in range(6)])
    assert resp.status_code == 200 and "Не больше 5 фото" in resp.content.decode() and not Ad.objects.exists()


@override_settings(**WITH_IMAGES)
def test_indecent_photo_rejects_whole_ad(client):
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({moderation.AdVerdict: verdict()})), \
         mock.patch.object(images, "check_many", return_value=[seen(), seen(False, "adult", "Откровенное фото")]), \
         mock.patch.object(images, "upload") as up:
        post(client, photos=[png(), png("blue", "b.png")])
    ad = Ad.objects.get()
    assert ad.status == Ad.Status.REJECTED and ad.violation == "adult" and not up.called
    assert set(ad.photos.values_list("status", flat=True)) == {Photo.Status.REJECTED}
    assert not ad.photos.exclude(data=None).exists()
    assert client.get(ad.get_absolute_url()).status_code == 404


def test_without_keys_photos_wait_and_publish_later(client, admin_client):
    """Нет модели со зрением или ImageKit: фото не теряется, а ждёт ключей и публикуется конвейером."""
    with mock.patch.object(images, "upload") as up:
        submit(client, photos=[png()])
    ad = Ad.objects.get()
    photo = ad.photos.get()
    assert ad.status == Ad.Status.APPROVED and not up.called
    assert photo.status == Photo.Status.PENDING and photo.data and "Ждёт настройки" in photo.note
    assert "скоро появится" in client.get(ad.get_manage_url()).content.decode()
    warning = admin_client.get("/admin/classifieds/ad/").content.decode()
    assert "Фото объявлений сейчас не публикуются" in warning and "IMAGEKIT_PRIVATE_KEY" in warning

    with override_settings(**WITH_IMAGES), \
         mock.patch.object(images, "check_many", return_value=[seen()]), \
         mock.patch.object(images, "upload", return_value=("https://ik.imagekit.io/x/1.jpg", "f1")):
        moderation.moderate_pending()
        assert "Фото объявлений сейчас не публикуются" not in admin_client.get("/admin/classifieds/ad/").content.decode()
    photo.refresh_from_db()
    assert photo.status == Photo.Status.PUBLISHED and photo.url.endswith("1.jpg") and photo.data is None


@override_settings(**WITH_IMAGES)
def test_photo_rejection_reason_shown_and_upload_retried(client):
    uploads = mock.Mock(side_effect=[images.ImageError("ImageKit: 500"), ("https://ik.imagekit.io/x/2.jpg", "f2")])
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({moderation.AdVerdict: verdict()})), \
         mock.patch.object(images, "check_many", return_value=[seen(), seen(False, "mismatch", "Машина, а не диван")]), \
         mock.patch.object(images, "upload", uploads):
        post(client, photos=[png(), png("blue", "b.png")])
        ad = Ad.objects.get()
        first, second = ad.photos.order_by("order")
        assert first.status == Photo.Status.CHECKED and first.data  # ImageKit не ответил — фото ждёт
        manage = client.get(ad.get_manage_url()).content.decode()
        assert "скоро появится" in manage and "не опубликовано: не похоже на то, что в объявлении" in manage
        moderation.moderate_pending()
    first.refresh_from_db()
    assert first.status == Photo.Status.PUBLISHED and uploads.call_count == 2


def test_portfolio_photos_allowed_in_prompt():
    assert "Портфолио мастера" in moderation.IMAGE_SYSTEM and "фотографа" in moderation.IMAGE_SYSTEM
    assert "чужие люди или дети крупным планом" not in moderation.IMAGE_SYSTEM


def test_stop_words_reject_without_ai(client):
    with mock.patch.object(ai, "get_client") as get_client:
        post(client, title="Продам Glock 19", description="Пистолет в отличном состоянии, есть документы.")
    ad = Ad.objects.get()
    assert ad.status == Ad.Status.REJECTED and ad.violation == "weapons" and not get_client.called
    assert "оружие" in client.get(ad.get_manage_url()).content.decode()


def test_ai_rejection_explains_and_allows_fix(client):
    answer = verdict(decision="reject", violation="discrimination", reason="Только для славян",
                     public_reason="Уберите требование к национальности жильцов.")
    submit(client, answer=answer, category=Category.objects.get(slug="sdam-kvartiru").pk,
           title="Сдам студию", description="Сдам студию в Авентуре только для славянской семьи без детей.")
    ad = Ad.objects.get()
    assert ad.status == Ad.Status.REJECTED and ad.violation == "discrimination"
    page = client.get(ad.get_manage_url()).content.decode()
    assert "Уберите требование к национальности" in page and "Исправить и отправить снова" in page
    assert client.get(ad.get_absolute_url()).status_code == 404

    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({moderation.AdVerdict: verdict(
            category="sdam-kvartiru", title="Сдам студию")})):
        resp = client.post(f"/obyavleniya/my/{ad.token}/edit/", form_data(
            category=Category.objects.get(slug="sdam-kvartiru").pk, title="Сдам студию",
            description="Сдам студию в Авентуре на длительный срок, мебель и парковка."))
    ad.refresh_from_db()
    assert resp.status_code == 302 and ad.status == Ad.Status.APPROVED


@pytest.mark.parametrize("raw, expected", [
    ("(305) 555-1234", "+13055551234"), ("305.555.1234", "+13055551234"), ("+1 305 555 1234", "+13055551234"),
    ("+380 67 123 4567", "+380671234567"), ("", ""),
])
def test_phone_normalization(raw, expected):
    assert normalize_phone(raw) == expected


def test_contact_validation(client):
    html = submit(client, phone="", telegram="").content.decode()
    assert "Укажите телефон или Telegram" in html
    assert "Проверьте номер" in submit(client, phone="12345").content.decode()
    assert "Это не ZIP-код Флориды" in submit(client, zip_code="10001").content.decode()
    assert normalize_telegram("https://t.me/ivan_miami") == "ivan_miami"
    assert "имя пользователя Telegram" in submit(client, telegram="@a b").content.decode()
    assert not Ad.objects.exists()
    submit(client, phone="", has_whatsapp="on")  # только Telegram — WhatsApp без телефона сбрасывается
    ad = Ad.objects.get()
    assert ad.phone == "" and not ad.has_whatsapp and ad.telegram == "anna_miami"


def test_duplicate_and_contact_limit(client):
    make_ad(title="Диван IKEA, как новый", phone="+13055551234")
    submit(client)
    ad = Ad.objects.latest("pk")
    assert ad.status == Ad.Status.REJECTED and ad.violation == "duplicate"
    for n in range(moderation.MAX_ACTIVE_PER_CONTACT):
        make_ad(title=f"Вещь {n}", telegram="anna_miami", phone="")
    submit(client, title="Новое объявление про стул", ip="198.51.100.9")
    assert Ad.objects.latest("pk").violation == "too_many"


def test_ai_failure_keeps_pending_then_rejects(client):
    with mock.patch.object(ai, "ask", side_effect=ai.AIError("timeout")):
        post(client)
        ad = Ad.objects.get()
        assert ad.status == Ad.Status.PENDING and ad.attempts == 1
        assert "Объявление на проверке" in client.get(ad.get_manage_url()).content.decode()
        Ad.objects.filter(pk=ad.pk).update(created_at=timezone.now() - timedelta(minutes=10))
        moderation.moderate_pending()
        moderation.moderate_pending()
    ad.refresh_from_db()
    assert ad.status == Ad.Status.REJECTED and ad.attempts == moderation.MAX_ATTEMPTS


@override_settings(**WITH_IMAGES)
def test_edit_keeps_published_photos_and_date(client):
    ad = make_ad(published_at=timezone.now() - timedelta(days=3))
    kept = Photo.objects.create(ad=ad, order=0, status=Photo.Status.PUBLISHED, url="https://ik/1.jpg", file_id="f1")
    gone = Photo.objects.create(ad=ad, order=1, status=Photo.Status.PUBLISHED, url="https://ik/2.jpg", file_id="f2")
    published_at, expires_at = ad.published_at, ad.expires_at
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({moderation.AdVerdict: verdict(
            title="Стол обеденный, дуб")})), \
         mock.patch.object(images, "check_many", return_value=[seen()]) as check, \
         mock.patch.object(images, "upload", return_value=("https://ik/3.jpg", "f3")), \
         mock.patch.object(images, "delete") as delete:
        resp = client.post(f"/obyavleniya/my/{ad.token}/edit/", {
            **form_data(category=ad.category.pk, title="Стол обеденный, дуб", phone="+13055550000", telegram=""),
            "remove_photo": [str(gone.pk)], "photos": [png()]})
    ad.refresh_from_db()
    assert resp.status_code == 302 and ad.status == Ad.Status.APPROVED and ad.title == "Стол обеденный, дуб"
    assert ad.published_at == published_at and ad.expires_at == expires_at
    assert len(check.call_args.args[0]) == 1  # проверяется только новое фото
    assert delete.call_args.args == ("f2",) and not Photo.objects.filter(pk=gone.pk).exists()
    assert list(ad.photos.values_list("url", flat=True)) == [kept.url, "https://ik/3.jpg"]

    too_many = client.post(f"/obyavleniya/my/{ad.token}/edit/", {
        **form_data(category=ad.category.pk, phone="+13055550000"), "photos": [png(name=f"{n}.png") for n in range(4)]})
    assert "Можно добавить ещё не больше 3 фото" in too_many.content.decode()


def test_renew_close_and_expiry(client):
    ad = make_ad()
    client.post(f"/obyavleniya/my/{ad.token}/renew/")
    ad.refresh_from_db()
    assert not ad.can_renew and "Продлить можно будет" in client.get(ad.get_manage_url()).content.decode()

    Ad.objects.filter(pk=ad.pk).update(expires_at=timezone.now() - timedelta(days=1))
    assert "Стол обеденный" not in client.get("/obyavleniya/").content.decode()
    detail = client.get(ad.get_absolute_url()).content.decode()
    assert "Срок объявления истёк" in detail and "Показать контакты" not in detail and "noindex" in detail
    assert client.post(f"/obyavleniya/{ad.pk}/contacts/").status_code == 302
    client.post(f"/obyavleniya/my/{ad.token}/renew/")
    ad.refresh_from_db()
    assert ad.is_active and timedelta(days=29) < ad.expires_at - timezone.now()
    assert "Стол обеденный" in client.get("/obyavleniya/").content.decode()

    client.post(f"/obyavleniya/my/{ad.token}/close/")
    ad.refresh_from_db()
    assert ad.status == Ad.Status.CLOSED and ad.closed_at
    assert "Автор снял объявление" in client.get(ad.get_absolute_url()).content.decode()
    assert "Стол обеденный" not in client.get("/obyavleniya/").content.decode()
    assert client.get(f"/obyavleniya/my/{ad.token}/edit/").status_code == 302


def test_reports_hide_ad_after_three_addresses(client):
    ad = make_ad()
    for ip in ["203.0.113.1", "203.0.113.1", "203.0.113.2"]:
        client.post(f"/obyavleniya/{ad.pk}/report/", {"reason": "scam"}, REMOTE_ADDR=ip)
    ad.refresh_from_db()
    assert ad.status == Ad.Status.APPROVED and ad.reports.count() == 2
    page = client.post(f"/obyavleniya/{ad.pk}/report/", {"reason": "sold", "comment": "Уже продано"},
                       REMOTE_ADDR="203.0.113.3").content.decode()
    assert "жалоба принята" in page
    ad.refresh_from_db()
    assert ad.status == Ad.Status.HIDDEN and client.get(ad.get_absolute_url()).status_code == 404
    assert "Объявление скрыто" in client.get(ad.get_manage_url()).content.decode()
    assert client.post(f"/obyavleniya/{make_ad().pk}/report/", {}).status_code == 400
    assert Report.objects.filter(comment="Уже продано").exists()


def test_filters_and_zip_ordering(client):
    far = make_ad(title="Шкаф в Тампе", zip_code="33611", city="Тампа", region=Region.objects.get(slug="tampa"),
                  price=500)
    near = make_ad(title="Шкаф в Авентуре", zip_code="33180", city="Авентура", price=50,
                   published_at=timezone.now() - timedelta(days=2))
    exact = make_ad(title="Шкаф в Санни-Айлс", zip_code="33160", price=None,
                    published_at=timezone.now() - timedelta(days=5))
    other = make_ad(title="Шкаф в Нейплсе", zip_code="34102", city="Нейплс", region=None, price=200)

    def titles(query):
        return [a.title for a in client.get(f"/obyavleniya/?{query}").context["page_obj"].object_list]

    assert titles("zip=33160") == [exact.title, near.title, other.title, far.title]  # дальше — по свежести
    assert titles("region=tampa") == [far.title] and titles("region=other") == [other.title]
    assert titles("q=авентуре шкаф") == [near.title]
    assert titles("price_min=100&price_max=300") == [other.title]
    assert titles("sort=cheap")[:2] == [near.title, other.title]
    assert titles("zip=99999") == [other.title, far.title, near.title, exact.title]  # чужой ZIP игнорируется
    filtered = client.get("/obyavleniya/?region=tampa").content.decode()
    assert 'content="noindex, follow"' in filtered and "Найдено: 1" in filtered
    assert 'content="index, follow' in client.get("/obyavleniya/").content.decode()


def test_honeypot_and_ip_limit(client):
    with mock.patch.object(ai, "get_client") as get_client:
        resp = post(client, company="Spam LLC")
    assert resp.status_code == 200 and not Ad.objects.exists() and not get_client.called
    for n in range(moderation.MAX_PER_IP_PER_DAY):
        submit(client, title=f"Разные вещи номер {n}", ip="192.0.2.5", telegram=f"user_{n}x", phone="")
    resp = submit(client, title="Ещё одна вещь", ip="192.0.2.5", telegram="other_user", phone="")
    assert "уже подано несколько объявлений" in resp.content.decode()
    assert Ad.objects.count() == moderation.MAX_PER_IP_PER_DAY


def test_cleanup_removes_old_photos():
    old = make_ad(status=Ad.Status.CLOSED, closed_at=timezone.now() - timedelta(days=40))
    fresh = make_ad(status=Ad.Status.CLOSED, closed_at=timezone.now() - timedelta(days=2))
    for ad, fid in [(old, "old"), (fresh, "fresh")]:
        Photo.objects.create(ad=ad, status=Photo.Status.PUBLISHED, url=f"https://ik/{fid}.jpg", file_id=fid)
    with mock.patch.object(images, "delete") as delete:
        assert moderation.cleanup() == 1
    assert delete.call_args.args == ("old",) and not old.photos.exists() and fresh.photos.exists()


def test_check_many_maps_answers_by_number():
    data = images.prepare(png())
    answer = images.ImagesVerdict(images=[
        images.NumberedImageVerdict(number=2, ok=False, violation="mismatch", reason="не то", text_on_image=""),
        images.NumberedImageVerdict(number=1, ok=True, violation="none", reason="диван", text_on_image=""),
    ])
    with mock.patch.object(ai, "ask", return_value=answer) as ask:
        result = images.check_many([data, data, data], "Диван", purpose="moderate_ad", system="sys")
    assert [r.ok for r in result] == [True, False, False] and result[2].violation == "unreadable"
    content = ask.call_args.kwargs["user"]
    assert sum(block["type"] == "image" for block in content) == 3 and ask.call_args.kwargs["system"] == "sys"


@pytest.mark.parametrize("zip_code, region", [
    ("33160", "miami"), ("33301", "miami"), ("33401", "miami"), ("32801", "orlando"), ("32901", "orlando"),
    ("33602", "tampa"), ("34236", "tampa"), ("32202", "jacksonville"), ("34102", "other"), ("32301", "other"),
    ("10001", ""), ("3316", ""),
])
def test_region_by_zip(zip_code, region):
    assert region_slug_for_zip(zip_code) == region


def test_admin_restore_hidden(admin_client):
    ad = make_ad(status=Ad.Status.HIDDEN)
    Report.objects.create(ad=ad, reason="scam", ip_hash="x")
    resp = admin_client.post("/admin/classifieds/ad/", {"action": "action_restore", "_selected_action": [ad.pk]})
    ad.refresh_from_db()
    assert resp.status_code == 302 and ad.status == Ad.Status.APPROVED and not ad.reports.exists()
    assert admin_client.get(f"/admin/classifieds/ad/{ad.pk}/change/").status_code == 200
    assert admin_client.get("/admin/classifieds/ad/").status_code == 200


def test_sort_by_distance_from_hub(client):
    miami = make_ad(title="Шкаф в Майами", city="Майами")
    aventura = make_ad(title="Шкаф в Авентуре", city="Авентура")
    orlando = make_ad(title="Шкаф в Орландо", city="Орландо", region=Region.objects.get(slug="orlando"))
    unknown = make_ad(title="Шкаф где-то", city="Деревня Простоквашино", region=None)
    assert (aventura.lat, aventura.lon) == (25.9565, -80.1392) and unknown.lat is None

    resp = client.get("/obyavleniya/?sort=near-orlando")
    assert [a.title for a in resp.context["page_obj"].object_list] == [
        orlando.title, aventura.title, miami.title, unknown.title]
    html = resp.content.decode()
    assert "≈ 194 мили от Орландо" in html and "≈ 204 мили от Орландо" in html
    assert 'href="/obyavleniya/" rel="nofollow" aria-current="true"' in html  # повторный клик сбрасывает
    assert [a.title for a in client.get("/obyavleniya/mebel/?sort=near-miami").context["page_obj"].object_list][:2] \
        == [miami.title, aventura.title]
    assert "миль от" not in client.get("/obyavleniya/").content.decode()  # без сортировки расстояния не пишем


@override_settings(**WITH_IMAGES)
def test_photo_check_failure_does_not_hide_ad(client):
    """Сбой модели со зрением (любой, не только ошибка API): объявление публикуется, фото проверим позже."""
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({moderation.AdVerdict: verdict()})), \
         mock.patch.object(images, "check_many", side_effect=ValueError("schema mismatch")), \
         mock.patch.object(images, "upload") as up:
        post(client, photos=[png()])
    ad = Ad.objects.get()
    photo = ad.photos.get()
    assert ad.status == Ad.Status.APPROVED and ad.is_active and not up.called
    assert photo.status == Photo.Status.PENDING and photo.data and "ValueError: schema mismatch" in photo.note
    assert "Диван IKEA" in client.get("/obyavleniya/").content.decode()

    with mock.patch.object(images, "check_many", return_value=[seen()]), \
         mock.patch.object(images, "upload", return_value=("https://ik.imagekit.io/x/3.jpg", "f3")):
        moderation.moderate_pending()
    photo.refresh_from_db()
    assert photo.status == Photo.Status.PUBLISHED


@override_settings(**WITH_IMAGES)
def test_vague_photo_problem_drops_only_photo(client):
    """«other» по фото (например, детская фотосессия в портфолио фотографа) не отклоняет всё объявление."""
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({moderation.AdVerdict: verdict(
            category="foto-video", title="Профессиональный фотограф")})), \
         mock.patch.object(images, "check_many", return_value=[seen(False, "other", "Дети на фото")]), \
         mock.patch.object(images, "upload") as up:
        post(client, photos=[png()], category=Category.objects.get(slug="foto-video").pk,
             title="Профессиональный фотограф", description="Фотограф на мероприятие или семейную фотосессию.")
    ad = Ad.objects.get()
    assert ad.status == Ad.Status.APPROVED and ad.photos.get().status == Photo.Status.REJECTED and not up.called
    assert "не опубликовано: не подходит для семейного сайта" in client.get(ad.get_manage_url()).content.decode()

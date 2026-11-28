"""API разделов: медиатека, афиша, справочник, гайды, объявления, комментарии, ключ агента."""

import io
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from classifieds.models import Ad
from classifieds.models import Category as AdCategory
from comments.models import Comment
from directory.models import Category, Listing, Submission
from events.models import Event
from gallery import services
from gallery.models import MediaItem
from guides.models import Guide
from news.models import Article

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    settings.IMAGEKIT_PRIVATE_KEY = ""
    return tmp_path


@pytest.fixture
def api():
    staff = User.objects.create_user("editor", password="x", is_staff=True)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=staff).key}")
    return client


def png_bytes(size=(800, 500), color="teal") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return out.getvalue()


def upload(name="photo.png", data=None):
    file = io.BytesIO(data or png_bytes())
    file.name = name
    return file


def fake_download(url, limit):
    return png_bytes(), "image/png"


# --- медиатека -----------------------------------------------------------------------------------

def test_upload_photo_file_stored_on_disk(api, media_root):
    resp = api.post("/api/v1/media/", {"file": upload(), "caption": "Майами-Бич", "credit": "Фото: редакция"},
                    format="multipart")
    assert resp.status_code == 201, resp.json()
    data = resp.json()
    assert data["kind"] == "photo" and data["storage"] == "local" and data["width"] == 800
    assert data["url"].startswith("http") and "/media/media/photo/" in data["url"]
    item = MediaItem.objects.get(pk=data["id"])
    assert (media_root / item.path).exists()
    assert api.delete(f"/api/v1/media/{item.pk}/").status_code == 204
    assert not (media_root / item.path).exists()


def test_media_from_youtube_link_embeds_player(api):
    resp = api.post("/api/v1/media/", {"source": "https://youtu.be/dQw4w9WgXcQ?t=3", "caption": "Видео"},
                    format="json")
    assert resp.status_code == 201, resp.json()
    data = resp.json()
    assert data["kind"] == "video" and data["provider"] == "youtube"
    assert data["embed_url"] == "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"


def test_media_from_image_link_downloads(api):
    with mock.patch("gallery.services.download", side_effect=fake_download):
        resp = api.post("/api/v1/media/", {"source": "https://example.com/a.png"}, format="json")
    assert resp.status_code == 201 and resp.json()["source_url"] == "https://example.com/a.png"


def test_media_rejects_garbage_and_missing_input(api):
    assert api.post("/api/v1/media/", {}, format="json").status_code == 400
    resp = api.post("/api/v1/media/", {"file": upload("x.png", b"not an image")}, format="multipart")
    assert resp.status_code == 400 and "картинка" in str(resp.json())


@pytest.mark.parametrize("url,provider", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
    ("https://youtube.com/shorts/dQw4w9WgXcQ", "youtube"),
    ("https://vimeo.com/76979871", "vimeo"),
    ("https://rutube.ru/video/0123456789abcdef0123456789abcdef/", "rutube"),
    ("https://vk.com/video-123_456", "vk"),
])
def test_parse_video_link(url, provider):
    assert services.parse_video_link(url)["provider"] == provider


def test_internal_addresses_are_not_downloaded():
    with pytest.raises(services.MediaError):
        services.download("http://127.0.0.1/secret.png", 1000)


# --- заметки с фото и видео ----------------------------------------------------------------------

def test_article_with_photo_video_gallery_renders(api, client):
    with mock.patch("gallery.services.download", side_effect=fake_download):
        resp = api.post("/api/v1/articles/", {
            "title": "Пляжи Майами открыты", "teaser": "Анонс", "body": "Текст.", "status": "published",
            "photo_url": "https://example.com/beach.png", "photo_credit": "Фото: City of Miami",
            "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "gallery_urls": ["https://example.com/1.png", "https://example.com/2.png"],
        }, format="json")
    assert resp.status_code == 201, resp.json()
    data = resp.json()
    assert data["photo_info"]["credit"] == "Фото: City of Miami" and data["video_info"]["embed_url"]
    assert len(data["gallery"]) == 2 and data["cover_url"] == data["photo_info"]["url"]
    html = client.get(Article.objects.get(pk=data["id"]).get_absolute_url())
    page = html.content.decode()
    assert html.status_code == 200
    assert data["photo_info"]["url"] in page and "Фото: City of Miami" in page
    assert "youtube-nocookie.com/embed/dQw4w9WgXcQ" in page and "story__gallery" in page
    assert client.get("/").status_code == 200

    # убрать фото — снова обложка-иллюстрация
    resp = api.patch(f"/api/v1/articles/{data['id']}/", {"photo": None, "gallery": []}, format="json")
    assert resp.json()["photo"] is None and resp.json()["gallery"] == [] and "/static/" in resp.json()["cover_url"]


def test_inline_photos_in_article_body(api, client):
    photo = MediaItem.objects.create(kind="photo", url="https://example.com/lighthouse.jpg", storage="external",
                                     caption="Маяк", credit="Фото: Carol M. Highsmith / Library of Congress",
                                     width=1600, height=1067)
    video = MediaItem.objects.create(kind="video", url="https://youtu.be/x", storage="external")
    body = (f"Первый абзац.\n\n[[photo:{photo.pk}|Маяк Джупитер-Инлет, 1860 год]]\n\n## Дальше\n\n"
            f"[[photo:{photo.pk}]]\n\n[[photo:{video.pk}|видео сюда нельзя]]\n\n[[photo:999999|удалено]]\n\nКонец.")
    body_uk = f"Перший абзац.\n\n[[photo:{photo.pk}|Маяк Юпітер-Інлет, 1860 рік]]\n\nКінець."
    resp = api.post("/api/v1/articles/", {"title": "Дорога", "teaser": "Анонс", "body": body, "status": "published",
                                          "title_uk": "Дорога", "teaser_uk": "Анонс", "body_uk": body_uk},
                    format="json")
    assert resp.status_code == 201, resp.json()
    article = Article.objects.get(pk=resp.json()["id"])
    assert [kind for kind, _ in article.blocks] == ["p", "img", "h", "img", "p"]
    assert article.word_count == 5  # «Первый абзац. ## Дальше Конец.» — строки с фото не считаются

    page = client.get(article.get_absolute_url()).content.decode()
    assert page.count('class="story__inline"') == 2 and "[[photo" not in page
    assert "Маяк Джупитер-Инлет, 1860 год · Фото: Carol M. Highsmith / Library of Congress" in page
    assert "Маяк · Фото: Carol M. Highsmith" in page  # без подписи в тексте — подпись фото
    assert 'width="1600" height="1067"' in page and 'loading="lazy"' in page
    assert page.count("https://example.com/lighthouse.jpg") >= 3  # 2 в тексте + разметка NewsArticle

    page_uk = client.get(f"/uk{article.get_absolute_url()}").content.decode()
    assert "Маяк Юпітер-Інлет, 1860 рік · Фото: Carol M. Highsmith" in page_uk


def test_article_photo_must_be_photo(api):
    video = MediaItem.objects.create(kind="video", url="https://youtu.be/x", storage="external")
    resp = api.post("/api/v1/articles/", {"title": "T", "teaser": "t", "body": "b", "photo": video.pk},
                    format="json")
    assert resp.status_code == 400 and "photo" in resp.json()


# --- афиша ---------------------------------------------------------------------------------------

EVENT = {"title": "Концерт в Майами", "description": "Большой концерт на русском.", "venue": "Fillmore",
         "city": "Miami Beach", "region": "miami", "price": "от $45", "url": "https://tickets.example.com/1"}


def test_create_event_publishes_with_image(api, client):
    day = (timezone.localdate() + timedelta(days=10)).isoformat()
    with mock.patch("gallery.services.download", side_effect=fake_download):
        resp = api.post("/api/v1/events/", {**EVENT, "starts_on": day, "starts_at": "19:30",
                                            "image_url": "https://example.com/poster.png"}, format="json")
    assert resp.status_code == 201, resp.json()
    data = resp.json()
    assert data["status"] == "approved" and data["slug"] and data["page_url"].endswith(f"/afisha/{data['slug']}/")
    assert data["image_status"] == "published" and "/media/" in data["image_url"]
    assert client.get(f"/afisha/{data['slug']}/").status_code == 200
    assert EVENT["title"] in client.get("/afisha/").content.decode()

    upcoming = api.get("/api/v1/events/?upcoming=1&region=miami&q=Fillmore").json()
    assert data["id"] in [e["id"] for e in upcoming["results"]]

    resp = api.post(f"/api/v1/events/{data['id']}/reject/", {"reason": "отменён"}, format="json")
    assert resp.json()["status"] == "rejected"
    assert client.get(f"/afisha/{data['slug']}/").status_code == 404
    assert api.post(f"/api/v1/events/{data['id']}/approve/").json()["status"] == "approved"

    resp = api.patch(f"/api/v1/events/{data['id']}/", {"image_remove": True, "price": "бесплатно"}, format="json")
    assert resp.json()["image_url"] == "" and resp.json()["price"] == "бесплатно"


def test_event_validation(api):
    day = timezone.localdate()
    resp = api.post("/api/v1/events/", {**EVENT, "starts_on": day.isoformat(),
                                        "ends_on": (day - timedelta(days=1)).isoformat()}, format="json")
    assert resp.status_code == 400 and "ends_on" in resp.json()


# --- справочник ----------------------------------------------------------------------------------

def test_directory_category_and_listing_with_photo(api, client):
    resp = api.post("/api/v1/directory/categories/", {"name": "Ветеринары", "kind": "business",
                                                      "description": "Русскоязычные ветклиники"}, format="json")
    assert resp.status_code == 201, resp.json()
    slug = resp.json()["slug"]
    assert slug.startswith("veterinar")
    resp = api.post("/api/v1/directory/listings/", {
        "category": slug, "name": "Клиника Айболит", "city": "Sunny Isles", "region": "miami",
        "phone": "+1 305 555 1234", "languages": "русский, английский", "is_recommended": True,
        "photo_file": upload("logo.png"),
    }, format="multipart")
    assert resp.status_code == 201, resp.json()
    data = resp.json()
    assert data["photo_info"]["url"] and data["page_url"].startswith("http")
    page = client.get(Listing.objects.get(pk=data["id"]).get_absolute_url())
    assert page.status_code == 200 and data["photo_info"]["url"] in page.content.decode()
    assert client.get(f"/links/{slug}/").status_code == 200
    assert api.get(f"/api/v1/directory/listings/?category={slug}").json()["count"] == 1
    assert api.get("/api/v1/directory/categories/?kind=business").status_code == 200


def test_submission_approve_and_reject(api):
    category = Category.objects.filter(kind="business").first()
    sub = Submission.objects.create(category=category, name="Пекарня", description="Свежий хлеб", city="Tampa",
                                    contact_name="Иван", contact_email="i@example.com")
    resp = api.post(f"/api/v1/directory/submissions/{sub.pk}/approve/", {"region": "tampa"}, format="json")
    assert resp.status_code == 200, resp.json()
    sub.refresh_from_db()
    assert sub.status == "approved" and sub.listing.from_owner and sub.listing.region.slug == "tampa"
    resp = api.post(f"/api/v1/directory/submissions/{sub.pk}/reject/", {}, format="json")
    sub.listing.refresh_from_db()
    assert resp.json()["status"] == "rejected" and not sub.listing.is_active


# --- гайды ---------------------------------------------------------------------------------------

def test_guide_create_and_publish(api, client):
    resp = api.post("/api/v1/guides/", {
        "title": "Как получить права во Флориде", "slug": "prava-test", "teaser": "Пошагово",
        "body": "## Документы\n\nПаспорт и I-94.", "section": "car",
        "sources": [{"name": "FLHSMV", "url": "https://www.flhsmv.gov/"}],
    }, format="json")
    assert resp.status_code == 201, resp.json()
    assert api.post("/api/v1/guides/prava-test/publish/").status_code == 400  # не проверен человеком
    api.patch("/api/v1/guides/prava-test/", {"human_reviewed": True}, format="json")
    with mock.patch("guides.services.post_guide", return_value="выключен"):
        resp = api.post("/api/v1/guides/prava-test/publish/")
    assert resp.status_code == 200 and resp.json()["guide"]["status"] == "published"
    assert client.get("/guides/prava-test/").status_code == 200
    assert api.post("/api/v1/guides/prava-test/unpublish/").json()["status"] == "draft"


# --- объявления ----------------------------------------------------------------------------------

def test_classified_ad_created_live_with_photo(api, client):
    rubric = AdCategory.objects.exclude(parent=None).first()
    photo = api.post("/api/v1/media/", {"file": upload()}, format="multipart").json()
    resp = api.post("/api/v1/classifieds/ads/", {
        "category": rubric.slug, "title": "Сдам комнату", "description": "Рядом с пляжем, всё включено.",
        "price": 900, "price_unit": "month", "city": "Hollywood", "contact_name": "Анна", "phone": "+13055551234",
        "add_photos": [photo["id"]],
    }, format="json")
    assert resp.status_code == 201, resp.json()
    data = resp.json()
    assert data["status"] == "approved" and data["expires_at"] and len(data["photos"]) == 1
    ad = Ad.objects.get(pk=data["id"])
    assert ad.is_active and client.get(ad.get_absolute_url()).status_code == 200
    assert api.post(f"/api/v1/classifieds/ads/{ad.pk}/close/").json()["status"] == "closed"
    assert api.post(f"/api/v1/classifieds/ads/{ad.pk}/restore/").json()["status"] == "approved"
    resp = api.delete(f"/api/v1/classifieds/ads/{ad.pk}/photos/{data['photos'][0]['id']}/")
    assert resp.status_code == 200 and resp.json()["photos"] == []


def test_ad_needs_rubric_not_section(api):
    section = AdCategory.objects.filter(parent=None).first()
    resp = api.post("/api/v1/classifieds/ads/", {"category": section.slug, "title": "x", "description": "y",
                                                 "city": "Miami", "contact_name": "A"}, format="json")
    assert resp.status_code == 400 and "category" in resp.json()


# --- комментарии ---------------------------------------------------------------------------------

def test_comments_reply_hide_publish(api):
    article = Article.objects.create(title="Новость", teaser="t", body="b", status=Article.Status.PUBLISHED,
                                     published_at=timezone.now())
    resp = api.post("/api/v1/comments/", {"article": article.pk, "text": "Спасибо за вопрос!"}, format="json")
    assert resp.status_code == 201, resp.json()
    data = resp.json()
    assert data["status"] == "approved" and data["name"] == "Редакция"
    assert api.post(f"/api/v1/comments/{data['id']}/hide/", {}, format="json").json()["status"] == "rejected"
    assert api.post(f"/api/v1/comments/{data['id']}/publish/").json()["status"] == "approved"
    assert api.get(f"/api/v1/comments/?article={article.pk}").json()["count"] == 1
    assert api.post("/api/v1/comments/", {"text": "без цели"}, format="json").status_code == 400
    assert Comment.objects.count() == 1


# --- прочее --------------------------------------------------------------------------------------

def test_stats_tags_and_index(api):
    data = api.get("/api/v1/stats/").json()
    assert {"events", "directory", "classifieds", "comments", "guides", "media"} <= data.keys()
    assert api.get("/api/v1/tags/").status_code == 200
    assert api.get("/api/v1/").status_code == 200
    assert api.get("/api/schema/").status_code == 200
    for path in ("events", "directory/categories", "directory/listings", "directory/submissions", "guides",
                 "classifieds/categories", "classifieds/ads", "comments", "authors", "signal-sources", "hints",
                 "media"):
        assert api.get(f"/api/v1/{path}/").status_code == 200, path


def test_new_endpoints_require_staff():
    anon, before = APIClient(), Event.objects.count()
    for path in ("/api/v1/events/", "/api/v1/media/", "/api/v1/directory/listings/"):
        assert anon.get(path).status_code == 401
    assert anon.post("/api/v1/events/", EVENT, format="json").status_code == 401
    assert Event.objects.count() == before


def test_setup_agent_command_with_env_token(capsys):
    token = "a" * 40
    call_command("setup_agent", token=token)
    user = User.objects.get(username="agent")
    assert user.is_staff and not user.has_usable_password() and Token.objects.get(user=user).key == token
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    assert client.get("/api/v1/stats/").status_code == 200
    call_command("setup_agent", rotate=True)
    assert Token.objects.get(user=user).key != token
    assert "Authorization: Token" in capsys.readouterr().out


@override_settings(SITE_URL="https://florida-ru.com", CANONICAL_HOST="florida-ru.com",
                   ALLOWED_HOSTS=["florida-ru.com", "x.onrender.com", "testserver"])
def test_api_is_not_redirected_from_render_host(api):
    resp = api.post("/api/v1/media/", {"source": "https://youtu.be/dQw4w9WgXcQ"}, format="json",
                    HTTP_HOST="x.onrender.com")
    assert resp.status_code == 201

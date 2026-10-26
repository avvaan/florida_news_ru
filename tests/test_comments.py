"""Комментарии к новостям и отзывы о бизнесах: защита от ботов, ИИ-модерация, жалобы, рейтинг и страница бизнеса."""

import json
import re
import time
from unittest import mock

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from comments import moderation
from comments.forms import make_stamp
from comments.models import Comment
from directory.models import Category, Listing
from news.models import Article, Region, Topic
from pipeline import ai
from pipeline.models import AICall

from .test_social import FakeDeepSeek

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("sync_moderation")]


@pytest.fixture
def sync_moderation():
    with override_settings(DIRECTORY_MODERATION_SYNC=True):
        yield


@pytest.fixture
def article():
    return Article.objects.create(
        title="Налоговые каникулы на товары к урагану", teaser="Что входит в список", body="Текст.",
        topic=Topic.objects.get(slug="money"), region=Region.objects.get(slug="miami"),
        status=Article.Status.PUBLISHED, published_at=timezone.now(),
    )


@pytest.fixture
def business():
    cat = Category.objects.create(slug="test-vrachi", name="Врачи", kind=Category.Kind.BUSINESS,
                                  schema_type="MedicalClinic")
    return Listing.objects.create(category=cat, name="Клиника доктора Петрова", city="Санни-Айлс-Бич",
                                  address="100 Collins Ave, Sunny Isles Beach, FL 33160", phone="(305) 555-0100",
                                  description="Семейный врач, говорит по-русски.")


def ok(**kw):
    data = {"decision": "approve", "violation": "none", "reason": "Обычный комментарий", "public_reason": ""}
    data.update(kw)
    return moderation.CommentVerdict(**data)


def data_for(kind, pk, **kw):
    data = {"name": "Анна", "email": "anna@example.com", "text": "Спасибо, очень полезно — не знала про это.",
            "agree": "on", "website": "", "stamp": make_stamp(kind, pk, time.time() - 10)}
    data.update(kw)
    return data


def post(client, target, verdict=None, ip="198.51.100.7", **kw):
    kind = "listing" if isinstance(target, Listing) else "article"
    with mock.patch.object(ai, "get_client", return_value=FakeDeepSeek({moderation.CommentVerdict: verdict or ok()})):
        return client.post(f"/comments/{kind}/{target.pk}/", data_for(kind, target.pk, **kw), REMOTE_ADDR=ip)


def test_article_comment_published(client, article):
    page = client.get(article.get_absolute_url()).content.decode()
    assert 'id="comments"' in page and "Комментариев пока нет" in page and 'name="stamp"' in page
    assert 'name="rating"' not in page  # оценки только у отзывов о бизнесах

    resp = post(client, article)
    comment = Comment.objects.get()
    assert resp.status_code == 302
    assert resp["Location"] == f"{article.get_absolute_url()}?comment={comment.token}#my-comment"
    assert comment.status == Comment.Status.APPROVED and comment.article == article
    assert AICall.objects.filter(purpose="moderate_comment").exists()

    html = client.get(resp["Location"]).content.decode()
    assert "Спасибо, комментарий опубликован" in html and "не знала про это" in html
    assert "anna@example.com" not in client.get(article.get_absolute_url()).content.decode()


def test_rejected_comment_explains(client, article):
    post(client, article, verdict=ok(decision="reject", violation="insult", reason="Грубость",
                                     public_reason="Уберите, пожалуйста, грубые слова."), text="Автор — идиот, пишет чушь")
    comment = Comment.objects.get()
    assert comment.status == Comment.Status.REJECTED and comment.violation == "insult"
    html = client.get(f"{article.get_absolute_url()}?comment={comment.token}").content.decode()
    assert "Уберите, пожалуйста, грубые слова" in html and "идиот" not in html.split('id="comments"')[1].split(
        "</form>")[0].split("Комментарий не опубликован")[0]


STAMPS = {  # особые метки формы: (смещение времени открытия, на какую страницу)
    "fast": (-1, None), "old": (-2 * 24 * 3600, None), "other_page": (-10, 999999),
}


@pytest.mark.parametrize("change, error", [
    ({"stamp": "подделка"}, "Обновите страницу"),
    ({"stamp": "other_page"}, "Форма устарела"),
    ({"stamp": "fast"}, "Слишком быстро"),  # отправка через секунду после открытия формы
    ({"stamp": "old"}, "Форма устарела"),
    ({"text": "Смотрите тут: https://spam.example/x"}, "Ссылки в комментариях"),
    ({"text": "пишите на spam-site.com"}, "Ссылки в комментариях"),
    ({"email": "не почта"}, "e-mail"),
    ({"agree": ""}, "Нужно подтвердить"),
])
def test_bot_protection_and_validation(client, article, change, error):
    if change.get("stamp") in STAMPS:
        shift, pk = STAMPS[change["stamp"]]
        change = {"stamp": make_stamp("article", pk or article.pk, time.time() + shift)}
    with mock.patch.object(ai, "get_client") as get_client:
        resp = client.post(f"/comments/article/{article.pk}/", data_for("article", article.pk, **change))
    assert resp.status_code == 400 and not Comment.objects.exists() and not get_client.called
    assert error.lower() in resp.content.decode().lower()


def test_honeypot_saves_nothing(client, article):
    with mock.patch.object(ai, "get_client") as get_client:
        resp = client.post(f"/comments/article/{article.pk}/", data_for("article", article.pk, website="http://bot"))
    assert resp.status_code == 302 and not Comment.objects.exists() and not get_client.called


def test_limits_duplicates_and_stop_words(client, article):
    post(client, article)
    post(client, article, ip="198.51.100.8")  # тот же текст с того же e-mail — дубль
    assert Comment.objects.latest("pk").violation == "duplicate"
    with mock.patch.object(ai, "get_client") as get_client:
        post(client, article, text="Лучший эскорт в Майами, звоните", email="x@example.com", ip="198.51.100.9")
    assert Comment.objects.latest("pk").violation == "stop" and not get_client.called
    for n in range(moderation.MAX_PER_IP_PER_HOUR):
        post(client, article, text=f"Комментарий номер {n}, по делу", email=f"u{n}@example.com", ip="203.0.113.5")
    resp = post(client, article, text="Ещё один комментарий", email="z@example.com", ip="203.0.113.5")
    assert resp.status_code == 400 and "уже много комментариев" in resp.content.decode()


def test_ai_failure_keeps_pending(client, article):
    with mock.patch.object(ai, "ask", side_effect=ai.AIError("timeout")):
        resp = post(client, article)
        comment = Comment.objects.get()
        assert comment.status == Comment.Status.PENDING
        html = client.get(resp["Location"]).content.decode()
        assert "Комментарий на проверке" in html and "location.reload" in html and "не знала" not in html.split(
            "Комментарий на проверке")[1].split("</section>")[0]
        Comment.objects.filter(pk=comment.pk).update(created_at=timezone.now() - timezone.timedelta(minutes=10))
        stale = client.get(resp["Location"]).content.decode()
        assert "Проверка задерживается" in stale and "location.reload" not in stale  # не обновляем вечно
        moderation.moderate_pending()
        moderation.moderate_pending()
    comment.refresh_from_db()
    assert comment.status == Comment.Status.REJECTED and comment.attempts == moderation.MAX_ATTEMPTS


def test_reports_hide_comment(client, article):
    post(client, article)
    comment = Comment.objects.get()
    for ip in ["192.0.2.1", "192.0.2.1", "192.0.2.2"]:
        resp = client.post(f"/comments/report/{comment.pk}/", REMOTE_ADDR=ip)
    assert resp["Location"].endswith(f"?reported={comment.pk}#comment-{comment.pk}")
    comment.refresh_from_db()
    assert comment.status == Comment.Status.APPROVED and comment.reports == 2
    assert "жалоба принята" in client.get(resp["Location"]).content.decode()
    client.post(f"/comments/report/{comment.pk}/", REMOTE_ADDR="192.0.2.3")
    comment.refresh_from_db()
    assert comment.status == Comment.Status.HIDDEN
    assert "не знала про это" not in client.get(article.get_absolute_url()).content.decode()


def test_business_page_reviews_and_rating(client, business):
    url = business.get_absolute_url()
    assert re.fullmatch(r"/links/test-vrachi/\d+-klinika-doktora-petrova/", url)
    page = client.get(url).content.decode()
    assert "Клиника доктора Петрова" in page and "Отзывов пока нет" in page and 'name="rating"' in page
    assert client.get(f"/links/test-vrachi/{business.pk}-wrong/").status_code == 301

    resp = post(client, business, text="Без оценки, но отзыв")
    assert resp.status_code == 400 and "Поставьте оценку" in resp.content.decode()
    resp = post(client, business, rating="5", text="Внимательный врач, объяснил всё по-русски, ждали 10 минут.")
    assert "Спасибо, отзыв опубликован" in client.get(resp["Location"]).content.decode()
    post(client, business, rating="4", text="Хорошо, но парковка платная и тесная.", email="b@example.com",
         ip="198.51.100.20")
    post(client, business, rating="1", text="Ужасно", email="c@example.com", ip="198.51.100.21",
         verdict=ok(decision="reject", violation="accusation", reason="Обвинения"))
    assert Comment.objects.filter(listing=business, status="approved").count() == 2

    page = client.get(url).content.decode()
    assert "<b>4,5</b>" in page and "2 отзыва" in page and "★★★★★" in page
    ld = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)]
    clinic = next(d for d in ld if d.get("@type") == "MedicalClinic")
    assert clinic["aggregateRating"]["ratingValue"] == 4.5 and clinic["aggregateRating"]["reviewCount"] == 2
    assert len(clinic["review"]) == 2 and clinic["review"][0]["author"]["name"] == "Анна"

    listing_page = client.get("/links/test-vrachi/").content.decode()
    assert f'href="{url}"' in listing_page and "<b>4,5</b> · 2 отзыва" in listing_page
    cache.clear()
    assert url in client.get("/sitemap.xml").content.decode()
    cache.clear()


def test_links_have_no_page_and_bad_targets_404(client, business, article):
    links = Category.objects.create(slug="test-links", name="Ссылки", kind=Category.Kind.LINKS)
    official = Listing.objects.create(category=links, name="IRS", url="https://www.irs.gov/")
    assert official.get_absolute_url() == "https://www.irs.gov/"
    assert client.post(f"/comments/listing/{official.pk}/", data_for("listing", official.pk)).status_code == 404
    draft = Article.objects.create(title="Черновик", teaser="t", body="b", status=Article.Status.DRAFT)
    assert client.post(f"/comments/article/{draft.pk}/", data_for("article", draft.pk)).status_code == 404
    assert client.get(f"/comments/article/{article.pk}/").status_code == 405


def test_admin_hide_and_publish(admin_client, article, client):
    post(client, article)
    comment = Comment.objects.get()
    admin_client.post("/admin/comments/comment/", {"action": "action_hide", "_selected_action": [comment.pk]})
    comment.refresh_from_db()
    assert comment.status == Comment.Status.REJECTED
    admin_client.post("/admin/comments/comment/", {"action": "action_publish", "_selected_action": [comment.pk]})
    comment.refresh_from_db()
    assert comment.status == Comment.Status.APPROVED
    assert admin_client.get("/admin/comments/comment/").status_code == 200
    assert admin_client.get(f"/admin/comments/comment/{comment.pk}/change/").status_code == 200

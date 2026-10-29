import pytest
from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from ads.models import AdBanner
from news.models import Article, ArticleSource, Region, Topic
from sources.models import WeatherAlert

pytestmark = pytest.mark.django_db


@pytest.fixture
def article():
    a = Article.objects.create(
        title="Налоговые каникулы на товары к урагану", teaser="Что входит в список",
        body="Первый абзац.\n\nВторой абзац.", region=Region.objects.get(slug="miami"),
        topic=Topic.objects.get(slug="money"), status=Article.Status.PUBLISHED, published_at=timezone.now(),
    )
    ArticleSource.objects.create(article=a, name="Florida Phoenix", url="https://floridaphoenix.com/x")
    return a


@override_settings(TELEGRAM_CHANNEL_URL="https://t.me/florida_ru")
def test_home_and_sections(client, article):
    for url in ("/", "/region/miami/", "/region/florida/", "/topic/safety/", "/business/", "/about/", "/rss/"):
        assert client.get(url).status_code == 200, url
    html = client.get("/").content.decode()
    assert article.title in html and "Подписаться" in html and "https://t.me/florida_ru" in html


@override_settings(TELEGRAM_CHANNEL_URL="")
def test_telegram_button_hidden_without_channel_url(client, article):
    from core.models import SiteSettings

    SiteSettings.objects.update(telegram_channel_url="https://t.me/")
    for url in ("/", article.get_absolute_url()):
        html = client.get(url).content.decode()
        assert "t.me/" not in html and "Подписаться" not in html, url


def test_digest_not_repeated_in_feed(client):
    now = timezone.now()
    for i in range(14):
        Article.objects.create(title=f"Заметка номер {i}", teaser="t", body="b", topic=Topic.objects.get(slug="laws"),
                               score=i, status=Article.Status.PUBLISHED, published_at=now - timezone.timedelta(minutes=i))
    ctx = client.get("/").context
    digest = {a.pk for a in ctx["most_important"]}
    assert len(digest) == 5 and not digest & {a.pk for a in ctx["feed"]}
    assert len(ctx["feed"]) == 14 - 1 - 3 - 5  # главная тема, три плитки и дайджест — каждая заметка один раз


def test_region_filter_includes_statewide(client, article):
    statewide = Article.objects.create(title="Закон для всего штата", teaser="t", body="b",
                                       region=Region.objects.get(slug="florida"),
                                       status=Article.Status.PUBLISHED, published_at=timezone.now())
    tampa_html = client.get("/region/tampa/").content.decode()
    assert statewide.title in tampa_html and article.title not in tampa_html


def test_article_page_has_seo_and_sources(client, article):
    html = client.get(article.get_absolute_url()).content.decode()
    assert '"@type": "NewsArticle"' in html
    assert 'rel="canonical"' in html and 'property="og:image"' in html
    assert "Florida Phoenix" in html and "https://floridaphoenix.com/x" in html
    assert "не юридическая и не финансовая консультация" in html
    assert html.count("<p>Первый абзац.</p>") == 1


def test_unpublished_article_hidden_from_public(client, article):
    article.status = Article.Status.REVIEW
    article.save()
    assert client.get(article.get_absolute_url()).status_code == 404
    staff = User.objects.create_user("ed", password="x", is_staff=True)
    client.force_login(staff)
    assert "Предпросмотр" in client.get(article.get_absolute_url()).content.decode()


def test_sitemaps(client, article):
    xml = client.get("/sitemap.xml").content.decode()
    assert article.get_absolute_url() in xml
    news = client.get("/news-sitemap.xml").content.decode()
    assert "<news:language>ru</news:language>" in news and article.title in news
    assert "Sitemap:" in client.get("/robots.txt").content.decode()


def test_weather_block_only_with_active_alerts(client, article):
    assert 'id="weather-h"' not in client.get("/").content.decode()
    WeatherAlert.objects.create(external_id="x", event="Hurricane Warning", event_ru="Предупреждение об урагане",
                                severity="Extreme", expires=timezone.now() + timezone.timedelta(hours=5))
    html = client.get("/").content.decode()
    assert 'id="weather-h"' in html and "Предупреждение об урагане" in html


def test_ads_respect_dates_and_region(client, article):
    AdBanner.objects.create(advertiser="Clinic Miami", slot="sidebar", headline="Врач в Майами",
                            url="https://example.com", region=Region.objects.get(slug="miami"))
    AdBanner.objects.create(advertiser="Old", slot="sidebar", headline="Просроченная реклама",
                            url="https://example.com", ends_at=timezone.now() - timezone.timedelta(days=1))
    assert "Врач в Майами" in client.get("/region/miami/").content.decode()
    assert "Врач в Майами" not in client.get("/region/tampa/").content.decode()
    assert "Просроченная реклама" not in client.get("/").content.decode()


def test_admin_review_queue_publish_button(client, article):
    article.status = Article.Status.REVIEW
    article.review_reason = "Чувствительная тема"
    article.published_at = None
    article.save()
    admin = User.objects.create_superuser("admin", "a@example.com", "x")
    client.force_login(admin)
    queue = client.get(reverse("admin:news_reviewarticle_changelist")).content.decode()
    assert article.title in queue
    url = reverse("admin:news_reviewarticle_change", args=[article.pk])
    assert "Опубликовать" in client.get(url).content.decode()

    data = {
        "title": article.title, "teaser": article.teaser, "body": article.body, "region": article.region_id,
        "topic": article.topic_id, "status": "review", "slug": article.slug, "review_reason": "",
        "sources-TOTAL_FORMS": "0", "sources-INITIAL_FORMS": "0", "_publish": "1",
    }
    response = client.post(url, data)
    assert response.status_code == 302
    article.refresh_from_db()
    assert article.status == Article.Status.PUBLISHED and article.published_at is not None


def test_admin_pages_render(client):
    admin = User.objects.create_superuser("admin", "a@example.com", "x")
    client.force_login(admin)
    for name in ("admin:pipeline_aicall_changelist", "admin:sources_source_changelist",
                 "admin:ads_adbanner_changelist", "admin:news_article_changelist"):
        assert client.get(reverse(name)).status_code == 200, name
    assert client.get(reverse("admin:core_sitesettings_changelist")).status_code == 302


def test_merged_topics_share_pages(client):
    """«ЧП» + «Происшествия», «Деньги» + «Бизнес», «Афиша» + «Куда сходить»: один пункт меню, одна страница."""
    def make(title, slug):
        return Article.objects.create(title=title, teaser="t", body="Текст.", topic=Topic.objects.get(slug=slug),
                                      status=Article.Status.PUBLISHED, published_at=timezone.now())

    make("Пожар на складе в Хайалиа", "safety")
    make("Ограбление магазина в Тампе", "incidents")
    make("Цены на бензин снизились", "money")
    make("Фестиваль в парке Орландо", "events")
    safety = client.get("/topic/safety/").content.decode()
    assert "Пожар на складе" in safety and "Ограбление магазина" in safety and "ЧП и происшествия" in safety
    assert "Цены на бензин снизились" in client.get("/business/").content.decode()
    assert "Фестиваль в парке Орландо" in client.get("/afisha/").content.decode()
    for old, new in [("/topic/incidents/", "/topic/safety/"), ("/topic/money/", "/business/"),
                     ("/topic/events/", "/afisha/"), ("/topic/business/", "/business/")]:
        resp = client.get(old)
        assert resp.status_code == 301 and resp["Location"] == new, old
    nav = client.get("/").content.decode().split('aria-label="Темы"')[1].split("</nav>")[0]
    assert ">ЧП<" in nav and ">Деньги и бизнес<" in nav and ">Афиша<" in nav and ">Справочник<" in nav
    for gone in (">Происшествия<", ">Деньги<", ">Бизнес<", ">Куда сходить<", ">Ссылки и бизнесы<"):
        assert gone not in nav, gone
    assert nav.count('href="/afisha/"') == 1

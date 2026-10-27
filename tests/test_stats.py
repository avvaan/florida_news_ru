"""Посещаемость: сигнал из браузера, боты помечаются и считаются отдельно, панель в админке."""

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone

from core.models import Page
from stats.admin import average_per_day, build_dashboard
from stats.models import DailyStat, Hit, PageView, Source
from stats.tracking import RATE_LIMIT, bot_reason, normalize_source

pytestmark = pytest.mark.django_db

IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
          "Version/18.0 Mobile/15E148 Safari/604.1")
ANDROID = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/129.0.6668.100 Mobile Safari/537.36")
TELEGRAM_ANDROID = ANDROID + " Telegram-Android/11.2.2 (Google Pixel 8; Android 14; SDK 34; HIGH)"
TELEGRAM_IOS = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Mobile/15E148 Safari/604.1")
FACEBOOK_APP = IPHONE.replace("Safari/604.1", "[FBAN/FBIOS;FBAV/480.0.0.40.104;FBBV/650000000;FBDV/iPhone15,2]")
YANDEX_APP = ANDROID + " YaApp_Android/24.50 YaSearchBrowser/24.50 YandexSearch/24.50"
MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36"

HUMANS = [IPHONE, ANDROID, TELEGRAM_ANDROID, TELEGRAM_IOS, FACEBOOK_APP, YANDEX_APP, MAC]
BOTS = [
    "",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/120.0 Safari/537.36",
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "meta-externalagent/1.1",
    "TelegramBot (like TwitterBot)",
    "WhatsApp/2.23.20.0",
    "curl/8.4.0",
    "python-requests/2.31",
    "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)",
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)",
    "Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)",
    "Mozilla/5.0 (Linux; Android 11; moto g power (2022)) AppleWebKit/537.36 Chrome/109 Mobile Safari/537.36 "
    "Chrome-Lighthouse",
    "Go-http-client/2.0",
    "UptimeRobot/2.0",
]


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()
    yield
    cache.clear()


def beacon(client, path="/", referrer="", agent=IPHONE, visitor="0b6e1f6a-3a6c-4b8e-9d55-1d3c7a2f9e10",
           origin="http://testserver", ip="203.0.113.5", **data):
    body = {"p": path, "r": referrer, "w": 390, "v": visitor, "d": False, **data}
    headers = {"HTTP_USER_AGENT": agent, "REMOTE_ADDR": ip}
    if origin:
        headers["HTTP_ORIGIN"] = origin
    return client.post("/stats/hit/", data=json.dumps(body), content_type="text/plain;charset=UTF-8", **headers)


# --- Правила: боты --------------------------------------------------------------------

@pytest.mark.parametrize("agent", HUMANS)
def test_real_browsers_are_humans(agent):
    assert bot_reason(agent) == ""


@pytest.mark.parametrize("agent", BOTS)
def test_bots_by_user_agent(agent):
    assert bot_reason(agent)


def test_webdriver_is_a_bot_even_with_a_normal_browser():
    assert bot_reason(MAC, automation=True) == "webdriver"
    assert bot_reason("Mozilla/5.0 (compatible; Googlebot/2.1)") == "UA: bot"


# --- Правила: откуда пришли ---------------------------------------------------------------

HOSTS = {"florida-ru.com", "testserver"}


@pytest.mark.parametrize("referrer, utm, expected", [
    ("", "", "прямой заход"),
    ("http://188.114.97.7/", "", "прямой заход"),  # IP Cloudflare — не сайт
    ("https://[2606:4700::6812:1]/", "", "прямой заход"),
    ("https://florida-ru.com/guides/", "", ""),  # переход внутри сайта — не вход
    ("https://www.florida-ru.com/", "", ""),
    ("https://l.facebook.com/l.php?u=x", "", "facebook"),
    ("https://lm.facebook.com/", "", "facebook"),
    ("https://m.facebook.com/", "", "facebook"),
    ("https://l.threads.com/?u=x", "", "threads"),
    ("https://t.co/abc", "", "x"),
    ("android-app://org.telegram.messenger/", "", "telegram"),
    ("https://t.me/floridaru", "", "telegram"),
    ("https://www.google.com/", "", "google"),
    ("https://www.google.co.uk/", "", "google"),
    ("https://example.org/page", "", "example.org"),
    ("https://www.google.com/", "Telegram", "telegram"),  # метка utm важнее адреса
    ("", "whatsapp", "whatsapp"),
    ("https://florida-ru.com/", "tg", "telegram"),
])
def test_referrer_normalisation(referrer, utm, expected):
    assert normalize_source(referrer, utm, HOSTS) == expected


# --- Сигнал из браузера --------------------------------------------------------------------

def test_beacon_records_a_human_view(client):
    resp = beacon(client, "/guides/?utm_source=telegram&utm_medium=group&utm_campaign=oct",
                  referrer="https://t.me/s/floridaru?x=1")
    assert resp.status_code == 204
    hit = Hit.objects.get()
    assert (hit.path, hit.source, hit.referrer) == ("/guides/", "telegram", "https://t.me")
    assert (hit.utm_source, hit.utm_medium, hit.utm_campaign) == ("telegram", "group", "oct")
    assert (hit.device, hit.screen_width, hit.is_bot, hit.bot_reason) == ("mobile", 390, False, "")
    assert len(hit.visitor) == 32 and "0b6e1f6a" not in hit.visitor and "203.0.113.5" not in hit.visitor


def test_beacon_keeps_bots_but_marks_them(client):
    beacon(client, agent="Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome/120.0 Safari/537.36")
    beacon(client, agent=MAC, d=True)
    reasons = set(Hit.objects.values_list("is_bot", "bot_reason"))
    assert reasons == {(True, "UA: headless"), (True, "webdriver")}


def test_one_visitor_per_day_by_browser_code(client):
    beacon(client, "/")
    beacon(client, "/guides/", referrer="http://testserver/")
    beacon(client, "/", visitor="7c9e6679-7425-40de-944b-e07fc1f90ae7")
    beacon(client, "/", visitor="", ip="198.51.100.1")  # localStorage недоступен — код из IP и браузера
    assert Hit.objects.values("visitor").distinct().count() == 3
    assert Hit.objects.get(path="/guides/").source == ""  # внутренний переход — не вход


def test_beacon_rejects_get_and_foreign_or_service_pages(client, admin_client):
    assert client.get("/stats/hit/").status_code == 405
    beacon(client, origin="https://evil.example")
    beacon(client, origin="")  # без Origin и Referer
    for path in ("/admin/", "/stats/hit/", "/robots.txt", "/sitemap.xml", "/static/css/site.css",
                 "/net-takogo-adresa/", "https://evil.example/"):
        beacon(client, path)
    admin_client.post("/stats/hit/", data=json.dumps({"p": "/"}), content_type="text/plain",
                      HTTP_USER_AGENT=MAC, HTTP_ORIGIN="http://testserver")  # редакция
    resp = client.post("/stats/hit/", data="x" * 5000, content_type="text/plain", HTTP_USER_AGENT=MAC,
                       HTTP_ORIGIN="http://testserver")
    assert resp.status_code == 204 and not Hit.objects.exists()


def test_beacon_accepts_referer_header_without_origin(client):
    client.post("/stats/hit/", data=json.dumps({"p": "/"}), content_type="text/plain", HTTP_USER_AGENT=IPHONE,
                HTTP_REFERER="http://testserver/guides/")
    assert Hit.objects.count() == 1


def test_beacon_rate_limit(client):
    codes = [beacon(client).status_code for _ in range(RATE_LIMIT + 1)]
    assert codes[:RATE_LIMIT] == [204] * RATE_LIMIT and codes[-1] == 429
    assert Hit.objects.count() == RATE_LIMIT
    assert beacon(client, ip="198.51.100.2").status_code == 204  # другой адрес — свой лимит


def test_pages_load_the_script_and_server_no_longer_counts(client):
    html = client.get("/", HTTP_USER_AGENT=IPHONE).content.decode()
    assert "js/hit.js" in html and 'defer' in html
    assert "js/hit.js" not in client.get("/net-takogo-adresa/", HTTP_USER_AGENT=IPHONE).content.decode()
    assert not DailyStat.objects.exists() and not PageView.objects.exists() and not Hit.objects.exists()


def test_script_is_small():
    from pathlib import Path

    from django.conf import settings

    assert (Path(settings.BASE_DIR) / "static/js/hit.js").stat().st_size < 1024


# --- Панель -------------------------------------------------------------------------------

def make_hit(day, path="/", visitor="a", bot=False, source="", **kw):
    fields = {"device": "mobile", "is_bot": bot, "bot_reason": "UA: bot" if bot else "",
              "agent": "Googlebot" if bot else IPHONE, **kw}
    return Hit.objects.create(date=day, path=path, visitor=visitor, source=source, **fields)


def test_average_per_day_counts_only_days_with_data():
    today = timezone.localdate()
    start = today - timedelta(days=29)
    assert average_per_day(90, start, today, today - timedelta(days=2)) == 30  # 3 дня, а не 30
    assert average_per_day(90, start, today, today - timedelta(days=100)) == 3
    assert average_per_day(90, start, today, None) == 0


def test_dashboard_shows_humans_and_counts_bots_separately():
    today = timezone.localdate()
    make_hit(today, visitor="a", source="telegram", utm_source="telegram")
    make_hit(today, "/guides/", visitor="a")
    make_hit(today, visitor="b", source=Source.DIRECT)
    for n in range(3):
        make_hit(today, f"/guides/{n}/", visitor=f"bot{n}", bot=True, source=Source.DIRECT)
    make_hit(today - timedelta(days=1), visitor="c", source="google")
    DailyStat.objects.create(date=today - timedelta(days=5), views=500, visitors=480, mobile=10, desktop=470)
    Source.objects.create(date=today - timedelta(days=5), source="188.114.97.7", visits=40)

    d = build_dashboard(30)
    assert d["today"] == {"views": 3, "visitors": 2}
    assert d["period"] == {"views": 4, "visitors": 3}
    assert d["views_per_visitor"] == 1.3
    assert d["avg_visitors"] == 2  # 3 посетителя за 2 дня работы нового счётчика
    assert (d["bots_today"], d["bots_today_pct"]) == (3, 50)
    assert {s["source"]: (s["total"], s["utm"]) for s in d["sources"]} == {
        "Telegram": (1, 1), "прямой заход": (1, 0), "Google": (1, 0)}
    assert d["legacy_in_period"] == 500 and d["bots"][0]["total"] == 3

    raw = build_dashboard(30, raw=True)
    assert raw["period"] == {"views": 4 + 3 + 500, "visitors": 3 + 3 + 480}
    assert raw["avg_visitors"] == round((3 + 3 + 480) / 6)  # старый счётчик — с 5 дней назад
    assert dict((s["source"], s["total"]) for s in raw["sources"])["прямой заход"] == 1 + 3 + 40  # IP → прямой


def test_admin_dashboard_page(admin_client):
    today = timezone.localdate()
    make_hit(today, "/guides/", source="facebook")
    make_hit(today, bot=True)
    DailyStat.objects.create(date=today - timedelta(days=3), views=300, visitors=290)
    html = admin_client.get("/admin/stats/dailystat/?days=7").content.decode()
    assert "Посещаемость сайта" in html and "Все гайды" in html and "Facebook" in html
    assert "Отсеяно ботов сегодня: 1 (50%)" in html and "показать ботов" in html
    assert "Просмотров на посетителя" in html and "старый счётчик, с ботами" in html
    raw = admin_client.get("/admin/stats/dailystat/?days=7&bots=1")
    assert raw.status_code == 200 and "скрыть ботов" in raw.content.decode()
    assert admin_client.get("/admin/stats/dailystat/?days=abc").status_code == 200
    assert admin_client.get("/admin/stats/hit/?is_bot__exact=1").status_code == 200


# --- Пересчёт старых записей ------------------------------------------------------------------

def test_reclassify_hits_applies_current_rules_and_reports():
    today = timezone.localdate()
    stale = make_hit(today, agent="Mozilla/5.0 (compatible; GPTBot/1.2)")  # записан до нового правила
    ip_source = make_hit(today, visitor="b", source="188.114.97.0", referrer="http://188.114.97.0")
    human = make_hit(today, visitor="c", source="google", referrer="https://www.google.com")
    DailyStat.objects.create(date=today - timedelta(days=2), views=569, visitors=517)
    Source.objects.create(date=today - timedelta(days=2), source=Source.DIRECT, visits=500)
    Source.objects.create(date=today - timedelta(days=2), source="188.114.97.7", visits=9)

    out = StringIO()
    call_command("reclassify_hits", stdout=out)
    stale.refresh_from_db()
    ip_source.refresh_from_db()
    human.refresh_from_db()
    assert (stale.is_bot, stale.bot_reason) == (True, "UA: gptbot")
    assert ip_source.source == Source.DIRECT and (human.is_bot, human.source) == (False, "google")
    text = out.getvalue()
    assert "изменено по новым правилам: 2" in text and "1.10" in text and "98%" in text
    assert "Дни только со старым счётчиком (1)" in text


def test_reclassify_dry_run_changes_nothing():
    hit = make_hit(timezone.localdate(), source="188.114.97.0", referrer="http://188.114.97.0")
    call_command("reclassify_hits", "--dry-run", stdout=StringIO())
    hit.refresh_from_db()
    assert hit.source == "188.114.97.0"


def test_privacy_policy_describes_beacon_counter():
    body = Page.objects.get(slug="privacy").body
    assert "считаем собственным счётчиком без cookie" in body and "localStorage" in body
    assert "удаляется через два дня" not in body and "Если в будущем" not in body

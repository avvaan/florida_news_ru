"""Посещаемость: свой счётчик без cookie и IP, страница статистики в админке."""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Page
from stats.models import DailyStat, PageView, Source, VisitorKey

pytestmark = pytest.mark.django_db

IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 Chrome/128 Safari/537.36"


def visit(client, path="/", agent=IPHONE, ip="203.0.113.5", **extra):
    return client.get(path, HTTP_USER_AGENT=agent, REMOTE_ADDR=ip, **extra)


def test_counts_views_unique_visitors_devices_and_sources(client):
    visit(client)
    visit(client, "/guides/", HTTP_REFERER="http://testserver/")  # переход внутри сайта — не источник
    visit(client, agent=MAC, ip="198.51.100.7", HTTP_REFERER="https://www.google.com/search?q=florida")
    visit(client, agent=MAC, ip="198.51.100.8", HTTP_REFERER="https://t.me/floridaru")

    day = DailyStat.objects.get(date=timezone.localdate())
    assert (day.views, day.visitors, day.mobile, day.desktop) == (4, 3, 1, 2)
    assert dict(PageView.objects.values_list("path", "views")) == {"/": 3, "/guides/": 1}
    assert dict(Source.objects.values_list("source", "visits")) == {"прямой заход": 1, "google": 1, "telegram": 1}
    key = VisitorKey.objects.first().key
    assert "203.0.113.5" not in key and len(key) == 32  # IP не хранится


def test_skips_bots_admin_staff_errors_and_non_html(client, admin_client):
    visit(client, agent="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)")
    visit(client, agent="TelegramBot (like TwitterBot)")
    visit(client, agent="")
    visit(client, "/robots.txt")
    visit(client, "/news/net-takoj-zametki/")  # 404
    visit(client, "/admin/login/")
    admin_client.get("/", HTTP_USER_AGENT=MAC)  # редакция не считается
    assert not DailyStat.objects.exists() and not PageView.objects.exists()


def test_old_visitor_keys_are_deleted_on_new_day(client):
    VisitorKey.objects.create(date=timezone.localdate() - timedelta(days=3), key="x" * 32)
    visit(client)
    assert not VisitorKey.objects.filter(key="x" * 32).exists()


def test_admin_dashboard(client, admin_client):
    visit(client, "/guides/")
    visit(client, agent=MAC, ip="198.51.100.9", HTTP_REFERER="https://www.facebook.com/")
    page = admin_client.get("/admin/stats/dailystat/?days=7")
    html = page.content.decode()
    assert page.status_code == 200 and "Посещаемость сайта" in html
    assert "Все гайды" in html and "Главная" in html and "facebook" in html
    assert 'class="is-on"' in html and "7 дней" in html
    assert admin_client.get("/admin/stats/dailystat/?days=abc").status_code == 200


def test_privacy_policy_describes_counter():
    body = Page.objects.get(slug="privacy").body
    assert "считаем собственным счётчиком без cookie" in body and "Если в будущем" not in body

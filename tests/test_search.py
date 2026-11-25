"""Поиск по сайту: /poisk/?q=…"""

import pytest
from django.utils import timezone

from core.search import terms
from directory.models import Listing
from guides.models import Guide

pytestmark = pytest.mark.django_db


def test_terms_cut_russian_endings():
    assert terms("русского стоматолога") == ["русск", "стоматолог"]
    assert terms("SunPass в Майами") == ["sunpass", "майами"]  # короткие слова и латиница — как есть


def test_search_finds_directory_guides_and_is_noindex(client):
    Guide.objects.create(title="Как подготовиться к урагану", slug="test-uragan", teaser="Запасы, окна, эвакуация",
                         body="Текст", status=Guide.Status.PUBLISHED, published_at=timezone.now())
    html = client.get("/poisk/", {"q": "стоматолога в Майами"}).content.decode()
    dentist = Listing.objects.active().filter(category__slug="stomatologi", region__slug="miami").first()
    assert dentist.get_absolute_url() in html and 'content="noindex, follow"' in html
    guides = client.get("/poisk/", {"q": "ураган"}).content.decode()
    assert "/guides/test-uragan/" in guides
    hidden = Listing.objects.filter(is_active=False, category__slug="krasota").first()
    assert hidden.get_absolute_url() not in client.get("/poisk/", {"q": hidden.name.split()[0]}).content.decode()


def test_search_empty_and_nothing_found(client):
    assert client.get("/poisk/").status_code == 200
    html = client.get("/poisk/", {"q": "zzqxw"}).content.decode()
    assert "ничего не нашлось" in html
    assert client.get("/uk/poisk/", {"q": "стоматолог"}).status_code == 200
    assert 'href="/poisk/"' in client.get("/").content.decode()  # ссылка в шапке

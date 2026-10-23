import pytest
from django.core.cache import cache

from core.models import SiteSettings

pytestmark = pytest.mark.django_db


def test_dmca_and_corrections_pages_open(client):
    assert client.get("/dmca/").status_code == 200
    assert client.get("/corrections/").status_code == 200


def test_footer_has_legal_links_and_owner(client):
    html = client.get("/").content.decode()
    assert "CITRUSTACK LLC. Florida RU — florida-ru.com" in html
    for href in ("/about/", "/guides/", "/links/", "/p/advertising/", "/corrections/", "/dmca/", "/p/privacy/", "/p/contacts/"):
        assert f'href="{href}"' in html


def test_dmca_page_shows_agent(client):
    SiteSettings.objects.update(dmca_agent_email="agent@example.com", dmca_agent_phone="+1 305 555 0100",
                                dmca_agent_address="1 Example St\nMiami, FL 33101")
    html = client.get("/dmca/").content.decode()
    assert "Designated Agent: John Suvorov" in html and "CITRUSTACK LLC" in html
    assert 'href="mailto:agent@example.com"' in html and "Phone: " in html and "Miami, FL 33101" in html
    assert "https://dmca.copyright.gov/osp/" in html and 'href="/corrections/"' in html


def test_corrections_links_contact_email(client):
    SiteSettings.objects.update(contact_email="news@example.com")
    html = client.get("/corrections/").content.decode()
    assert "mailto:news@example.com" in html and 'href="/dmca/"' in html


def test_sitemap_lists_legal_pages(client):
    cache.clear()  # sitemap кэшируется на 10 минут — не оставляем свой ответ другим тестам
    xml = client.get("/sitemap.xml").content.decode()
    cache.clear()
    assert "/dmca/</loc>" in xml and "/corrections/</loc>" in xml


def test_contact_email_is_in_footer_and_contacts(client):
    assert SiteSettings.load().contact_email == "info@florida-ru.com"
    html = client.get("/").content.decode()
    assert 'href="mailto:info@florida-ru.com"' in html
    assert "info@florida-ru.com" in client.get("/p/contacts/").content.decode()

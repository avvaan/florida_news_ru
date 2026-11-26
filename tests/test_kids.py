"""«Детям»: модель кружка, фильтры, правило noindex для тонких страниц, форма, жалобы, импорт CSV, разметка."""

import json
import re
from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from kids import filters
from kids.importer import import_csv
from kids.models import City, Club, ClubReport, Esa, Format

from .helpers import FIXTURES

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def empty_catalog(request):
    """Миграция 0003 публикует первые кружки; тестам фильтров и правил нужен пустой каталог."""
    if not request.node.name.startswith("test_first_clubs"):
        ClubReport.objects.all().delete()
        Club.objects.all().delete()


def city(slug="orlando"):
    return City.objects.get(slug=slug)


def make(name, category="shakhmaty", city_slug="orlando", status=Club.Status.PUBLISHED, **kw):
    return Club.objects.create(name=name, category=category, status=status,
                               city=city(city_slug) if city_slug else None, **kw)


def robots(html: str) -> str:
    return re.search(r'<meta name="robots" content="([^"]*)"', html).group(1)


def ld(html: str) -> dict:
    out = {}
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        data = json.loads(block)
        kind = data["@type"]
        out[kind if isinstance(kind, str) else "+".join(kind)] = data
    return out


# --- первые кружки (миграция 0003) ---

def test_first_clubs_published_by_migration(client):
    published = Club.objects.filter(status=Club.Status.PUBLISHED)
    assert published.count() == 7 and set(published.values_list("city__slug", flat=True)) == {"orlando"}
    assert Club.objects.get(name="Bilingual Bridges").status == Club.Status.DRAFT  # нет города и формата
    yulia = Club.objects.get(name="Yulia's Piano Studio")
    assert yulia.last_verified_at is None and "без ручной сверки" in yulia.editor_note  # ресёрч не сверен
    assert yulia.lang_ru and yulia.lang_uk and "Киев" not in yulia.description
    assert Club.objects.get(website="https://russianballetorlando.org/").last_verified_at.isoformat() == "2026-10-17"
    html = client.get("/deti/").content.decode()
    assert "Yulia&#x27;s Piano Studio" in html and "Ещё не проверено редакцией" in html
    assert robots(html).startswith("index")


# --- модель ---

def test_seeded_cities_with_ukrainian_names():
    assert City.objects.count() == 15
    longwood = city("longwood")
    assert longwood.name_locative == "в Лонгвуде" and longwood.name_locative_uk == "у Лонгвуді"
    assert not longwood.uk_outdated  # перевод уже есть — ИИ его не переписывает
    assert city("lake-nona").lat and city("daytona-beach").name_en == "Daytona Beach"


def test_city_slug_cannot_take_category_or_service_address():
    for slug in ("shakhmaty", "kruzhok", "dobavit"):
        with pytest.raises(ValidationError):
            City(name="X", name_en="X", name_locative="в X", slug=slug).full_clean()


def test_club_defaults_slug_and_unknowns():
    club = make("Шахматы «Ладья»")
    assert club.slug == "shakhmaty-ladya-orlando"
    assert club.esa_status == Esa.UNKNOWN and club.age_text == "" and club.languages == []
    twin = make("Шахматы «Ладья»")
    assert twin.slug == "shakhmaty-ladya-orlando-2"


def test_club_validation_and_helpers():
    club = Club(name="A", category="muzyka", age_min=10, age_max=5, status=Club.Status.PUBLISHED)
    with pytest.raises(ValidationError):
        club.clean()  # возраст «до» меньше «от» и очные занятия без города
    club = make("B", age_min=5, lang_ru=True, lang_bilingual=True, esa_status=Esa.YES, esa_pep=True,
                esa_ftc=True, whatsapp="(407) 555-0100", telegram="@club")
    assert club.age_text == "от 5 лет" and club.languages == ["русский", "двуязычный"]
    assert club.esa_programs == ["PEP", "FTC"]
    assert club.whatsapp_url == "https://wa.me/14075550100" and club.telegram_url == "https://t.me/club"
    assert club.point == (city().lat, city().lng) and not club.point_is_exact  # центр города


def test_stale_queryset():
    fresh = make("Fresh", last_verified_at=timezone.localdate())
    old = make("Old", last_verified_at=timezone.localdate() - timedelta(days=91))
    never = make("Never")
    assert set(Club.objects.stale()) == {old, never} and fresh not in Club.objects.stale()


# --- фильтры ---

@pytest.fixture
def catalog():
    return {
        "chess_orl": make("Chess Orlando", age_min=6, age_max=12, lang_ru=True, esa_status=Esa.YES, esa_pep=True),
        "chess_lw": make("Chess Longwood", city_slug="longwood", age_min=8, lang_uk=True),
        "chess_online": make("Chess Online", city_slug=None, format=Format.ONLINE, lang_ru=True,
                             esa_status=Esa.YES, esa_fes_ua=True),
        "dance_orl": make("Dance Orlando", category="tantsy", age_min=3, age_max=7, lang_ru=True, format=Format.BOTH),
        "music_any": make("Music No Age", category="muzyka", city_slug="winter-park", lang_en=True),
        "draft": make("Draft Club", status=Club.Status.DRAFT, lang_ru=True),
    }


def names(f):
    return {c.name for c in filters.find(f)}


def test_filters_each_and_combined(catalog):
    F = filters.Filters
    assert "Draft Club" not in names(F())
    assert names(F(category="shakhmaty")) == {"Chess Orlando", "Chess Longwood", "Chess Online"}
    assert names(F(city=city())) == {"Chess Orlando", "Dance Orlando"}
    # возраст не указан — кружок тоже показываем, но после тех, где возраст подходит точно
    assert names(F(age=5)) == {"Dance Orlando", "Music No Age", "Chess Online"}
    assert [c.name for c in filters.find(F(age=5))][0] == "Dance Orlando"
    assert names(F(lang="uk")) == {"Chess Longwood"}
    assert names(F(esa="any")) == {"Chess Orlando", "Chess Online"}
    assert names(F(esa="fes-ua")) == {"Chess Online"}
    assert names(F(format="online")) == {"Chess Online", "Dance Orlando"}
    assert names(F(format="offline")) == {"Chess Orlando", "Chess Longwood", "Dance Orlando", "Music No Age"}
    # комбинации
    assert names(F(category="shakhmaty", age=10, lang="ru")) == {"Chess Orlando", "Chess Online"}
    assert names(F(category="shakhmaty", city=city(), esa="pep", format="offline")) == {"Chess Orlando"}
    assert names(F(category="tantsy", lang="uk")) == set()


def test_parse_extra_drops_garbage():
    f = filters.parse_extra({"age": "abc", "lang": "xx", "esa": "pep", "format": "online", "page": "2"})
    assert f.extra == {"esa": "pep", "format": "online"}
    assert filters.parse_extra({"age": "40"}).age is None and filters.parse_extra({"age": "7"}).age == 7


def test_list_pages_combine_filters(client, catalog):
    html = client.get("/deti/shakhmaty/?age=10&lang=ru").content.decode()
    assert "Chess Orlando" in html and "Chess Online" in html and "Chess Longwood" not in html
    html = client.get("/deti/shakhmaty/orlando/?esa=pep").content.decode()
    assert "Chess Orlando" in html and "Chess Online" not in html


def test_filter_form_redirects_to_pretty_url(client, catalog):
    resp = client.get("/deti/?cat=shakhmaty&city=orlando")
    assert resp.status_code == 301 and resp["Location"] == "/deti/shakhmaty/orlando/"
    resp = client.get("/deti/?cat=shakhmaty&city=&age=7&lang=&esa=&format=")
    assert resp.status_code == 302 and resp["Location"] == "/deti/shakhmaty/?age=7"
    assert client.get("/deti/nesushchestvuet/").status_code == 404
    assert client.get("/deti/orlando/shakhmaty/").status_code == 404  # город всегда второй


def test_empty_result_shows_message_and_noindex(client, catalog):
    html = client.get("/deti/tantsy/?lang=uk").content.decode()
    assert "По этим условиям кружков пока нет" in html and robots(html) == "noindex, follow"
    assert 'href="/deti/tantsy/"' in html  # «Убрать фильтры»


# --- правило noindex для тонких страниц ---

def test_is_indexable_rule():
    F = filters.Filters
    assert filters.is_indexable(3, F(category="shakhmaty"))
    assert not filters.is_indexable(2, F(category="shakhmaty"))
    assert not filters.is_indexable(10, F(category="shakhmaty", age=5))


def test_thin_pages_are_noindex_and_out_of_sitemap(client, catalog):
    assert robots(client.get("/deti/shakhmaty/").content.decode()).startswith("index")  # 3 кружка
    assert robots(client.get("/deti/shakhmaty/orlando/").content.decode()) == "noindex, follow"  # 1 кружок
    assert robots(client.get("/deti/orlando/").content.decode()) == "noindex, follow"  # 2 кружка
    assert robots(client.get("/deti/shakhmaty/?format=online").content.decode()) == "noindex, follow"
    assert robots(client.get("/deti/").content.decode()).startswith("index")  # 5 опубликованных
    make("Chess Orlando 2")
    make("Chess Orlando 3")
    assert robots(client.get("/deti/shakhmaty/orlando/").content.decode()).startswith("index")
    from django.core.cache import cache

    cache.clear()  # sitemap.xml кэшируется на 10 минут (config/urls.py)
    xml = client.get("/sitemap.xml").content.decode()
    assert "/deti/shakhmaty/orlando/</loc>" in xml and "/deti/shakhmaty/</loc>" in xml
    assert "/deti/tantsy/</loc>" not in xml and "/deti/longwood/</loc>" not in xml
    assert "/deti/kruzhok/chess-orlando-orlando/</loc>" in xml and "draft-club" not in xml
    assert "/deti/stipendii-pep-fes/</loc>" in xml and "/uk/deti/stipendii-pep-fes/" not in xml  # только по-русски


def test_empty_catalog_is_noindex(client):
    html = client.get("/deti/").content.decode()
    assert robots(html) == "noindex, follow" and "Каталог только начинает наполняться" in html


def test_seo_titles(client, catalog):
    for n in range(2):
        make(f"Chess Longwood {n}", city_slug="longwood")
    html = client.get("/deti/shakhmaty/orlando/").content.decode()
    assert "<title>Кружки по шахматам для детей в Орландо — на русском языке — TutFlorida</title>" in html
    assert ">Кружки по шахматам для детей в Орландо</h1>" in html
    html = client.get("/deti/longwood/").content.decode()
    # в Лонгвуде 1 из 3 кружков на украинском, 2 — без указанного языка: обещать «на русском» нельзя
    assert "<title>Детские кружки и секции в Лонгвуде — TutFlorida</title>" in html
    assert 'rel="canonical" href="http://localhost:8000/deti/longwood/"' in html
    data = ld(html)
    assert data["ItemList"]["numberOfItems"] == 3
    assert [i["name"] for i in data["BreadcrumbList"]["itemListElement"]] == ["Главная", "Детям", "Лонгвуд"]


def test_ukrainian_version(client, catalog):
    html = client.get("/uk/deti/shakhmaty/orlando/").content.decode()
    assert "Chess Orlando" in html and "в Орландо" in html


# --- карточка ---

def test_club_page_markup_verified_date_and_report_button(client, catalog):
    club = catalog["chess_orl"]
    club.last_verified_at = timezone.datetime(2026, 11, 20).date()
    club.address, club.lat, club.lng = "100 Test St, Orlando, FL", 28.54, -81.38
    club.save()
    html = client.get(club.get_absolute_url()).content.decode()
    assert "Информация проверена 20 ноября 2026" in html
    assert "Сообщить об ошибке" in html and 'action="/deti/kruzhok/chess-orlando-orlando/oshibka/"' in html
    org = ld(html)["EducationalOrganization+LocalBusiness"]
    assert org["address"]["streetAddress"] == "100 Test St, Orlando, FL" and org["geo"]["latitude"] == 28.54
    assert "aggregateRating" not in org and "review" not in org
    assert "Стоимость</dt><dd>не указано" in html.replace("\n", "").replace("  ", "")
    online = client.get(catalog["chess_online"].get_absolute_url()).content.decode()
    assert "EducationalOrganization" in ld(online) and "maps.google.com" not in online


def test_draft_hidden_archived_noindex(client, catalog):
    draft = catalog["draft"]
    assert client.get(draft.get_absolute_url()).status_code == 404
    staff = User.objects.create_user("ed", password="x", is_staff=True)
    client.force_login(staff)
    html = client.get(draft.get_absolute_url()).content.decode()
    assert "Черновик" in html and robots(html) == "noindex, follow"
    client.logout()
    club = catalog["dance_orl"]
    club.status = Club.Status.ARCHIVED
    club.save()
    html = client.get(club.get_absolute_url()).content.decode()
    assert "в архиве" in html and robots(html) == "noindex, follow"


def test_photo_shown_only_with_owner_permission(client, catalog):
    from gallery.models import MediaItem
    from kids.models import ClubPhoto

    club = catalog["chess_orl"]
    media = MediaItem.objects.create(kind="photo", url="https://example.com/a.jpg", storage="external")
    photo = ClubPhoto.objects.create(club=club, media=media)
    assert "example.com/a.jpg" not in client.get(club.get_absolute_url()).content.decode()
    photo.permission_confirmed = True
    photo.save()
    assert "example.com/a.jpg" in client.get(club.get_absolute_url()).content.decode()


def test_report_creates_record(client, catalog):
    club = catalog["chess_orl"]
    resp = client.post(club.get_report_url(), {"reason": "outdated", "comment": "Переехали"})
    assert resp.status_code == 302 and resp["Location"].endswith("?report=sent#report")
    report = ClubReport.objects.get()
    assert report.club == club and report.reason == "outdated" and report.ip_hash
    assert "Спасибо! Редакция проверит карточку." in client.get(resp["Location"]).content.decode()
    client.post(club.get_report_url(), {"reason": "error", "company": "bot"})  # ловушка для ботов
    assert ClubReport.objects.count() == 1


# --- форма «Добавить кружок» ---

FORM = {
    "submitter_role": "parent", "name": "Кружок робототехники", "category": "robototekhnika",
    "format": "offline", "city_choice": "oviedo", "age_min": "8", "age_max": "14", "languages": ["ru", "en"],
    "description": "Собираем роботов и учимся программировать, занятия в небольших группах.",
    "esa_status": "unknown", "esa_programs": ["pep"], "website": "https://robo.example.com/",
    "submitter_name": "Анна", "submitter_email": "anna@example.com", "agree": "on",
}


def test_submit_form_creates_draft(client):
    page = client.get("/deti/dobavit/").content.decode()
    assert robots(page) == "noindex, follow" and 'name="city_choice"' in page
    resp = client.post("/deti/dobavit/", FORM)
    assert resp.status_code == 302 and resp["Location"] == "/deti/dobavit/spasibo/"
    club = Club.objects.get()
    assert club.status == Club.Status.DRAFT and club.origin == Club.Origin.FORM
    assert club.city == city("oviedo") and club.lang_ru and club.lang_en and not club.lang_uk
    assert club.esa_status == Esa.UNKNOWN and not club.esa_pep  # программы без «принимает» не сохраняем
    assert club.submitter_email == "anna@example.com" and club.ip_hash
    assert client.get(club.get_absolute_url()).status_code == 404  # до проверки редакцией не виден


def test_submit_form_validation_other_city_and_bot(client):
    bad = {**FORM, "website": "", "city_choice": ""}
    html = client.post("/deti/dobavit/", bad).content.decode()
    assert "Укажите хотя бы один способ связи" in html and "Укажите город" in html
    assert not Club.objects.exists()
    client.post("/deti/dobavit/", {**FORM, "city_choice": "other", "city_other": "Deltona"})
    assert Club.objects.get().city is None and "Deltona" in Club.objects.get().editor_note
    client.post("/deti/dobavit/", {**FORM, "company": "spam"})
    assert Club.objects.count() == 1


# --- импорт CSV ---

def test_import_csv_five_rows_idempotent():
    report = import_csv(FIXTURES / "kids_sample.csv")
    assert len(report.created) == 5 and not report.errors, report.errors
    chess = Club.objects.get(website="https://chess.example.com/")
    assert chess.status == Club.Status.PUBLISHED and chess.lang_ru and chess.lang_en
    assert chess.esa_status == Esa.YES and chess.esa_pep and chess.esa_fes_ua and not chess.esa_ftc
    assert chess.origin == Club.Origin.IMPORT and chess.last_verified_at.isoformat() == "2026-11-20"
    dance = Club.objects.get(slug="test-dance")
    assert dance.category == "tantsy" and dance.city == city("longwood") and dance.status == Club.Status.DRAFT
    assert dance.esa_status == Esa.UNKNOWN and dance.age_max is None
    online = Club.objects.get(category="robototekhnika")
    assert online.city is None and online.format == Format.ONLINE and online.lang_bilingual
    swim = Club.objects.get(category="plavanie")
    assert swim.format == Format.BOTH and swim.esa_ftc and swim.last_verified_at.isoformat() == "2026-11-20"

    again = import_csv(FIXTURES / "kids_sample.csv")
    assert len(again.created) == 0 and len(again.unchanged) == 5 and Club.objects.count() == 5


def test_import_matches_by_website_and_keeps_filled_fields():
    import_csv(FIXTURES / "kids_sample.csv")
    csv = ("name,website,price_text,description\n"
           "Тестовый шахматный кружок,http://chess.example.com,$100 в месяц,\n")
    report = import_csv(StringIO(csv))
    assert len(report.updated) == 1 and Club.objects.count() == 5
    chess = Club.objects.get(website="https://chess.example.com/")
    assert chess.price_text == "$100 в месяц"
    assert chess.description == "Тестовая запись для проверки импорта."  # пустая ячейка не стирает


def test_import_reports_bad_rows_and_dry_run():
    csv = ("name,category,city,age_min\n"
           "Без города,shakhmaty,Атлантида,5\n"
           "Без направления,,Orlando,5\n"
           "Плохой возраст,muzyka,Orlando,сто\n"
           "Хорошая,muzyka,Orlando,5\n")
    report = import_csv(StringIO(csv))
    assert len(report.created) == 1 and len(report.errors) == 3
    assert report.errors[0][0] == 2 and "Атлантида" in report.errors[0][1]
    dry = import_csv(StringIO("name,category\nНовая,muzyka\n"), dry_run=True)
    assert len(dry.created) == 1 and not Club.objects.filter(name="Новая").exists()
    with pytest.raises(ValueError):
        import_csv(StringIO("name,unknown_column\nX,1\n"))
    semi = import_csv(StringIO("name;category;description\nYulia's Studio;muzyka;Уроки, для детей\nЛишняя;muzyka;a;b\n"))
    assert [c.name for c in semi.created] == ["Yulia's Studio"] and "больше ячеек" in semi.errors[0][1]


def test_import_command_and_directory_export_file():
    out = StringIO()
    call_command("import_clubs", str(FIXTURES / "kids_sample.csv"), "--dry-run", stdout=out)
    assert "создано: 5" in out.getvalue() and not Club.objects.exists()
    from django.conf import settings

    report = import_csv(settings.BASE_DIR / "kids" / "data" / "from_directory_central_fl.csv")
    assert len(report.created) == 3 and not report.errors
    assert set(Club.objects.values_list("status", flat=True)) == {Club.Status.DRAFT}


# --- страница о стипендиях, меню, тег Search Console ---

def test_esa_page_public_without_editor_markers(client):
    html = client.get("/deti/stipendii-pep-fes/").content.decode()
    assert robots(html).startswith("index") and "stepupforstudents.org" in html
    assert "ПРОВЕРИТЬ" not in html and "Черновик" not in html  # пометки — только в комментариях шаблона
    assert '<link rel="alternate" hreflang="uk"' not in html and 'href="/uk/deti/" hreflang="uk"' in html
    assert client.get("/uk/deti/stipendii-pep-fes/").status_code == 404
    assert 'href="/deti/stipendii-pep-fes/"' in client.get("/deti/").content.decode()


def test_esa_page_can_be_hidden_again(client, monkeypatch):
    from kids import seo

    monkeypatch.setattr(seo, "ESA_PAGE_VERIFIED", False)
    assert client.get("/deti/stipendii-pep-fes/").status_code == 404
    client.force_login(User.objects.create_user("ed", password="x", is_staff=True))
    html = client.get("/deti/stipendii-pep-fes/").content.decode()
    assert robots(html) == "noindex, nofollow" and "Черновик" in html


def test_menu_and_footer_link(client):
    html = client.get("/").content.decode()
    assert 'href="/deti/"' in html and ">Детям<" in html


def test_search_finds_clubs(client, catalog):
    html = client.get("/poisk/?q=Chess").content.decode()
    assert "Детские кружки" in html and "Chess Orlando" in html and "Draft Club" not in html


@pytest.mark.parametrize("value", ["google-site-verification=ABC123", "ABC123", "  ABC123 "])
def test_google_verification_meta_has_only_code(client, value, monkeypatch):
    monkeypatch.setenv("GOOGLE_SITE_VERIFICATION", value)
    import importlib

    from config import settings as conf

    importlib.reload(conf)
    with override_settings(GOOGLE_SITE_VERIFICATION=conf.GOOGLE_SITE_VERIFICATION):
        html = client.get("/").content.decode()
    assert '<meta name="google-site-verification" content="ABC123">' in html


def test_static_files_have_no_dangling_source_maps():
    """Сборка статики (collectstatic с хэшами) падает на ссылке sourceMappingURL на несуществующий файл:
    так образ не собирался и автодеплой откатывался. Проверяем все JS и CSS в static/."""
    from django.conf import settings

    root = settings.BASE_DIR / "static"
    for path in [*root.rglob("*.js"), *root.rglob("*.css")]:
        for ref in re.findall(r"sourceMappingURL=([^\s*]+)", path.read_text(encoding="utf-8", errors="ignore")):
            assert (path.parent / ref).exists(), f"{path.relative_to(root)} ссылается на отсутствующий {ref}"

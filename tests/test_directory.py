"""Справочник: полезные официальные ссылки и рекомендации бизнесов по категориям."""

import json
import re

import pytest

from directory.models import Category, Listing

pytestmark = pytest.mark.django_db


def ld(html: str) -> dict:
    return {d["@type"]: d for d in (json.loads(b) for b in
            re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S))}


def test_seeded_categories_and_st_nina_church():
    assert Category.objects.filter(kind="links").count() == 9
    assert Category.objects.filter(kind="business").count() == 21
    church = Listing.objects.get(category__slug="cerkvi", url="https://www.stninaorlando.org/")
    assert church.is_recommended
    assert church.region.slug == "orlando" and "Hanging Moss" in church.address


def test_index_lists_official_links_and_business_categories(client):
    html = client.get("/links/").content.decode()
    assert "Официальные ссылки" in html and "https://www.flhsmv.gov/" in html
    assert 'href="/links/cerkvi/"' in html and "1 место" in html and "Пока пусто — предложите" in html
    assert ">Справочник<" in client.get("/").content.decode()  # пункт меню


def test_church_page_has_local_business_markup(client):
    html = client.get("/links/cerkvi/").content.decode()
    assert "stninaorlando.org" in html and "Рекомендуем" in html
    item = ld(html)["ItemList"]["itemListElement"][0]["item"]
    assert item["@type"] == "Church" and item["address"]["streetAddress"].startswith("6832 Hanging Moss")
    assert 'content="index, follow' in html


def test_empty_category_is_noindex_and_partner_is_labelled_first(client):
    assert 'content="noindex, follow"' in client.get("/links/strahovanie/").content.decode()  # только скрытые
    avto = Category.objects.get(slug="strahovanie")
    Listing.objects.create(category=avto, name="Клиника А", url="https://a.example/")
    Listing.objects.create(category=avto, name="Клиника Б", url="https://b.example/", is_partner=True)
    html = client.get("/links/strahovanie/").content.decode()
    assert html.index("Клиника Б") < html.index("Клиника А") and "Партнёр" in html
    assert 'content="index, follow' in html


def test_guide_link_shown_only_for_published_guide(client):
    listing = Listing.objects.get(url="https://www.flhsmv.gov/")
    assert listing.guide_slug == "prava-vo-floride-dlya-priezzhih"
    html = client.get("/links/dokumenty-i-immigraciya/").content.decode()
    assert "Подробнее в гайде" not in html  # стартовый гайд — черновик, ссылку не показываем


def test_sitemap_includes_only_filled_categories(client):
    from django.core.cache import cache

    cache.clear()  # sitemap кэшируется на 10 минут
    sitemap = client.get("/sitemap.xml").content.decode()
    assert "/links/</loc>" in sitemap and "/links/cerkvi/</loc>" in sitemap
    assert "/links/vrachi/</loc>" in sitemap and "/links/strahovanie/</loc>" not in sitemap
    assert "/links/produkty/</loc>" in sitemap  # «Лакомка» и Green Hills включены


def test_businesses_from_editor_table():
    from directory.models import Listing

    business = Listing.objects.filter(category__kind="business")
    assert business.filter(name__startswith="Wayside").exists() and business.filter(category__slug="cerkvi").exists()
    hidden = set(business.filter(is_active=False).values_list("name", flat=True))
    assert {"Romashka Euro Deli", "Klondike"} <= hidden or "Romashka Euro Deli" in hidden
    assert not any(name.startswith("Lacomka") for name in hidden)  # «Лакомку» проверили и включили
    assert all(Listing.objects.filter(name__in=hidden).values_list("editor_note", flat=True))
    gesheva = business.get(name__startswith="Irena Gesheva")
    assert gesheva.phone == "(941) 629-2900" and "/doctor/irena-gesheva-md/" in gesheva.url


def test_category_region_filter(client):
    doctors = Listing.objects.active().filter(category__slug="vrachi")
    html = client.get("/links/vrachi/").content.decode()
    assert f"Все ({doctors.count()})" in html and "Другие города" in html
    assert html.index("Джексонвилл") < html.index("Палметто")  # регионы раньше «других городов»
    tampa = client.get("/links/vrachi/?region=tampa").content.decode()
    assert tampa.count('class="dir__card"') == doctors.filter(region__slug="tampa").count() > 1
    assert 'content="noindex, follow"' in tampa
    produkty = client.get("/links/produkty/").content.decode()
    assert "Romashka" not in produkty and "Kalinka" in produkty  # Ромашка ждёт проверки, Калинку проверили


def test_wayside_family_dental(client):
    from directory.models import Listing

    item = Listing.objects.get(name__startswith="Wayside Family Dental")
    assert item.category.slug == "stomatologi" and item.is_recommended and item.is_active
    assert item.phone == "(407) 732-4570" and item.region.slug == "orlando"
    html = client.get("/links/stomatologi/").content.decode()
    assert html.index("Wayside Family Dental") < html.index("Tetri") and "Рекомендуем" in html


def test_batch2_additions(client):
    from directory.models import Listing

    lacomka = Listing.objects.get(name__startswith="Lacomka")
    assert lacomka.is_active and lacomka.phone == "(407) 677-1101" and "Winter Park" in lacomka.address
    for name, slug in (("Green Hills", "produkty"), ("Мария — логопед", "deti"), ("Circus Dog Show", "prazdniki"),
                       ("Argo Restaurant", "restorany"), ("Zefir Milenia", "podarki"), ("Revivery", "krasota"),
                       ("Golden Age", "pozhilye"), ("Sofia Art Academy", "deti"), ("Alexander Miloserdov", "krasota"),
                       ("GroomBoom", "zhivotnye"), ("EuroHome", "produkty"), ("Funky Fresh", "podarki"),
                       ("All Green Project", "deti"), ("Mariia Delibaltova", "krasota")):
        item = Listing.objects.get(name__startswith=name)
        assert item.category.slug == slug and item.is_active, name
    html = client.get("/links/produkty/").content.decode()
    assert "Green Hills" in html and "Лакомка" in html


def test_batch3_verified_table():
    from directory.models import Listing

    assert Listing.objects.get(name__startswith="Kalinka").is_active
    citrin = Listing.objects.get(name__startswith="Mark Citrin")
    assert citrin.phone == "(305) 899-9919" and citrin.description  # дополнили, описание не затёрли
    assert Listing.objects.get(name__startswith="Alenka").phone == "(407) 910-7351"
    for name in ("Law Offices of George Lambert", "Toyota of Hollywood", "Valeria Studio — брови и ресницы"):
        assert not Listing.objects.get(name=name).is_active, name


def test_category_icons(client):
    for cat in Category.objects.all():
        assert cat.icon == f"directory/{cat.slug}.webp", cat.slug  # у каждой стартовой категории есть иконка
    html = client.get("/links/").content.decode()
    assert html.count('class="dir__icon') == Category.objects.count()
    assert "directory/cerkvi" in client.get("/links/cerkvi/").content.decode()


def test_orthodox_parishes_batch(client):
    from directory.models import Listing

    churches = Listing.objects.filter(category__slug="cerkvi")
    assert churches.filter(is_active=True).count() == 11  # Святая Нина + 10 приходов
    assert not churches.get(name__contains="Григория Богослова").is_active  # без адреса — скрыт
    html = client.get("/links/cerkvi/").content.decode()
    assert "Почаевской" in html and "Все (11)" in html and "stnicholasftl.org" in html


@pytest.mark.django_db
def test_batch8_ukrainian_businesses(client):
    """Таблица украинских бизнесов: с контактами — на сайте, без контактов — скрыты до проверки."""
    batch = Listing.objects.filter(editor_note__contains="Ukrainian Business in Florida")
    assert batch.count() == 62 and batch.filter(is_active=True).count() == 11
    pierogi = batch.get(name="Pierogi Bar St. Pete")
    assert pierogi.region.slug == "tampa" and pierogi.url == "https://pierogi.bar/"
    assert all(item.phone or item.url or item.address for item in batch.filter(is_active=True))
    assert "Pierogi Bar St. Pete" in client.get("/links/restorany/").content.decode()
    assert "Mudslide Coffee" not in client.get("/links/restorany/").content.decode()


@pytest.mark.django_db
def test_batch9_russian_speaking_doctors(client):
    """Врачи по всей Флориде: проверенные и «вероятно» видны, с противоречивыми источниками — скрыты до звонка."""
    batch = Listing.objects.filter(category__slug="vrachi", editor_note__contains="Сверено в ноябре 2026")
    assert batch.count() == 226 and batch.filter(is_active=False).count() == 13
    assert not batch.filter(is_active=False).exclude(editor_note__startswith="Проверка: нужен звонок").exists()
    assert all(item.languages.startswith("русский") for item in batch)
    assert all(item.url and item.address for item in batch)
    gaukhman = batch.get(name__startswith="Alexander David Gaukhman")  # был в двух регионах — одна запись
    assert gaukhman.region.slug == "miami"
    assert batch.get(name__startswith="Alla Fine").pk != batch.get(name__startswith="Alexander S. Fine").pk
    assert batch.filter(region=None, city="Пенсакола").count() == 3  # дальние места — без региона
    html = client.get("/links/vrachi/").content.decode()
    assert "Kandinov" in html and "Mighell" not in html  # скрытые не показываются
    assert "уточните при записи" in html


def test_doctor_specialty_guess():
    from directory.specialties import guess

    assert guess("Elena Ivanova, MD — педиатр, детский кардиолог (Pediatric Associates)") == "kids"
    assert guess("Ivan Petrov, MD — хирург-ортопед (позвоночник)") == "ortho"
    assert guess("Ivan Petrov, MD — терапевт, гастроэнтеролог") == "therapy"
    assert guess("Ivan Petrov, MD — эндокринолог (Family Medicine Group)") == "other"  # английское название не мешает
    assert guess("Health Comfort") == ""  # без специальности не угадываем


@pytest.mark.django_db
def test_doctors_filter_by_specialty(client):
    """На странице врачей — кнопки направлений с числом врачей; фильтр работает вместе с регионом."""
    doctors = Listing.objects.active().filter(category__slug="vrachi")
    assert not doctors.filter(specialty="").exists()  # всем врачам из таблиц направление угадано
    kids = doctors.filter(specialty="kids")
    html = client.get("/links/vrachi/?spec=kids").content.decode()
    assert html.count('class="dir__card"') == kids.count() > 5
    assert 'content="noindex, follow"' in html
    assert f'Детские врачи <span class="ads__n">{kids.count()}</span>' in html
    both = client.get("/links/vrachi/?spec=kids&region=miami").content.decode()
    assert both.count('class="dir__card"') == kids.filter(region__slug="miami").count() > 0
    assert "Все направления" in client.get("/links/vrachi/").content.decode()
    assert "Все направления" not in client.get("/links/produkty/").content.decode()  # у бизнесов направлений нет
    assert client.get("/links/vrachi/?spec=xxx").content.decode().count('class="dir__card"') == doctors.count()
    uk = client.get("/uk/links/vrachi/").content.decode()
    assert "Дитячі лікарі" in uk and "Усі напрями" in uk


def test_krasota_research_batch(client):
    import json
    from pathlib import Path

    from directory.models import Listing

    rows = json.loads((Path(__file__).parents[1] / "directory/data/businesses_2026_11_krasota.json").read_text())
    beauty = Listing.objects.filter(category__slug="krasota")
    for row in rows:
        item = beauty.get(name=row["name"])
        assert item.is_active == row["active"], row["name"]
        assert item.editor_note.startswith("Ресёрч 25.11.2026"), row["name"]
        assert item.editor_note == row["note"], row["name"]
    banya = beauty.get(name__startswith="BeachBanya")
    assert banya.phone == "(954) 921-7333" and banya.region.slug == "miami"
    html = client.get("/links/krasota/").content.decode()
    assert "BeachBanya" in html and "Eurotouch Esthetics" in html
    hidden = [row["name"] for row in rows if not row["active"]]
    assert hidden == ["Marusya Beauty Salon — салон красоты"]  # скрыт только закрывшийся бизнес
    assert "Marusya Beauty Salon" not in html and "Открыто 25.11.2026" not in html  # заметка редакции не видна читателям


def test_research_waves_imported(client):
    """Ресёрч-пакеты (businesses_2026_11_res_*.json): каждая запись в базе, видимость и заметка совпадают с таблицей."""
    import json
    from pathlib import Path

    from directory.models import Listing

    for path in sorted((Path(__file__).parents[1] / "directory/data").glob("businesses_2026_11_res_*.json")):
        for row in json.loads(path.read_text()):
            item = Listing.objects.get(category__slug=row["category"], name=row["name"])
            assert item.is_active == row["active"], row["name"]
            assert item.editor_note == row["note"] and item.editor_note.startswith("Ресёрч 25.11.2026"), row["name"]
            if row["active"]:
                assert row["phone"] or row["url"], row["name"]  # без контактов не публикуем

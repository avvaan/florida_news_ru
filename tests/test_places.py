"""«Что посетить»: карточки мест в разметке, import_places, пары ru/uk, страницы на двух языках, sitemap."""

import json
import re
from io import StringIO

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError

from guides import markup
from places import importer
from places.models import Destination

pytestmark = pytest.mark.django_db

CARD = ("[[place|{name}]]\naddress: 40001 State Road 9336, Homestead, FL 33034\nurl: {url}\n"
        "price: {price}\nhours: {hours}\nphone: +1 305-242-7700")
WORDS = {"ru": "Обычный абзац про парк, тропы и лучшее время для поездки. ",
         "uk": "Звичайний абзац про парк, стежки та найкращий час для поїздки. "}
PRICE = {"ru": "$35 за машину на 7 дней", "uk": "$35 за авто на 7 днів"}
HOURS = {"ru": "круглосуточно; визит-центр 9:00–17:00", "uk": "цілодобово; візит-центр 9:00–17:00"}


def article(lang="ru", slug="test-park", title=None, region="south", cards=3, images=8, extra=""):
    title = title or {"ru": "Тестовый парк", "uk": "Тестовий парк"}[lang]
    parts = [f"Вступление с **важным** и [ссылкой](https://www.nps.gov/ever/)."]
    for n in range(1, 7):
        parts.append(f"## Раздел {n}\n\n" + WORDS[lang] * 60)
    for n in range(cards):
        parts.append(CARD.format(name=f"Место {n}", url=f"https://www.nps.gov/place{n}/", price=PRICE[lang],
                                 hours=HOURS[lang]))
    parts += [f"[[img:{n}|Подпись {n}]]" for n in range(2, 2 + images)]
    body = "\n\n".join(parts) + extra
    return (f"---\nslug: {slug}\nlang: {lang}\ntitle: {title}\nteaser: {'Коротко о главном: что посмотреть. ' * 3}\n"
            f"region: {region}\norder: 1\nchecked: 2026-11-24\ncover_caption: Болото на закате\n"
            "source: NPS | https://www.nps.gov/ever/a | A\nsource: NPS | https://www.nps.gov/ever/b | B\n"
            f"source: FL | https://www.floridastateparks.org/c | C\n---\n{body}\n")


@pytest.fixture(autouse=True)
def fresh_cache():
    """sitemap.xml кэшируется на 10 минут — не оставляем кэш с тестовыми статьями другим тестам."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def content_dir(tmp_path, monkeypatch):
    for lang in ("ru", "uk", "photos"):
        (tmp_path / lang).mkdir()
    monkeypatch.setattr(importer, "CONTENT_DIR", tmp_path)
    return tmp_path


def write_pair(content_dir, slug="test-park", **kwargs):
    for lang in ("ru", "uk"):
        (content_dir / lang / f"{slug}.md").write_text(article(lang, slug, **kwargs), encoding="utf-8")
    photos = {str(n): {"credit": "Freepik", "stock_id": n, "title": "x"} for n in range(1, 9)}
    photos["9"] = {"credit": "NPS", "stock_id": None, "title": "Anhinga Trail",
                   "source_url": "https://www.nps.gov/media/photo/view.htm?id=1"}
    photos["8"] = {"credit": "TutFlorida", "kind": "illustration", "title": "pool"}
    (content_dir / "photos" / f"{slug}.json").write_text(json.dumps(photos), encoding="utf-8")


def run(*args):
    out = StringIO()
    call_command("import_places", *args, stdout=out)
    return out.getvalue()


def test_place_card_markup():
    blocks = markup.parse("Текст.\n\n" + CARD.format(name="Парк <b>", url="https://www.nps.gov/ever/",
                                                      price="**$35**", hours="9:00–17:00"))
    card = blocks[1]
    assert card.kind == "place" and not card.problems
    assert card.place["name"] == "Парк <b>" and card.place["hours"] == "9:00–17:00"
    assert str(card.place_html["price"]) == "<strong>$35</strong>"
    assert card.place_domain == "nps.gov/ever" and "google.com/maps" in card.map_url
    long = markup.parse(CARD.format(name="X", url="https://www.floridastateparks.org/parks-and-trails/wekiwa/",
                                    price="1", hours="2"))[0]
    assert long.place_domain == "floridastateparks.org"
    bad = markup.parse("[[place|Без полей]]\nurl: http://x.com\nцена: 5")[0]
    assert any("price" in p for p in bad.problems) and any("https" in p for p in bad.problems)
    assert any("ключ: значение" in p for p in bad.problems)
    # карточки не считаются в объём текста
    assert markup.plain_length("Текст.\n\n" + CARD.format(name="X", url="https://a.gov/", price="1", hours="2")) == 6


def test_check_reports_file_and_pair_errors(content_dir):
    write_pair(content_dir)
    (content_dir / "uk" / "test-park.md").write_text(article("uk", cards=2, images=7), encoding="utf-8")
    (content_dir / "ru" / "lonely.md").write_text(article("ru", "lonely", cards=1), encoding="utf-8")
    with pytest.raises(CommandError):
        run("--check", "--no-images")
    out = StringIO()
    with pytest.raises(CommandError):
        call_command("import_places", "--check", "--no-images", stdout=out)
    text = out.getvalue()
    assert "✓ ru/test-park.md" in text and "✗ uk/test-park.md" in text
    assert "картинки в тексте" in text and "карточек мест" in text and "нет версии uk/lonely.md" in text
    assert "карточки мест различаются" in text
    assert not Destination.objects.exists()


def test_import_publishes_pair_and_is_idempotent(content_dir):
    write_pair(content_dir)
    assert "Новых: 2" in run("--no-images")
    assert "без изменений: 2" in run("--no-images")
    ru = Destination.objects.get(slug="test-park", lang="ru")
    assert ru.is_published and ru.translation.lang == "uk" and len(ru.places) == 3
    assert ru.credit(3) == {"credit": "Freepik", "url": "", "kind": "photo"} and ru.cover == "places/test-park-1"
    assert ru.credit(9)["url"].startswith("https://www.nps.gov/")
    assert ru.image_files[0] == "places/test-park-1.jpg" and ru.image_files[1] == "places/test-park-2.webp"


def test_pages_in_both_languages(content_dir, client):
    write_pair(content_dir)
    run("--no-images")
    ru_html = client.get("/chto-posetit/test-park/").content.decode()
    uk_html = client.get("/uk/chto-posetit/test-park/").content.decode()
    assert '<html lang="ru">' in ru_html and '<html lang="uk">' in uk_html
    assert 'hreflang="uk" href="http' in ru_html and '/uk/chto-posetit/test-park/">' in ru_html
    assert 'hreflang="ru" href="http' in uk_html and 'hreflang="x-default"' in uk_html
    assert 'content="uk_UA"' in uk_html
    assert "Часы работы" in ru_html and "Години роботи" in uk_html
    assert ru_html.count('class="place"') == 3 and "nps.gov/place0" in ru_html
    assert 'href="tel:+13052427700"' in ru_html and "Фото: Freepik" in ru_html and "Фото: Freepik" in uk_html
    assert 'Фото: <a href="https://www.nps.gov/media/photo/view.htm?id=1"' in ru_html
    from django.conf import settings
    assert f"Подпись 8 · Иллюстрация {settings.SITE_NAME}" in ru_html
    assert f"Подпись 8 · Ілюстрація {settings.SITE_NAME}" in uk_html
    assert "Цены и часы работы проверены по официальным сайтам: 24 ноября 2026" in ru_html
    assert "24 листопада 2026" in uk_html
    ld = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', uk_html, re.S)]
    article_ld = next(d for d in ld if d["@type"] == "Article")
    assert article_ld["inLanguage"] == "uk" and article_ld["about"][0]["@type"] == "TouristAttraction"
    crumbs = next(d for d in ld if d["@type"] == "BreadcrumbList")
    assert [i["name"] for i in crumbs["itemListElement"]] == ["Головна", "Що відвідати", "Тестовий парк"]

    listing = client.get("/chto-posetit/").content.decode()
    assert "Тестовый парк" in listing and "Майами и юго-восток" in listing and '/uk/chto-posetit/"' in listing
    assert "Тестовий парк" in client.get("/uk/chto-posetit/").content.decode()
    home = client.get("/").content.decode()
    assert 'href="/chto-posetit/">Что посетить</a>' in home
    assert 'href="/uk/chto-posetit/">Що відвідати</a>' in client.get("/uk/").content.decode()


def test_draft_is_hidden_and_404(content_dir, client):
    write_pair(content_dir)
    for lang in ("ru", "uk"):
        path = content_dir / lang / "test-park.md"
        path.write_text(path.read_text(encoding="utf-8").replace("order: 1", "order: 1\nstatus: draft"),
                        encoding="utf-8")
    run("--no-images")
    assert client.get("/chto-posetit/test-park/").status_code == 404
    assert client.get("/chto-posetit/net-takoj/").status_code == 404
    assert "Статьи скоро появятся" in client.get("/chto-posetit/").content.decode()


def test_sitemap_lists_both_languages_with_images(content_dir, client):
    write_pair(content_dir)
    run("--no-images")
    sitemap = client.get("/sitemap.xml").content.decode()
    assert "/chto-posetit/test-park/</loc>" in sitemap and "/uk/chto-posetit/test-park/</loc>" in sitemap
    assert "/uk/chto-posetit/</loc>" in sitemap and "/static/places/test-park-9.webp</image:loc>" in sitemap


def test_real_place_files_are_valid():
    """Все статьи в репозитории проходят проверку: объём, картинки, карточки мест, пары ru/uk."""
    files = importer.content_files()
    problems = {}
    parsed = {}
    for path in files:
        item = importer.parse_file(path)
        parsed[(path.stem, path.parent.name)] = item
        if errors := importer.validate(item):
            problems[f"{path.parent.name}/{path.name}"] = errors
    for slug in {slug for slug, _ in parsed}:
        if errors := importer.validate_pair(parsed.get((slug, "ru")), parsed.get((slug, "uk"))):
            problems[f"pair {slug}"] = errors
    assert not problems

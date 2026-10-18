"""Гайды из файлов: разметка, импорт import_guides, страницы гайда и списка, проверка реальных файлов."""

from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from guides import importer, markup
from guides.models import Guide

pytestmark = pytest.mark.django_db

SECTION = "## Раздел {n}\n\n" + "Обычный абзац про документы и сроки. " * 110


def guide_text(slug="test-guide", title="Тестовый гайд", extra=""):
    body = "Вступление с **важным** и [ссылкой](https://www.flhsmv.gov/).\n\n"
    body += "\n\n".join(SECTION.format(n=n) for n in range(1, 7))
    body += ("\n\n[[img:2|Очередь в офисе]]\n\n- первый пункт\n- второй пункт\n\n1. шаг\n2. шаг\n\n"
             "> **Важно.** Сроки короткие.\n\n| Что | Сколько |\n|---|---|\n| Пошлина | $48 |\n\n"
             "## Вопросы и ответы\n\n### Вопрос?\n\nОтвет.\n\n[[img:3|Документы на столе]]" + extra)
    return (f"---\nslug: {slug}\ntitle: {title}\nteaser: Коротко о главном\nsection: docs\norder: 2\n"
            "topics: laws, roads\nsource: FLHSMV | https://www.flhsmv.gov/a/ | Страница A\n"
            "source: USCIS | https://www.uscis.gov/b | Страница B\nsource: SSA | https://www.ssa.gov/c | C\n"
            f"---\n{body}\n")


@pytest.fixture
def content_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "CONTENT_DIR", tmp_path)
    return tmp_path


def run(*args):
    out = StringIO()
    call_command("import_guides", *args, stdout=out)
    return out.getvalue()


def review_and_publish(slug="test-guide"):
    """Как редактор в админке: «проверено человеком» → публикация."""
    from guides.services import publish_guide

    guide = Guide.objects.get(slug=slug)
    guide.human_reviewed = True
    guide.save()
    with mock.patch("guides.services.post_guide", return_value="dry-run"):
        publish_guide(guide)
    return Guide.objects.get(slug=slug)


def test_markup_blocks_and_escaping():
    blocks = markup.parse(
        "## Права и <script>\n\nТекст **жирный** [тут](https://a.gov/x) и [плохо](javascript:alert(1)).\n\n"
        "## Права и <script>\n\n- a\n- b\n\n> врезка\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n[[img:2|Подпись]]"
    )
    kinds = [b.kind for b in blocks]
    assert kinds == ["h2", "p", "h2", "ul", "note", "table", "img"]
    assert "&lt;script&gt;" in blocks[0].text and blocks[0].anchor != blocks[2].anchor  # якоря уникальны
    assert '<strong>жирный</strong>' in blocks[1].text
    assert '<a href="https://a.gov/x"' in blocks[1].text and 'href="javascript' not in blocks[1].text
    assert blocks[5].head == ["A", "B"] and blocks[5].items == [["1", "2"]]
    assert blocks[6].number == 2 and blocks[6].caption == "Подпись"


def test_old_plain_body_still_renders():
    blocks = markup.parse("Текст гайда.\n\n## Набор на случай ЧС\nВода и фонарик.")
    assert [b.kind for b in blocks] == ["p", "h2", "p"]


def test_check_reports_errors_without_touching_db(content_dir):
    (content_dir / "short-guide.md").write_text(
        "---\nslug: short-guide\ntitle: Т\nteaser: А\nsection: nope\ntopics: laws\n---\nМало текста.\n"
    )
    with pytest.raises(CommandError):
        run("--check", "--no-images")
    assert not Guide.objects.filter(slug="short-guide").exists()


def test_import_creates_drafts_and_is_idempotent(content_dir, client):
    (content_dir / "test-guide.md").write_text(guide_text())
    assert "Новых: 1" in run("--no-images")
    guide = Guide.objects.get(slug="test-guide")
    assert not guide.is_published and not guide.human_reviewed  # публикует только редактор после проверки
    assert client.get(guide.get_absolute_url()).status_code == 404
    guide = review_and_publish()
    assert guide.is_published and guide.section == "docs" and guide.cover == "guides/test-guide-1"
    assert set(guide.topics.values_list("slug", flat=True)) == {"laws", "roads"}
    assert guide.sources.count() == 3 and guide.revised_at is None

    assert "без изменений: 1" in run("--no-images")  # файл не менялся — правки в админке не затираются

    (content_dir / "test-guide.md").write_text(guide_text(title="Новый заголовок", extra="\n\nДописали абзац."))
    assert "обновлено: 1" in run("--no-images")
    guide.refresh_from_db()
    assert guide.title == "Новый заголовок" and guide.revised_at is not None
    # текст изменился после проверки — снова черновик, нужна повторная проверка
    assert not guide.is_published and not guide.human_reviewed and "проверьте заново" in guide.review_notes
    guide = review_and_publish()

    page = client.get(guide.get_absolute_url()).content.decode()
    assert 'class="toc"' in page and 'href="#razdel-1"' in page and 'id="razdel-1"' in page
    assert "<table>" in page and "guide__note" in page and "<strong>важным</strong>" in page
    assert "guides/test-guide-2.webp" in page and "Очередь в офисе" in page
    assert "guides/test-guide-1.jpg" in page  # og:image

    listing = client.get("/guides/").content.decode()
    assert 'id="docs"' in listing and "Новый заголовок" in listing and "test-guide-1-640.webp" in listing


def test_home_page_links_all_guides_by_section(content_dir, client):
    (content_dir / "test-guide.md").write_text(guide_text(title="Florida ID во Флориде: как получить"))
    run("--no-images")
    review_and_publish()
    home = client.get("/").content.decode()
    assert 'class="home-guides"' in home and 'href="/guides/test-guide/"' in home
    assert ">Florida ID</a>" in home and 'href="/guides/#docs"' in home  # короткое название и раздел


def test_import_existing_starter_draft_keeps_url(content_dir):
    (content_dir / "homestead-exemption.md").write_text(guide_text(slug="homestead-exemption"))
    run("--no-images")
    assert Guide.objects.filter(slug="homestead-exemption").count() == 1
    assert review_and_publish("homestead-exemption").is_published


def test_real_guide_files_are_valid():
    """Все гайды в репозитории проходят проверку: объём, разделы, источники, картинки на месте."""
    files = importer.content_files()
    assert files, "в guides/content/ нет гайдов"
    problems = {}
    for path in files:
        errors = importer.validate(importer.parse_file(path))
        if errors:
            problems[path.name] = errors
    assert not problems


def ld_types(html: str) -> dict:
    import json
    import re

    found = {}
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        data = json.loads(block)
        found[data["@type"]] = data
    return found


def test_guide_seo_markup(content_dir, client):
    (content_dir / "test-guide.md").write_text(guide_text())
    run("--no-images")
    review_and_publish()
    html = client.get("/guides/test-guide/").content.decode()
    ld = ld_types(html)
    assert ld["FAQPage"]["mainEntity"][0]["name"] == "Вопрос?"
    assert ld["FAQPage"]["mainEntity"][0]["acceptedAnswer"]["text"] == "Ответ."
    crumbs = [i["name"] for i in ld["BreadcrumbList"]["itemListElement"]]
    assert crumbs == ["Главная", "Гайды", "Тестовый гайд"]
    assert ld["Article"]["articleSection"] == "Документы и статус" and len(ld["Article"]["image"]) == 3
    assert 'content="index, follow, max-image-preview:large' in html
    assert 'property="og:image" content="' in html and "guides/test-guide-1.jpg" in html
    assert 'property="article:section" content="Документы и статус"' in html

    listing = ld_types(client.get("/guides/").content.decode())
    assert listing["CollectionPage"]["mainEntity"]["itemListElement"][0]["url"].endswith("/guides/test-guide/")


def test_sitemap_lists_guide_images_and_404_is_noindex(content_dir, client):
    (content_dir / "test-guide.md").write_text(guide_text())
    run("--no-images")
    review_and_publish()
    from django.core.cache import cache

    cache.clear()  # sitemap кэшируется на 10 минут
    sitemap = client.get("/sitemap.xml").content.decode()
    assert "xmlns:image" in sitemap and "/static/guides/test-guide-3.jpg</image:loc>" in sitemap
    assert "/p/about/" not in sitemap  # 301 в sitemap не нужен
    assert 'content="noindex, follow"' in client.get("/net-takoj-stranicy/").content.decode()
    assert 'content="index, follow' in client.get("/").content.decode()
    assert ld_types(client.get("/").content.decode()).get("WebSite")

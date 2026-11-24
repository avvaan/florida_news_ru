"""Статьи «Что посетить» из файлов places/content/<ru|uk>/<slug>.md → база.

Файл: шапка между строками «---» и текст в разметке guides/markup.py (с карточками мест).

    ---
    slug: everglades
    lang: ru
    title: Национальный парк Эверглейдс: …
    teaser: Анонс до 300 знаков
    region: south
    order: 1
    checked: 2026-11-24
    cover_caption: Подпись к обложке
    source: NPS | https://www.nps.gov/ever/planyourvisit/fees.htm | Fees & Passes
    ---
    Текст…

Авторство фото — places/content/photos/<slug>.json: {"1": {"credit": "Freepik", "stock_id": 123, "title": "…"}, …}.
Картинки — static/places/<slug>-<N>.webp (1200×675) и -<N>-640.webp, у обложки ещё -1.jpg; готовит их place_photo.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

from guides import markup

from .i18n import LANGS, REGIONS

CONTENT_DIR = Path(__file__).resolve().parent / "content"
MIN_CHARS, MAX_CHARS = 20_000, 45_000
MIN_INLINE_IMAGES = 8          # картинок в тексте, плюс обложка
MIN_PLACES = 3                 # карточек мест в статье
MIN_SOURCES = 3
HEADER_KEYS = {"slug", "lang", "title", "teaser", "region", "order", "checked", "cover_caption", "status", "source"}
# Чего не должно остаться в готовом тексте: заглушки и пометки автора.
PLACEHOLDER_RE = re.compile(r"TODO|TBD|XXX|\?\?\?|lorem ipsum", re.I)


@dataclass
class DestinationFile:
    path: Path
    slug: str = ""
    lang: str = ""
    title: str = ""
    teaser: str = ""
    region: str = ""
    order: int = 0
    checked: datetime.date | None = None
    cover_caption: str = ""
    status: str = "published"
    sources: list[tuple[str, str, str]] = field(default_factory=list)
    body: str = ""
    raw: str = ""

    @property
    def content_hash(self) -> str:
        photos = photos_path(self.slug)
        extra = photos.read_text(encoding="utf-8") if photos.exists() else ""
        return hashlib.sha256((self.raw + extra).encode()).hexdigest()

    @property
    def cover(self) -> str:
        return f"places/{self.slug}-1"

    @property
    def blocks(self) -> list[markup.Block]:
        return markup.parse(self.body)


def photos_path(slug: str) -> Path:
    return CONTENT_DIR / "photos" / f"{slug}.json"


def load_photos(slug: str) -> dict:
    path = photos_path(slug)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def photo_credits(slug: str) -> dict[str, dict]:
    """{номер: {"credit": «Freepik», "url": страница фото или "", "kind": photo|illustration}} — для подписи."""
    return {str(n): {"credit": str(meta.get("credit", "")), "url": str(meta.get("source_url") or ""),
                     "kind": str(meta.get("kind") or "photo")}
            for n, meta in load_photos(slug).items()}


def parse_file(path: Path) -> DestinationFile:
    raw = path.read_text(encoding="utf-8")
    item = DestinationFile(path=path, raw=raw)
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw.replace("\r\n", "\n"), re.S)
    if not match:
        raise ValueError(f"{path.parent.name}/{path.name}: нет шапки между строками ---")
    header, item.body = match.group(1), match.group(2).strip()
    for line in header.split("\n"):
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key not in HEADER_KEYS:
            raise ValueError(f"{path.parent.name}/{path.name}: неизвестное поле шапки «{key}»")
        if key == "source":
            parts = [p.strip() for p in value.split("|")]
            item.sources.append((parts[0], parts[1] if len(parts) > 1 else "", parts[2] if len(parts) > 2 else ""))
        elif key == "order":
            item.order = int(value or 0)
        elif key == "checked":
            item.checked = datetime.date.fromisoformat(value)
        else:
            setattr(item, key, value)
    return item


def validate(item: DestinationFile, check_images: bool = True) -> list[str]:
    """Список проблем одного файла; пустой — файл годится к публикации."""
    errors = []
    if item.slug != item.path.stem:
        errors.append(f"slug «{item.slug}» не совпадает с именем файла")
    if not re.fullmatch(r"[a-z0-9-]{3,110}", item.slug or ""):
        errors.append("slug: только латиница, цифры и дефис")
    if item.lang not in LANGS or item.lang != item.path.parent.name:
        errors.append(f"lang «{item.lang}»: ru или uk, как папка файла")
    if not item.title or len(item.title) > 160:
        errors.append(f"title: обязателен, до 160 знаков (сейчас {len(item.title)})")
    if not 50 <= len(item.teaser) <= 300:
        errors.append(f"teaser: 50–300 знаков (сейчас {len(item.teaser)})")
    if item.region not in REGIONS:
        errors.append(f"region: одно из {', '.join(REGIONS)}")
    if not item.checked:
        errors.append("checked: дата проверки цен и часов, ГГГГ-ММ-ДД")
    if not item.cover_caption:
        errors.append("cover_caption: подпись к обложке обязательна")
    if item.status not in {"published", "draft"}:
        errors.append("status: published или draft")
    if len(item.sources) < MIN_SOURCES:
        errors.append(f"source: нужно минимум {MIN_SOURCES} официальных источника")
    for name, url, _title in item.sources:
        if not name or not url.startswith("https://"):
            errors.append(f"source «{name}»: нужно «Название | https://… | заголовок страницы»")

    length = markup.plain_length(item.body)
    if not MIN_CHARS <= length <= MAX_CHARS:
        errors.append(f"объём {length} знаков без карточек мест, нужно {MIN_CHARS}–{MAX_CHARS}")
    blocks = item.blocks
    if sum(b.kind == "h2" for b in blocks) < 6:
        errors.append("нужно минимум 6 разделов «## »")
    if re.search(r"^# ", item.body, re.M):
        errors.append("заголовок «# » не нужен — он берётся из title")
    if re.search(r"<[a-zA-Z/][^>]*>", item.body):
        errors.append("HTML-теги в тексте не допускаются")
    if found := PLACEHOLDER_RE.search(item.body):
        errors.append(f"в тексте осталась заглушка «{found.group(0)}»")
    if re.search(r"\]\((?!https://)", item.body):
        errors.append("ссылки в тексте — только полные https://…")

    images = [b.number for b in blocks if b.kind == "img"]
    expected = list(range(2, 2 + max(len(images), MIN_INLINE_IMAGES)))
    if sorted(images) != expected:
        errors.append(f"картинки в тексте: нужно по одной [[img:2…]] … [[img:{expected[-1]}…]] "
                      f"(минимум {MIN_INLINE_IMAGES}), сейчас {images}")
    if any(b.kind == "img" and not b.caption for b in blocks):
        errors.append("у каждой картинки нужна подпись: [[img:2|Подпись]]")

    places = [b for b in blocks if b.kind == "place"]
    if len(places) < MIN_PLACES:
        errors.append(f"карточек мест «[[place|…]]» {len(places)}, нужно минимум {MIN_PLACES}")
    for block in places:
        errors += [f"карточка «{block.place['name']}»: {problem}" for problem in block.problems]

    photos = load_photos(item.slug)
    for n in (1, *images):
        meta = photos.get(str(n))
        if not meta or not meta.get("credit"):
            errors.append(f"photos/{item.slug}.json: нет записи об авторстве картинки {n}")
        elif (meta.get("kind") != "illustration" and not meta.get("stock_id")
              and not str(meta.get("source_url", "")).startswith("https://")):
            errors.append(f"photos/{item.slug}.json: у картинки {n} нет ни stock_id, ни source_url")
    if check_images:
        static = Path(settings.BASE_DIR) / "static" / "places"
        for n in (1, *images):
            for suffix in (".webp", "-640.webp", *([".jpg"] if n == 1 else [])):
                if not (static / f"{item.slug}-{n}{suffix}").exists():
                    errors.append(f"нет картинки static/places/{item.slug}-{n}{suffix}")
    return errors


def validate_pair(ru: DestinationFile | None, uk: DestinationFile | None) -> list[str]:
    """Русская и украинская версии одной статьи: обе есть и описывают одно и то же."""
    if not ru or not uk:
        missing = "uk" if ru else "ru"
        return [f"нет версии {missing}/{(ru or uk).slug}.md"]
    errors = []
    for attr in ("region", "order", "checked"):
        if getattr(ru, attr) != getattr(uk, attr):
            errors.append(f"{attr} различается: ru «{getattr(ru, attr)}», uk «{getattr(uk, attr)}»")
    ru_images = sorted(b.number for b in ru.blocks if b.kind == "img")
    uk_images = sorted(b.number for b in uk.blocks if b.kind == "img")
    if ru_images != uk_images:
        errors.append(f"картинки различаются: ru {ru_images}, uk {uk_images}")
    ru_urls = [b.place.get("url") for b in ru.blocks if b.kind == "place"]
    uk_urls = [b.place.get("url") for b in uk.blocks if b.kind == "place"]
    if ru_urls != uk_urls:
        errors.append("карточки мест различаются (сайты в другом порядке или другие): "
                      f"только ru {sorted(set(ru_urls) - set(uk_urls))}, только uk {sorted(set(uk_urls) - set(ru_urls))}")
    ru_addr = [b.place.get("address") for b in ru.blocks if b.kind == "place"]
    uk_addr = [b.place.get("address") for b in uk.blocks if b.kind == "place"]
    if ru_addr != uk_addr:
        diff = [f"{a} ≠ {b}" for a, b in zip(ru_addr, uk_addr) if a != b]
        errors.append(f"адреса в карточках различаются: {'; '.join(diff[:3])}")
    ru_len, uk_len = markup.plain_length(ru.body), markup.plain_length(uk.body)
    if uk_len < ru_len * 0.85 or uk_len > ru_len * 1.2:
        errors.append(f"объём версий сильно различается: ru {ru_len}, uk {uk_len} — перевод неполный?")
    return errors


def content_files(slugs: list[str] | None = None) -> list[Path]:
    files = sorted(p for lang in LANGS for p in (CONTENT_DIR / lang).glob("*.md"))
    if slugs:
        files = [p for p in files if p.stem in slugs]
    return files

"""Гайды из файлов guides/content/<slug>.md → база.

Файл: шапка между строками «---» и текст гайда в разметке guides/markup.py.

    ---
    slug: florida-id
    title: Florida ID для тех, кто не водит
    teaser: Анонс до 300 знаков
    section: docs
    order: 2
    topics: laws
    source: FLHSMV | https://www.flhsmv.gov/... | Название страницы
    source: …
    ---
    Текст…

Импорт (import_guides) создаёт или обновляет гайд, только если файл изменился с прошлого импорта
(хеш в content_hash), поэтому правки в админке не затираются при каждом деплое.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

from . import markup
from .models import Guide

CONTENT_DIR = Path(__file__).resolve().parent / "content"
SECTIONS = dict(Guide.Section.choices)
TOPICS = {"weather", "safety", "laws", "housing", "roads", "money", "education", "health", "events", "incidents"}
MIN_CHARS, MAX_CHARS = 20_000, 30_000
INLINE_IMAGES = (2, 3)


@dataclass
class GuideFile:
    path: Path
    slug: str = ""
    title: str = ""
    teaser: str = ""
    section: str = ""
    order: int = 0
    topics: list[str] = field(default_factory=list)
    sources: list[tuple[str, str, str]] = field(default_factory=list)
    status: str = "published"
    body: str = ""
    raw: str = ""

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.raw.encode()).hexdigest()

    @property
    def cover(self) -> str:
        return f"guides/{self.slug}-1"


def parse_file(path: Path) -> GuideFile:
    raw = path.read_text(encoding="utf-8")
    guide = GuideFile(path=path, raw=raw)
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw.replace("\r\n", "\n"), re.S)
    if not match:
        raise ValueError(f"{path.name}: нет шапки между строками ---")
    header, guide.body = match.group(1), match.group(2).strip()
    for line in header.split("\n"):
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key == "source":
            parts = [p.strip() for p in value.split("|")]
            guide.sources.append((parts[0], parts[1] if len(parts) > 1 else "", parts[2] if len(parts) > 2 else ""))
        elif key == "topics":
            guide.topics = [t.strip() for t in value.split(",") if t.strip()]
        elif key == "order":
            guide.order = int(value or 0)
        elif key in {"slug", "title", "teaser", "section", "status"}:
            setattr(guide, key, value)
        else:
            raise ValueError(f"{path.name}: неизвестное поле шапки «{key}»")
    return guide


def validate(guide: GuideFile, check_images: bool = True) -> list[str]:
    """Список проблем; пустой — файл годится к публикации."""
    errors = []
    if guide.slug != guide.path.stem:
        errors.append(f"slug «{guide.slug}» не совпадает с именем файла")
    if not re.fullmatch(r"[a-z0-9-]{3,110}", guide.slug or ""):
        errors.append("slug: только латиница, цифры и дефис")
    if not guide.title or len(guide.title) > 160:
        errors.append("title: обязателен, до 160 знаков")
    if not guide.teaser or len(guide.teaser) > 300:
        errors.append(f"teaser: обязателен, до 300 знаков (сейчас {len(guide.teaser)})")
    if guide.section not in SECTIONS:
        errors.append(f"section: одно из {', '.join(SECTIONS)}")
    if unknown := set(guide.topics) - TOPICS:
        errors.append(f"topics: неизвестные {', '.join(sorted(unknown))}")
    if not guide.topics:
        errors.append("topics: хотя бы одна тема")
    if len(guide.sources) < 3:
        errors.append("source: нужно минимум 3 официальных источника")
    for name, url, _title in guide.sources:
        if not name or not url.startswith("https://"):
            errors.append(f"source «{name}»: нужно «Название | https://… | заголовок страницы»")
    if guide.status not in {"published", "draft"}:
        errors.append("status: published или draft")

    length = markup.plain_length(guide.body)
    if not MIN_CHARS <= length <= MAX_CHARS:
        errors.append(f"объём {length} знаков, нужно {MIN_CHARS}–{MAX_CHARS}")
    blocks = markup.parse(guide.body)
    if sum(b.kind == "h2" for b in blocks) < 6:
        errors.append("нужно минимум 6 разделов «## »")
    if re.search(r"^# ", guide.body, re.M):
        errors.append("заголовок «# » не нужен — заголовок гайда берётся из title")
    images = [b.number for b in blocks if b.kind == "img"]
    if sorted(images) != list(INLINE_IMAGES):
        errors.append(f"иллюстрации: нужно ровно по одной [[img:2|…]] и [[img:3|…]], сейчас {images}")
    if any(b.kind == "img" and not b.caption for b in blocks):
        errors.append("у иллюстрации нужна подпись: [[img:2|Подпись]]")
    if re.search(r"<[a-zA-Z/][^>]*>", guide.body):
        errors.append("HTML-теги в тексте не допускаются")
    if check_images:
        static = Path(settings.BASE_DIR) / "static"
        for n in (1, *INLINE_IMAGES):
            base = static / "guides" / f"{guide.slug}-{n}"
            for suffix in (".webp", "-640.webp", ".jpg"):
                if not Path(f"{base}{suffix}").exists():
                    errors.append(f"нет картинки static/guides/{guide.slug}-{n}{suffix}")
    return errors


def content_files(slugs: list[str] | None = None) -> list[Path]:
    files = sorted(p for p in CONTENT_DIR.glob("*.md") if p.name != "README.md")
    if slugs:
        files = [p for p in files if p.stem in slugs]
    return files

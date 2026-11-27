"""Текст из HTML официальной страницы и нарезка на фрагменты по разделам (только стандартная библиотека)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser

SKIP_TAGS = {"head", "script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg", "button", "select",
             "iframe", "template"}
HEADINGS = {"h1", "h2", "h3"}
BLOCKS = {"p", "li", "td", "th", "dd", "dt", "div", "section", "article", "br", "tr", "blockquote", "pre"}
CHUNK_WORDS = 350
MIN_PAGE_WORDS = 30  # меньше — страница собирается JavaScript или состоит из одних ссылок
JS_MARKERS = ("enable javascript", "javascript is required", "you need to enable javascript")


@dataclass
class Section:
    heading: str
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line for line in self.lines if line)


VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track",
             "wbr"}


class _Extractor(HTMLParser):
    """Собирает текст внутри <main> (если есть) по разделам h1–h3, пропуская меню, скрипты и формы.

    Ведёт стек открытых элементов: пропускаемый блок (меню, скрытый элемент) заканчивается ровно там, где
    закрылся его тег, даже если внутри незакрытые теги или пустые элементы вроде <img>.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._stack: list[tuple[str, bool, bool]] = []  # (тег, пропускаемый, это main)
        self._skip = 0
        self._main_depth = 0
        self.has_main = False
        self.all_sections: list[Section] = [Section("")]
        self.main_sections: list[Section] = [Section("")]
        self._heading: list[str] | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag in VOID_TAGS:
            if tag == "br":
                self._flush()
            return
        skip = tag in SKIP_TAGS or attrs.get("aria-hidden") == "true" or \
            "visually-hidden" in (attrs.get("class") or "") or "hidden" in attrs
        is_main = not skip and (tag == "main" or attrs.get("role") == "main")
        self._stack.append((tag, skip, is_main))
        if skip:
            self._skip += 1
            return
        if is_main:
            self._flush()
            self._main_depth += 1
            self.has_main = True
        if self._skip:
            return
        if tag in HEADINGS:
            self._flush()
            self._heading = []
        elif tag in BLOCKS:
            self._flush()

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in VOID_TAGS or not any(t == tag for t, _s, _m in self._stack):
            return  # лишний закрывающий тег — игнорируем
        while self._stack:
            open_tag, skip, is_main = self._stack.pop()
            if skip:
                self._skip -= 1
            if is_main:
                self._flush()
                self._main_depth -= 1
            if open_tag == tag:
                break
        if self._skip:
            return
        if tag in HEADINGS and self._heading is not None:
            heading = _clean(" ".join(self._heading))
            self._heading = None
            if heading:
                self.all_sections.append(Section(heading))
                if self._main_depth:
                    self.main_sections.append(Section(heading))
        elif tag in BLOCKS:
            self._flush()

    def handle_data(self, data):
        if self._in_title:  # <title> внутри пропускаемого <head>: берём только его
            self.title += data
            return
        if self._skip:
            return
        if self._heading is not None:
            self._heading.append(data)
        else:
            self._buf.append(data)

    def _flush(self):
        text = _clean(" ".join(self._buf))
        self._buf = []
        if not text:
            return
        self.all_sections[-1].lines.append(text)
        if self._main_depth:
            self.main_sections[-1].lines.append(text)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()


@dataclass
class Page:
    title: str
    sections: list[Section]

    @property
    def text(self) -> str:
        return "\n\n".join(f"{s.heading}\n{s.text}".strip() for s in self.sections if s.text)

    @property
    def words(self) -> int:
        return len(self.text.split())

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()

    def looks_js_only(self) -> bool:
        low = self.text.lower()
        return self.words < MIN_PAGE_WORDS or (self.words < 400 and any(m in low for m in JS_MARKERS))


def parse_html(html: str) -> Page:
    parser = _Extractor()
    parser.feed(html)
    parser.close()
    parser._flush()
    sections = parser.main_sections if parser.has_main and any(s.lines for s in parser.main_sections) \
        else parser.all_sections
    title = _clean(parser.title).split(" | ")[0]
    return Page(title=title, sections=[s for s in sections if s.lines])


def parse_markdown(text: str, title: str = "") -> Page:
    """Наши гайды: облегчённый Markdown, разделы по «## »."""
    sections = [Section("")]
    for line in text.splitlines():
        if line.startswith("#"):
            sections.append(Section(line.lstrip("#").strip()))
        elif line.strip():
            sections[-1].lines.append(re.sub(r"[*_`]", "", line.strip()))
    return Page(title=title, sections=[s for s in sections if s.lines])


# Служебные разделы: журнал правок Policy Manual, сноски, меню «связанное». В них упоминается всё подряд —
# в поиске они вытесняли бы содержательные фрагменты.
SKIP_SECTIONS = re.compile(r"^(updates|footnotes|related (links|content)|share this page|last reviewed)", re.I)


def chunks(page: Page, limit: int = CHUNK_WORDS) -> list[tuple[str, str]]:
    """[(раздел, текст)]: разделы режутся по абзацам примерно на limit слов, мелкие склеиваются с соседом."""
    out: list[tuple[str, str]] = []
    for section in page.sections:
        if SKIP_SECTIONS.match(section.heading):
            continue
        current: list[str] = []
        size = 0
        for line in section.lines:
            n = len(line.split())
            if current and size + n > limit:
                out.append((section.heading, "\n".join(current)))
                current, size = [], 0
            if n > limit * 2:  # огромный абзац (таблица пошлин) — режем по словам
                words = line.split()
                for i in range(0, len(words), limit):
                    out.append((section.heading, " ".join(words[i:i + limit])))
                continue
            current.append(line)
            size += n
        if current:
            if out and out[-1][0] == section.heading and size < 40:
                out[-1] = (section.heading, out[-1][1] + "\n" + "\n".join(current))
            else:
                out.append((section.heading, "\n".join(current)))
    return [(heading[:300], text) for heading, text in out if len(text.split()) >= 8]

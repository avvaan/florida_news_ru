"""Разметка текста гайда: облегчённый Markdown без HTML.

Блоки разделяются пустой строкой:
- «## Заголовок» — раздел (попадает в оглавление), «### Подзаголовок» — внутри раздела;
- строки, все начинающиеся с «- », — список; с «1. », «2. » … — нумерованный список;
- «> текст» — врезка («> **Важно.** …»);
- строки «| a | b |» — таблица: первая строка — шапка, вторая — «|---|---|»;
- «[[img:2|Подпись]]» — иллюстрация гайда номер 2 (1 — обложка);
- всё остальное — абзац.
Внутри текста: **жирный** и [ссылка](https://…). Весь текст экранируется, HTML не пропускается.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

from core.text import make_slug

IMG_RE = re.compile(r"^\[\[img:(?P<n>\d+)(?:\|(?P<caption>.*))?\]\]$")
BULLET_RE = re.compile(r"^[-•] ")
NUMBER_RE = re.compile(r"^\d{1,2}[.)] ")
TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
THOUSANDS_RE = re.compile(r"(?<=\d) (?=\d{3}(?!\d))")  # «$25 000» не разрывается при переносе строки


@dataclass
class Block:
    kind: str                      # h2, h3, p, ul, ol, note, table, img
    text: SafeString | str = ""    # h2/h3/p/note — готовый HTML
    items: list = field(default_factory=list)  # ul/ol — HTML пунктов; table — строки ячеек
    head: list = field(default_factory=list)   # table — HTML ячеек шапки
    anchor: str = ""               # h2 — id для оглавления
    number: int = 0                # img — номер иллюстрации
    caption: str = ""              # img — подпись (обычный текст)


def inline(text: str) -> SafeString:
    """Экранирует текст и превращает **жирный** и [ссылку](https://…) в HTML."""
    html = escape(THOUSANDS_RE.sub("\u00a0", text.strip()))
    html = LINK_RE.sub(
        lambda m: f'<a href="{m.group(2)}" target="_blank" rel="noopener nofollow">{m.group(1)}</a>', html,
    )
    html = BOLD_RE.sub(r"<strong>\1</strong>", html)
    return mark_safe(html.replace("\n", " "))


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_list(lines: list[str], pattern: re.Pattern) -> bool:
    return bool(lines) and all(pattern.match(line) for line in lines)


def parse(body: str) -> list[Block]:
    blocks: list[Block] = []
    anchors: set[str] = set()
    for chunk in body.replace("\r\n", "\n").split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = [line.strip() for line in chunk.split("\n") if line.strip()]
        first = lines[0]
        if first.startswith("## ") or first.startswith("### "):
            level = "h2" if first.startswith("## ") else "h3"
            title = first.split(" ", 1)[1].strip()
            block = Block(level, text=inline(title))
            if level == "h2":
                base = make_slug(title, max_length=60) or "razdel"
                anchor, n = base, 2
                while anchor in anchors:
                    anchor, n = f"{base}-{n}", n + 1
                anchors.add(anchor)
                block.anchor = anchor
            blocks.append(block)
            if len(lines) > 1:
                blocks.extend(parse("\n".join(lines[1:])))
        elif match := IMG_RE.match(first):
            blocks.append(Block("img", number=int(match["n"]), caption=(match["caption"] or "").strip()))
        elif _is_list(lines, BULLET_RE):
            blocks.append(Block("ul", items=[inline(BULLET_RE.sub("", line)) for line in lines]))
        elif _is_list(lines, NUMBER_RE):
            blocks.append(Block("ol", items=[inline(NUMBER_RE.sub("", line)) for line in lines]))
        elif first.startswith(">"):
            text = "\n".join(line.lstrip(">").strip() for line in lines)
            blocks.append(Block("note", text=inline(text)))
        elif first.startswith("|") and len(lines) >= 2 and TABLE_SEP_RE.match(lines[1]):
            rows = [[inline(c) for c in _cells(line)] for line in lines[2:]]
            blocks.append(Block("table", head=[inline(c) for c in _cells(first)], items=rows))
        else:
            blocks.append(Block("p", text=inline(chunk)))
    return blocks


def plain_length(body: str) -> int:
    """Длина текста в знаках с пробелами, без служебной разметки."""
    text = re.sub(r"\[\[img:[^\]]*\]\]", "", body)
    text = LINK_RE.sub(r"\1", text)
    text = text.replace("**", "")
    text = re.sub(r"^(#{2,3} |[-•] |\d{1,2}[.)] |> ?)", "", text, flags=re.M)
    text = re.sub(r"^\|?\s*:?-{2,}.*$", "", text, flags=re.M)
    text = re.sub(r"\n{2,}", "\n", text)
    return len(text.strip())

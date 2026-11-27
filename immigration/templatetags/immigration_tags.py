import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def answer_html(question) -> str:
    """Текст ответа → безопасный HTML: абзацы, списки «- », сноски [n] — ссылки на источники под ответом."""
    def cite(match):
        n = match.group(1)
        return f'<sup><a href="#q{question.pk}-s{n}" class="imm-cite">[{n}]</a></sup>'

    bullet = re.compile(r"^([-*•]|\d+[.)])\s+")
    blocks = []
    for block in re.split(r"\n\s*\n", (question.answer or "").strip()):
        items, para = [], []
        for line in (x.strip() for x in block.splitlines()):
            if not line:
                continue
            if bullet.match(line):
                if para:
                    blocks.append("<p>" + "<br>".join(para) + "</p>")
                    para = []
                items.append(f"<li>{escape(bullet.sub('', line))}</li>")
            else:
                if items:
                    blocks.append("<ul>" + "".join(items) + "</ul>")
                    items = []
                para.append(escape(line))
        if para:
            blocks.append("<p>" + "<br>".join(para) + "</p>")
        if items:
            blocks.append("<ul>" + "".join(items) + "</ul>")
    html = "".join(blocks)
    html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html)
    return mark_safe(re.sub(r"\[(\d+)\]", cite, html))

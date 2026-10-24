import uuid
from datetime import timedelta

from django import template
from django.urls import reverse
from django.utils import timezone

from comments.forms import CommentForm
from comments.models import Comment

register = template.Library()


@register.inclusion_tag("comments/block.html", takes_context=True)
def comments_block(context, target):
    """{% comments_block article %} или {% comments_block listing %}: список, свой статус и форма."""
    request = context["request"]
    kind = "listing" if target.__class__.__name__ == "Listing" else "article"
    comments = list(target.comments.published())
    mine = None
    try:
        token = uuid.UUID(request.GET.get("comment", ""))
        mine = target.comments.filter(token=token).first()
    except ValueError:
        pass
    reported = request.GET.get("reported", "")
    return {
        "request": request, "csrf_token": context.get("csrf_token"), "target": target, "kind": kind,
        "comments": comments, "rating": target.comments.rating() if kind == "listing" else None,
        "form": CommentForm(kind=kind, pk=target.pk), "mine": mine, "action": action_url(kind, target.pk),
        "reported": int(reported) if reported.isdigit() else None,
        "noun": "отзыв" if kind == "listing" else "комментарий",
        # Автообновление страницы — только первые две минуты, пока идёт проверка в фоне.
        "mine_fresh": bool(mine and timezone.now() - mine.created_at < timedelta(minutes=2)),
    }


def action_url(kind: str, pk: int) -> str:
    return reverse(f"comments:add-{kind}", args=[pk])


@register.filter
def stars(value) -> str:
    """4.6 → «★★★★★», 3 → «★★★☆☆» (округление до целой звезды)."""
    if value is None:
        return ""
    full = max(0, min(5, round(float(value))))
    return "★" * full + "☆" * (5 - full)

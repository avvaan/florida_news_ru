from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from .i18n import OTHER, UI, human_date
from .models import Destination


def _list_url(lang: str) -> str:
    return reverse("places:list" if lang == "ru" else "places:list-uk")


def destination_list(request, lang):
    regions = Destination.objects.by_region(lang)
    items = [d for region in regions for d in region["items"]]
    return render(request, "places/list.html", {
        "places_section": True, "lang": lang, "t": UI[lang], "regions": regions, "items": items,
        "list_url": _list_url(lang), "other_url": _list_url(OTHER[lang]), "other_lang": OTHER[lang],
    })


def destination_detail(request, slug, lang):
    item = get_object_or_404(Destination.objects.prefetch_related("sources"), slug=slug, lang=lang)
    if not item.is_published and not request.user.is_staff:
        raise Http404
    published = Destination.objects.published().filter(lang=lang).exclude(pk=item.pk)
    others = list(published.filter(region=item.region).order_by("order", "title")[:8])
    if len(others) < 4:
        others += list(published.exclude(pk__in=[d.pk for d in others]).order_by("region", "order")[: 6 - len(others)])
    translation = item.translation
    when = item.revised_at or item.published_at
    return render(request, "places/detail.html", {
        "places_section": True, "lang": lang, "t": UI[lang], "item": item, "others": others, "translation": translation,
        "other_lang": OTHER[lang], "is_preview": not item.is_published, "list_url": _list_url(lang),
        "updated": when, "updated_text": human_date(when, lang), "checked_text": human_date(item.checked_on, lang),
    })

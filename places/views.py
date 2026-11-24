from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from core.i18n import current_language

from .i18n import UI, human_date
from .models import Destination


def destination_list(request):
    lang = current_language()
    regions = Destination.objects.by_region(lang)
    items = [d for region in regions for d in region["items"]]
    return render(request, "places/list.html", {
        "places_section": True, "lang": lang, "t": UI[lang], "regions": regions, "items": items,
        "list_url": reverse("places:list"),
    })


def destination_detail(request, slug):
    lang = current_language()
    item = get_object_or_404(Destination.objects.prefetch_related("sources"), slug=slug, lang=lang)
    if not item.is_published and not request.user.is_staff:
        raise Http404
    published = Destination.objects.published().filter(lang=lang).exclude(pk=item.pk)
    others = list(published.filter(region=item.region).order_by("order", "title")[:8])
    if len(others) < 4:
        others += list(published.exclude(pk__in=[d.pk for d in others]).order_by("region", "order")[: 6 - len(others)])
    when = item.revised_at or item.published_at
    return render(request, "places/detail.html", {
        "places_section": True, "lang": lang, "t": UI[lang], "item": item, "others": others,
        "is_preview": not item.is_published, "list_url": reverse("places:list"),
        "updated": when, "updated_text": human_date(when, lang), "checked_text": human_date(item.checked_on, lang),
    })

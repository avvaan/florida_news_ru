from django.http import Http404
from django.shortcuts import get_object_or_404, render

from core.models import SiteSettings

from .models import Guide


def guide_list(request):
    sections = Guide.objects.by_section()
    all_guides = [g for section in sections for g in section["guides"]]
    return render(request, "guides/list.html", {"sections": sections, "all_guides": all_guides})


def guide_detail(request, slug):
    guide = get_object_or_404(Guide.objects.prefetch_related("sources", "topics"), slug=slug)
    if not guide.is_published and not request.user.is_staff:
        raise Http404
    published = Guide.objects.published().exclude(pk=guide.pk)
    others = list(published.filter(section=guide.section).order_by("order", "title")[:8]) if guide.section else []
    if len(others) < 4:
        others += list(published.exclude(pk__in=[g.pk for g in others]).order_by("order", "title")[: 6 - len(others)])
    return render(request, "guides/detail.html", {"guide": guide, "others": others,
                                                  "guide_editor": site_editor(),
                                                  "is_preview": not guide.is_published})


def site_editor():
    """Редактор по умолчанию из настроек — если он включён на сайте."""
    editor = SiteSettings.load().default_author
    return editor if editor and editor.is_active else None

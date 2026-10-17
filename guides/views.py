from django.http import Http404
from django.shortcuts import get_object_or_404, render

from .models import Guide


def guide_list(request):
    return render(request, "guides/list.html", {"guides": Guide.objects.published().order_by("title")})


def guide_detail(request, slug):
    guide = get_object_or_404(Guide.objects.prefetch_related("sources", "topics"), slug=slug)
    if not guide.is_published and not request.user.is_staff:
        raise Http404
    others = Guide.objects.published().exclude(pk=guide.pk).order_by("title")[:6]
    return render(request, "guides/detail.html", {"guide": guide, "others": others,
                                                  "is_preview": not guide.is_published})

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from .models import Page


def page(request, slug):
    obj = get_object_or_404(Page, slug=slug)
    return render(request, "core/page.html", {"page": obj})


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /admin/",
        "",
        f"Sitemap: {settings.SITE_URL}/sitemap.xml",
        f"Sitemap: {settings.SITE_URL}/news-sitemap.xml",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8")

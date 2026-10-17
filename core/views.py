from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import Author, Page


def page(request, slug):
    if slug == "about":  # одна страница — один адрес
        return redirect("core-about", permanent=True)
    obj = get_object_or_404(Page, slug=slug)
    return render(request, "core/page.html", {"page": obj})


def about(request):
    return render(request, "core/about.html", {
        "page": Page.objects.filter(slug="about").first(),
        "authors": Author.objects.filter(is_active=True),
    })


def author(request, slug):
    obj = get_object_or_404(Author, slug=slug)
    if not obj.is_active and not request.user.is_staff:
        raise Http404
    return render(request, "core/author.html", {"author": obj, "is_preview": not obj.is_active})


def dmca(request):
    return render(request, "core/dmca.html")


def corrections(request):
    return render(request, "core/corrections.html")


def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /api/",
        "",
        f"Sitemap: {settings.SITE_URL}/sitemap.xml",
        f"Sitemap: {settings.SITE_URL}/news-sitemap.xml",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8")

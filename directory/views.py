from django.shortcuts import get_object_or_404, render

from core.models import SiteSettings
from guides.models import Guide

from .models import Category, Listing


def guides_by_slug(listings) -> dict:
    slugs = {item.guide_slug for item in listings if item.guide_slug}
    return {g.slug: g for g in Guide.objects.published().filter(slug__in=slugs)} if slugs else {}


def attach_guides(listings):
    guides = guides_by_slug(listings)
    for item in listings:
        item.guide = guides.get(item.guide_slug)
    return listings


def directory_index(request):
    categories = list(Category.objects.with_listings())
    links = [c for c in categories if c.kind == Category.Kind.LINKS]
    businesses = [c for c in categories if c.kind == Category.Kind.BUSINESS]
    attach_guides([item for c in links for item in c.listings.all()])
    return render(request, "directory/index.html", {
        "link_categories": links, "business_categories": businesses, "contact_email": SiteSettings.load().contact_email,
    })


def directory_category(request, slug):
    category = get_object_or_404(Category, slug=slug)
    listings = attach_guides(list(Listing.objects.active().filter(category=category).select_related("region")))
    others = Category.objects.filter(kind=category.kind).exclude(pk=category.pk)
    return render(request, "directory/category.html", {
        "category": category, "listings": listings, "others": others,
        "contact_email": SiteSettings.load().contact_email,
    })

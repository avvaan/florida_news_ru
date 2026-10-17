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
    all_listings = list(Listing.objects.active().filter(category=category).select_related("region"))
    regions = sorted({item.region for item in all_listings if item.region}, key=lambda r: r.order)
    has_other = any(item.region is None for item in all_listings)
    current = request.GET.get("region", "")
    if current == "other":
        listings = [item for item in all_listings if item.region is None]
    elif current:
        listings = [item for item in all_listings if item.region and item.region.slug == current]
    else:
        listings = all_listings
    attach_guides(listings)
    others = Category.objects.filter(kind=category.kind).exclude(pk=category.pk)
    return render(request, "directory/category.html", {
        "category": category, "listings": listings, "others": others, "total": len(all_listings),
        "regions": regions if len(regions) + has_other > 1 else [], "has_other": has_other, "current_region": current,
        "contact_email": SiteSettings.load().contact_email,
    })

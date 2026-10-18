import hashlib
import hmac

from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

from core.models import SiteSettings
from guides.models import Guide

from . import moderation
from .forms import SubmissionForm
from .models import Category, Listing, Submission


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


def ip_hash(request) -> str:
    """Обезличенный IP для лимита заявок: сам адрес не храним."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
    return hmac.new(settings.SECRET_KEY.encode(), f"submission:{ip}".encode(), hashlib.sha256).hexdigest()[:32]


@never_cache
def submit(request):
    form = SubmissionForm(request.POST or None, initial={"category": request.GET.get("category")})
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data.get("company"):  # бот заполнил скрытое поле — делаем вид, что всё хорошо
            return render(request, "directory/submit_done.html", {"submission": None})
        key = ip_hash(request)
        if Submission.objects.since(24).filter(ip_hash=key).count() >= moderation.MAX_PER_IP_PER_DAY:
            form.add_error(None, "С этого адреса уже отправлено несколько заявок за сутки. Попробуйте завтра.")
        else:
            sub = form.save(commit=False)
            sub.ip_hash = key
            sub.save()
            moderation.start_moderation(sub)
            return redirect("directory:submission", token=sub.token)
    return render(request, "directory/submit.html", {"form": form})


@never_cache
def submission_status(request, token):
    sub = get_object_or_404(Submission.objects.select_related("listing__category"), token=token)
    return render(request, "directory/submit_done.html", {"submission": sub})

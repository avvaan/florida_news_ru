import hashlib
import hmac
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.db.models import Avg, Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from core import geo
from core.models import SiteSettings
from guides.models import Guide

from . import moderation
from .forms import ListingUpdateForm, SubmissionForm
from .models import Category, Listing, ListingUpdate, Submission
from .specialties import Specialty


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


def attach_ratings(listings):
    """Средняя оценка и число опубликованных отзывов — для карточек в списке."""
    from comments.models import Comment

    rows = (Comment.objects.filter(listing__in=listings, status=Comment.Status.APPROVED, rating__isnull=False)
            .values("listing").annotate(avg=Avg("rating"), n=Count("pk")))
    by_id = {row["listing"]: row for row in rows}
    for item in listings:
        row = by_id.get(item.pk)
        item.rating_avg, item.rating_count = (round(row["avg"], 1), row["n"]) if row else (None, 0)


def sort_by_distance(listings, hub: str):
    """Ближе к главному городу — выше; без адреса и города (онлайн, «по всей Флориде») — в конце, как были."""
    origin = geo.hub_point(hub)
    for item in listings:
        item.point = geo.locate_place(item.address, item.city)
        item.distance = geo.distance_text(item.point, hub)
    return sorted(listings, key=lambda item: geo.miles(item.point, origin) if item.point else float("inf"))


def specialty_filter(listings, current: str):
    """Кнопки «Терапевты · 31», «Детские врачи · 8»… — по уже выбранному региону, без пустых.

    Показываются, если направлений хотя бы два (у врачей); у остальных категорий направлений нет.
    """
    counts = Counter(item.specialty for item in listings if item.specialty)
    current = current if current in Specialty.values else ""
    buttons = [{"value": value, "label": label, "count": counts[value]}
               for value, label in Specialty.choices if counts[value] or value == current]
    return (buttons if len(buttons) > 1 or current else []), current


# Страница «категория + регион» (/links/stomatologi/miami/) открыта для поиска, если в ней не меньше стольких мест;
# реже — noindex: тонкие страницы тянут сайт вниз.
MIN_REGION_PAGE = 3


def region_pages(category, listings) -> list:
    """Регионы, у которых есть своя индексируемая страница в категории (для sitemap и ссылок)."""
    counts = Counter(item.region for item in listings if item.region and not item.region.is_statewide)
    return sorted((r for r, n in counts.items() if n >= MIN_REGION_PAGE), key=lambda r: r.order)


def directory_category(request, slug, region=None):
    category = get_object_or_404(Category, slug=slug)
    all_listings = list(Listing.objects.active().filter(category=category).select_related("region"))
    regions = sorted({item.region for item in all_listings if item.region}, key=lambda r: r.order)
    has_other = any(item.region is None for item in all_listings)
    region_page = None
    if region:  # /links/<категория>/<регион>/ — своя страница под запрос «русский стоматолог в Майами»
        region_page = next((r for r in regions if r.slug == region and not r.is_statewide), None)
        if region_page is None or category.kind != Category.Kind.BUSINESS:
            raise Http404
    elif request.GET.get("region") in {r.slug for r in region_pages(category, all_listings)} and len(request.GET) == 1:
        # старые ссылки ?region=miami ведут на постоянный адрес региона
        return redirect("directory:category-region", slug=slug, region=request.GET["region"], permanent=True)
    current = region_page.slug if region_page else request.GET.get("region", "")
    if current == "other":
        listings = [item for item in all_listings if item.region is None]
    elif current:
        listings = [item for item in all_listings if item.region and item.region.slug == current]
    else:
        listings = all_listings
    specialties, current_spec = specialty_filter(listings, request.GET.get("spec", ""))
    if current_spec:
        listings = [item for item in listings if item.specialty == current_spec]
    near = request.GET.get("near", "")
    if near in geo.HUBS and category.kind == Category.Kind.BUSINESS:
        listings = sort_by_distance(listings, near)
    else:
        near = ""
    attach_guides(listings)
    attach_ratings(listings)
    others = Category.objects.filter(kind=category.kind).exclude(pk=category.pk)
    if region_page:  # соседние категории в том же регионе — только те, где есть страница региона
        counts = Counter(Listing.objects.active().filter(category__kind=Category.Kind.BUSINESS, region=region_page)
                         .exclude(category=category).values_list("category_id", flat=True))
        others = [c for c in others if counts[c.pk] >= MIN_REGION_PAGE]
    with_page = {r.slug for r in region_pages(category, all_listings)}
    return render(request, "directory/category.html", {
        "region_page": region_page, "region_slugs_with_page": with_page,
        "region_indexable": bool(region_page and len(listings) >= MIN_REGION_PAGE),
        "category": category, "listings": listings, "others": others, "total": len(all_listings),
        "regions": regions if len(regions) + has_other > 1 else [], "has_other": has_other, "current_region": current,
        "specialties": specialties, "current_spec": current_spec,
        "near": near,
        "near_links": geo.near_links(request, "near") if category.kind == Category.Kind.BUSINESS and len(all_listings) > 1
        else [],
        "contact_email": SiteSettings.load().contact_email,
    })


def listing_detail(request, slug, pk, item_slug):
    """Страница бизнеса: карточка, отзывы с оценками и форма отзыва."""
    item = get_object_or_404(Listing.objects.select_related("category", "region"), pk=pk, is_active=True,
                             category__kind=Category.Kind.BUSINESS)
    if request.path != item.get_absolute_url():
        return redirect(item.get_absolute_url(), permanent=True)
    attach_guides([item])
    others = (Listing.objects.active().filter(category=item.category).exclude(pk=item.pk)
              .select_related("region")[:20])
    nearby = sorted(others, key=lambda other: other.region_id != item.region_id)[:4]  # сначала из того же региона
    return render(request, "directory/listing.html", {"item": item, "category": item.category, "nearby": nearby})


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
            form.add_error(None, _("С этого адреса уже отправлено несколько заявок за сутки. Попробуйте завтра."))
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


MAX_UPDATES_PER_IP_PER_DAY = 5


@never_cache
def listing_update(request, slug, pk, item_slug):
    """«Это ваш бизнес?»: владелец предлагает правку, редактор применяет её в админке. Плюс значок для сайта."""
    item = get_object_or_404(Listing.objects.select_related("category"), pk=pk, is_active=True,
                             category__kind=Category.Kind.BUSINESS)
    initial = {name: getattr(item, name) for name in ListingUpdate.FIELDS}
    form = ListingUpdateForm(request.POST or None, initial=initial)
    sent = False
    if request.method == "POST" and form.is_valid():
        if not form.cleaned_data.get("company"):  # ловушка для ботов: им молча «спасибо»
            key = ip_hash(request)
            recent = ListingUpdate.objects.filter(ip_hash=key, created_at__gte=timezone.now() - timedelta(hours=24))
            if recent.count() >= MAX_UPDATES_PER_IP_PER_DAY:
                form.add_error(None, _("С этого адреса уже отправлено несколько правок за сутки. Попробуйте завтра."))
                return render(request, "directory/update.html", {"item": item, "category": item.category, "form": form})
            update = form.save(commit=False)
            update.listing, update.ip_hash = item, key
            update.save()
        sent = True
    page_url = request.build_absolute_uri(item.get_absolute_url())
    return render(request, "directory/update.html", {
        "item": item, "category": item.category, "form": form, "sent": sent, "page_url": page_url,
    })

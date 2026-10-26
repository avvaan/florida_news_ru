import math

from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Case, Count, ExpressionWrapper, F, FloatField, IntegerField, Max, Prefetch, Value, When
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from core import geo
from directory.views import ip_hash
from news.models import Region

from . import moderation
from .forms import AdForm, FilterForm, ReportForm
from .models import MAX_PHOTOS, Ad, Category, Photo

PER_PAGE = 24
CONTACTS_PER_HOUR = 40  # с одного адреса — дальше похоже на сбор телефонов
EDITS_PER_DAY = 10  # каждая правка — новая проверка ИИ


def _photos():
    return Prefetch("photos", queryset=Photo.objects.filter(status=Photo.Status.PUBLISHED).exclude(url=""))


def _filtered(request, ads):
    """Применяет фильтры из адресной строки. Возвращает (объявления, форма, есть ли фильтры)."""
    form = FilterForm(request.GET)
    form.is_valid()
    data = form.cleaned_data
    if q := data.get("q", "").strip():
        for word in q.lower().replace("ё", "е").split()[:6]:
            ads = ads.filter(search__contains=word)
    region = data.get("region")
    if region == "other":
        ads = ads.filter(region=None)
    elif region:
        ads = ads.filter(region__slug=region)
    if data.get("price_min") is not None:
        ads = ads.filter(price__gte=data["price_min"])
    if data.get("price_max") is not None:
        ads = ads.filter(price__lte=data["price_max"])
    if data.get("photo"):
        ads = ads.filter(photos__status=Photo.Status.PUBLISHED).distinct()
    sort = data.get("sort") or ""
    order = {"cheap": [F("price").asc(nulls_last=True)], "expensive": [F("price").desc(nulls_last=True)]}.get(sort, [])
    if hub := hub_from_sort(sort):
        ads = ads.annotate(dist=_squared_distance(hub))
        order = [F("dist").asc(nulls_last=True)]  # объявления из неизвестных городов — в конце
    if zip_code := data.get("zip"):
        # Сначала тот же ZIP, потом соседние (те же первые три цифры), потом остальные.
        ads = ads.annotate(near=Case(
            When(zip_code=zip_code, then=Value(0)), When(zip_code__startswith=zip_code[:3], then=Value(1)),
            default=Value(2), output_field=IntegerField(),
        ))
        order = [F("near").asc(), *order]
    ads = ads.order_by(*order, "-published_at", "-pk")
    active = any(data.get(k) for k in ("q", "region", "zip", "photo", "sort")) or \
        data.get("price_min") is not None or data.get("price_max") is not None
    return ads, form, active


def hub_from_sort(sort: str) -> str:
    hub = sort.removeprefix("near-")
    return hub if sort.startswith("near-") and hub in geo.HUBS else ""


def _squared_distance(hub: str):
    """Квадрат расстояния до главного города в «градусах широты»: для сортировки хватает плоской проекции."""
    lat, lon = geo.hub_point(hub)
    k = math.cos(math.radians(lat))
    dlat = F("lat") - Value(lat)
    dlon = (F("lon") - Value(lon)) * Value(k)
    return ExpressionWrapper(dlat * dlat + dlon * dlon, output_field=FloatField())


def _with_distance(request, page):
    """Подпись «≈ 12 миль от Майами» на карточках, когда список отсортирован по расстоянию."""
    if hub := hub_from_sort(request.GET.get("sort", "")):
        for ad in page.object_list:
            ad.distance = geo.distance_text(ad.point, hub)
    return page


def _regions():
    return Region.objects.filter(is_statewide=False).order_by("order")


def _page(request, ads):
    return _with_distance(request, Paginator(ads.select_related("category", "region").prefetch_related(_photos()),
                                             PER_PAGE).get_page(request.GET.get("page")))


def index(request):
    counts = dict(Ad.objects.active().values_list("category").annotate(n=Count("pk")).values_list("category", "n"))
    sections = list(Category.objects.filter(parent=None).prefetch_related("children"))
    for section in sections:
        for child in section.children.all():
            child.count = counts.get(child.pk, 0)
        section.count = sum(c.count for c in section.children.all())
    ads, form, filtered = _filtered(request, Ad.objects.active())
    page = _page(request, ads)
    return render(request, "classifieds/list.html", {
        "sections": sections, "page_obj": page, "form": form, "filtered": filtered,
        "total": sum(s.count for s in sections), "regions": _regions(),
        "near_links": geo.near_links(request, "sort", "near-"),
    })


def category(request, slug):
    cat = get_object_or_404(Category.objects.select_related("parent"), slug=slug)
    section = cat if cat.is_section else cat.parent
    children = list(section.children.all())
    counts = dict(Ad.objects.active().filter(category__in=children).values_list("category")
                  .annotate(n=Count("pk")).values_list("category", "n"))
    for child in children:
        child.count = counts.get(child.pk, 0)
    base = Ad.objects.active().filter(category__in=children if cat.is_section else [cat])
    ads, form, filtered = _filtered(request, base)
    page = _page(request, ads)
    return render(request, "classifieds/list.html", {
        "category": cat, "section": section, "children": children, "page_obj": page, "form": form,
        "filtered": filtered, "total": sum(counts.values()) if cat.is_section else counts.get(cat.pk, 0),
        "regions": _regions(), "near_links": geo.near_links(request, "sort", "near-"),
    })


def _detail_context(ad: Ad, **extra):
    similar = (Ad.objects.active().filter(category=ad.category).exclude(pk=ad.pk)
               .select_related("category", "region").prefetch_related(_photos()))
    if ad.region_id:
        similar = similar.annotate(same=Case(When(region_id=ad.region_id, then=Value(0)), default=Value(1),
                                             output_field=IntegerField())).order_by("same", "-published_at")
    else:
        similar = similar.order_by("-published_at")
    return {"ad": ad, "photos": ad.public_photos(), "similar": similar[:4],
            "report_form": ReportForm(), **extra}


def _public_ad(pk):
    ad = get_object_or_404(Ad.objects.select_related("category__parent", "region").prefetch_related("photos"), pk=pk)
    if not ad.is_public:
        raise Http404
    return ad


def detail(request, pk, slug):
    ad = _public_ad(pk)
    if slug != ad.slug:
        return redirect(ad, permanent=True)
    if ad.is_active:
        Ad.objects.filter(pk=ad.pk).update(views=F("views") + 1)
    return render(request, "classifieds/detail.html", _detail_context(ad))


@require_POST
def contacts(request, pk):
    """«Показать контакты»: POST с CSRF, чтобы телефоны не собирали простые боты."""
    ad = _public_ad(pk)
    if not ad.is_active:
        return redirect(ad)
    key = f"ad-contacts:{ip_hash(request)}"
    shown = cache.get(key, 0)
    if shown >= CONTACTS_PER_HOUR:
        return render(request, "classifieds/detail.html", _detail_context(ad, contacts_limited=True), status=429)
    cache.set(key, shown + 1, 3600)
    Ad.objects.filter(pk=ad.pk).update(contact_views=F("contact_views") + 1)
    return render(request, "classifieds/detail.html", _detail_context(ad, show_contacts=True))


@require_POST
def report(request, pk):
    ad = _public_ad(pk)
    form = ReportForm(request.POST)
    if not form.is_valid():
        return render(request, "classifieds/detail.html", _detail_context(ad, report_form=form, report_open=True),
                      status=400)
    moderation.report(ad, form.cleaned_data["reason"], form.cleaned_data["comment"], ip_hash(request))
    return render(request, "classifieds/detail.html", _detail_context(ad, reported=True))


def _save_photos(ad: Ad, photo_bytes: list[bytes]) -> None:
    last = ad.photos.aggregate(last=Max("order"))["last"]
    start = 0 if last is None else last + 1
    Photo.objects.bulk_create([Photo(ad=ad, order=start + n, data=data) for n, data in enumerate(photo_bytes)])


@never_cache
def submit(request):
    initial = {}
    if slug := request.GET.get("category"):
        initial["category"] = Category.objects.exclude(parent=None).filter(slug=slug).first()
    form = AdForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data.get("company"):  # бот заполнил скрытое поле — делаем вид, что всё хорошо
            return render(request, "classifieds/manage.html", {"ad": None})
        key = ip_hash(request)
        if Ad.objects.since(24).filter(ip_hash=key).count() >= moderation.MAX_PER_IP_PER_DAY:
            form.add_error(None, "С этого адреса уже подано несколько объявлений за сутки. Попробуйте завтра.")
        else:
            ad = form.save(commit=False)
            ad.ip_hash = key
            ad.save()
            _save_photos(ad, form.photo_bytes)
            moderation.start_moderation(ad)
            return redirect("classifieds:manage", token=ad.token)
    return render(request, "classifieds/submit.html", {"form": form, "max_photos": MAX_PHOTOS})


def _own_ad(token):
    return get_object_or_404(Ad.objects.select_related("category__parent", "region"), token=token)


@never_cache
def manage(request, token):
    ad = _own_ad(token)
    return render(request, "classifieds/manage.html", {"ad": ad, "photos": list(ad.photos.all())})


@never_cache
def edit(request, token):
    ad = _own_ad(token)
    if ad.status in (Ad.Status.CLOSED, Ad.Status.HIDDEN):
        return redirect(ad.get_manage_url())
    kept = [p for p in ad.photos.all() if p.status in (Photo.Status.PUBLISHED, Photo.Status.PENDING,
                                                        Photo.Status.CHECKED)]
    remove_ids = {int(x) for x in request.POST.getlist("remove_photo") if x.isdigit()} if request.method == "POST" else set()
    form = AdForm(request.POST or None, request.FILES or None, instance=ad,
                  existing_photos=len([p for p in kept if p.pk not in remove_ids]))
    edits_key = f"ad-edits:{ad.pk}"
    if request.method == "POST" and cache.get(edits_key, 0) >= EDITS_PER_DAY:
        form.add_error(None, "Сегодня объявление уже правили много раз. Попробуйте завтра.")
    elif request.method == "POST" and form.is_valid():
        cache.set(edits_key, cache.get(edits_key, 0) + 1, 24 * 3600)
        ad = form.save(commit=False)
        ad.status = Ad.Status.PENDING  # правку снова проверяет ИИ, пока она не одобрена — объявление скрыто
        ad.attempts = 0
        ad.save()
        moderation.delete_photos(ad, ad.photos.filter(pk__in=remove_ids))
        moderation.delete_photos(ad, ad.photos.filter(status__in=[Photo.Status.REJECTED, Photo.Status.SKIPPED]))
        _save_photos(ad, form.photo_bytes)
        moderation.start_moderation(ad)
        return redirect(ad.get_manage_url())
    return render(request, "classifieds/submit.html", {"form": form, "ad": ad, "photos": kept,
                                                       "max_photos": MAX_PHOTOS})


@require_POST
def renew(request, token):
    ad = _own_ad(token)
    if ad.can_renew:
        ad.renew()
        ad.save(update_fields=["published_at", "expires_at"])
    return redirect(ad.get_manage_url())


@require_POST
def close(request, token):
    ad = _own_ad(token)
    if ad.status in (Ad.Status.APPROVED, Ad.Status.PENDING, Ad.Status.REJECTED):
        ad.status = Ad.Status.CLOSED
        ad.closed_at = timezone.now()
        ad.save(update_fields=["status", "closed_at"])
    return redirect(ad.get_manage_url())

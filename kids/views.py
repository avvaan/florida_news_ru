import hashlib
import hmac
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache

from core.i18n import is_uk, only_language

from . import filters, seo
from .forms import ClubSubmitForm, FilterForm, ReportForm
from .models import Category, City, Club, ClubReport

MAX_SUBMISSIONS_PER_IP_PER_DAY = 5
MAX_REPORTS_PER_IP_PER_DAY = 10


def ip_hash(request, purpose: str) -> str:
    """Обезличенный IP для лимитов: сам адрес не храним."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
    return hmac.new(settings.SECRET_KEY.encode(), f"{purpose}:{ip}".encode(), hashlib.sha256).hexdigest()[:32]


def map_points(clubs) -> list[dict]:
    """Точки для карты: только очные занятия; без своих координат — центр города, с пометкой «примерно»."""
    points = []
    for club in clubs:
        if club.has_offline and (point := club.point):
            points.append({"lat": round(point[0], 5), "lng": round(point[1], 5), "name": club.name,
                           "url": club.get_absolute_url(), "exact": club.point_is_exact,
                           "city": club.city.loc("name") if club.city_id else ""})
    return points


def nav_links(f, published) -> dict:
    """Чипы «направления» и «города» с числом кружков в текущем срезе. Ссылки на тонкие страницы — nofollow."""
    by_cat = Counter(c.category for c in published if not f.city or c.city_id == f.city.pk)
    by_city = Counter(c.city_id for c in published if c.city_id and (not f.category or c.category == f.category))
    categories = [{"slug": value, "label": label, "count": by_cat[value],
                   "url": seo.list_url(value, f.city), "current": value == f.category,
                   "indexable": by_cat[value] >= filters.MIN_INDEXABLE}
                  for value, label in Category.choices if by_cat[value] or value == f.category]
    cities = [{"slug": city.slug, "label": city.loc("name"), "count": by_city[city.pk],
               "url": seo.list_url(f.category, city), "current": f.city is not None and city.pk == f.city.pk,
               "indexable": by_city[city.pk] >= filters.MIN_INDEXABLE}
              for city in City.objects.active() if by_city[city.pk] or (f.city and city.pk == f.city.pk)]
    return {"categories": categories, "cities": cities}


@dataclass(frozen=True)
class Section:
    """Страница списка для sitemap: направление и/или город."""

    category: str = ""
    city: City | None = None

    def get_absolute_url(self):
        return seo.list_url(self.category, self.city)


def indexable_sections() -> list[Section]:
    """Списки, открытые для поиска: в каждом не меньше MIN_INDEXABLE опубликованных кружков."""
    clubs = list(Club.objects.published().select_related("city"))
    counts = Counter()
    for club in clubs:
        counts[("", None)] += 1
        counts[(club.category, None)] += 1
        if club.city_id:
            counts[("", club.city)] += 1
            counts[(club.category, club.city)] += 1
    pages = [Section(cat, city) for (cat, city), n in counts.items() if n >= filters.MIN_INDEXABLE]
    return sorted(pages, key=lambda p: (p.category, p.city.order if p.city else -1))


def club_list(request, first=None, second=None):
    f = filters.resolve_path(first, second)
    if f is None:
        raise Http404
    # Форма фильтров отправляется на /deti/?cat=…&city=… — переводим на постоянный адрес раздела.
    if first is None and (request.GET.get("cat") or request.GET.get("city")):
        cat = request.GET.get("cat", "")
        city = City.objects.active().filter(slug=request.GET.get("city", "")).first()
        target = seo.list_url(cat if cat in Category.values else "", city)
        extra = filters.parse_extra(request.GET).extra
        if target != request.path or extra != dict(request.GET.items()):
            return redirect(target + (f"?{urlencode(extra)}" if extra else ""), permanent=not extra)
    f = filters.parse_extra(request.GET, f)
    clubs = list(filters.find(f))
    published = list(Club.objects.published().only("category", "city_id"))
    indexable = filters.is_indexable(len(clubs), f) and not request.GET.get("page")
    initial = {"cat": f.category, "city": f.city.slug if f.city else "", **f.extra}
    crumbs = seo.breadcrumbs(f)
    context = {
        "f": f, "clubs": clubs, "total": len(published), "indexable": indexable,
        "title": seo.title(f, clubs), "h1": seo.h1(f), "description": seo.description(f, len(clubs)),
        "crumbs": crumbs[:-1] if not f.is_empty else crumbs[:1],
        "breadcrumbs_ld": seo.dumps(seo.breadcrumbs_jsonld(crumbs)),
        "itemlist_ld": seo.dumps(seo.itemlist_jsonld(seo.h1(f), clubs)) if clubs else "",
        "filter_form": FilterForm(initial=initial), "nav": nav_links(f, published),
        "points": map_points(clubs), "reset_url": seo.list_url(f.category, f.city) if f.has_extra else "",
        "esa_page": seo.ESA_PAGE_VERIFIED or request.user.is_staff,
    }
    return render(request, "kids/list.html", context)


def club_detail(request, slug):
    club = get_object_or_404(Club.objects.select_related("city").prefetch_related("photos__media"), slug=slug)
    if club.status == Club.Status.DRAFT and not request.user.is_staff:
        raise Http404
    others = (Club.objects.published().filter(category=club.category).exclude(pk=club.pk)
              .select_related("city").ordered())
    nearby = sorted(others[:30], key=lambda o: o.city_id != club.city_id)[:4]
    f = filters.Filters(category=club.category, city=club.city)
    crumbs = seo.breadcrumbs(f) + [(club.name, club.get_absolute_url())]
    return render(request, "kids/detail.html", {
        "club": club, "nearby": nearby, "crumbs": crumbs[:-1],
        "breadcrumbs_ld": seo.dumps(seo.breadcrumbs_jsonld(crumbs)),
        "club_ld": seo.dumps(seo.club_jsonld(club)),
        "report_form": ReportForm(), "report_sent": request.GET.get("report") == "sent",
        "photos": club.public_photos(), "esa_page": seo.ESA_PAGE_VERIFIED or request.user.is_staff,
        "category_url": seo.list_url(club.category), "is_preview": club.status == Club.Status.DRAFT,
    })


@never_cache
def report(request, slug):
    club = get_object_or_404(Club.objects.select_related("city"), slug=slug, status=Club.Status.PUBLISHED)
    if request.method != "POST":
        return redirect(club.get_absolute_url() + "#report")
    form = ReportForm(request.POST)
    if form.is_valid():
        if not form.cleaned_data.get("company"):  # ловушка для ботов: им молча «спасибо»
            key = ip_hash(request, "kids-report")
            recent = ClubReport.objects.filter(ip_hash=key, created_at__gte=timezone.now() - timedelta(hours=24))
            if recent.count() < MAX_REPORTS_PER_IP_PER_DAY:
                obj = form.save(commit=False)
                obj.club, obj.ip_hash = club, key
                obj.save()
        return redirect(club.get_absolute_url() + "?report=sent#report")
    return render(request, "kids/report.html", {"club": club, "form": form})


@never_cache
def submit(request):
    form = ClubSubmitForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data.get("company"):
            return redirect("kids:submit-done")
        key = ip_hash(request, "kids-submit")
        recent = Club.objects.filter(ip_hash=key, created_at__gte=timezone.now() - timedelta(hours=24))
        if recent.count() >= MAX_SUBMISSIONS_PER_IP_PER_DAY:
            form.add_error(None, _("С этого адреса уже отправлено несколько заявок за сутки. Попробуйте завтра."))
        else:
            club = form.save(commit=False)
            club.ip_hash = key
            club.save()
            return redirect("kids:submit-done")
    return render(request, "kids/submit.html", {"form": form})


def submit_done(request):
    return render(request, "kids/submit_done.html")


def esa_page(request):
    """Только по-русски: на /uk/ страницы нет (переключатель ведёт в каталог, hreflang на uk не объявляем)."""
    if (not seo.ESA_PAGE_VERIFIED and not request.user.is_staff) or is_uk():
        raise Http404
    only_language(request, "ru", "kids:list")
    crumbs = [(_("Главная"), reverse("news:home")), (_("Детям"), reverse("kids:list")),
              (_("Оплата из стипендии"), reverse("kids:esa"))]
    return render(request, "kids/esa.html", {
        "verified": seo.ESA_PAGE_VERIFIED, "crumbs": crumbs[:-1],
        "breadcrumbs_ld": seo.dumps(seo.breadcrumbs_jsonld(crumbs)),
    })


esa_page.page_language = lambda **kwargs: "ru"  # украиноязычных читателей не перенаправлять на /uk/

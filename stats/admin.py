from datetime import timedelta

from django.contrib import admin
from django.db.models import Sum
from django.urls import Resolver404, resolve
from django.utils import timezone

from .models import DailyStat, PageView, Source

PERIODS = (7, 30, 90, 365)


def page_title(path: str) -> str:
    """Человеческое название страницы по адресу: заголовок заметки или гайда, название региона или темы."""
    from guides.models import Guide
    from news.models import Article, Region, Tag, Topic

    try:
        match = resolve(path)
    except Resolver404:
        return path
    slug = match.kwargs.get("slug")
    lookups = {
        "news:article": (Article, "title"), "guides:detail": (Guide, "title"),
        "news:region": (Region, "name"), "news:topic": (Topic, "name"), "news:tag": (Tag, "name"),
    }
    if match.view_name in lookups and slug:
        model, field = lookups[match.view_name]
        title = model.objects.filter(slug=slug).values_list(field, flat=True).first()
        prefix = {"news:region": "Регион: ", "news:topic": "Тема: ", "news:tag": "Тег: "}.get(match.view_name, "")
        return f"{prefix}{title}" if title else path
    return {"news:home": "Главная", "guides:list": "Все гайды", "core-about": "О проекте"}.get(match.view_name, path)


def build_dashboard(days: int) -> dict:
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    stats = {s.date: s for s in DailyStat.objects.filter(date__gte=start)}
    series = []
    for n in range(days):
        day = start + timedelta(days=n)
        s = stats.get(day)
        series.append({"date": day, "views": s.views if s else 0, "visitors": s.visitors if s else 0})
    peak = max([d["views"] for d in series] + [1])
    for d in series:
        d["views_pct"] = round(d["views"] / peak * 100, 1)
        d["visitors_pct"] = round(d["visitors"] / peak * 100, 1)

    period = DailyStat.objects.filter(date__gte=start).aggregate(
        views=Sum("views"), visitors=Sum("visitors"), mobile=Sum("mobile"), tablet=Sum("tablet"), desktop=Sum("desktop"),
    )
    period = {k: v or 0 for k, v in period.items()}
    devices_total = period["mobile"] + period["tablet"] + period["desktop"] or 1
    devices = [
        {"label": label, "count": period[key], "pct": round(period[key] / devices_total * 100)}
        for key, label in (("mobile", "Телефон"), ("desktop", "Компьютер"), ("tablet", "Планшет"))
    ]
    pages = (PageView.objects.filter(date__gte=start).values("path")
             .annotate(total=Sum("views")).order_by("-total")[:25])
    sources = (Source.objects.filter(date__gte=start).values("source")
               .annotate(total=Sum("visits")).order_by("-total")[:15])
    sources_total = sum(s["total"] for s in sources) or 1

    def day_card(day):
        s = stats.get(day) or DailyStat.objects.filter(date=day).first()
        return {"views": s.views if s else 0, "visitors": s.visitors if s else 0}

    return {
        "days": days,
        "periods": PERIODS,
        "today": day_card(today),
        "yesterday": day_card(today - timedelta(days=1)),
        "period": period,
        "avg_visitors": round(period["visitors"] / days),
        "series": series,
        "peak": peak,
        "show_dates": days <= 31,
        "devices": devices,
        "pages": [{**p, "title": page_title(p["path"])} for p in pages],
        "sources": [{**s, "pct": round(s["total"] / sources_total * 100)} for s in sources],
    }


@admin.register(DailyStat)
class DailyStatAdmin(admin.ModelAdmin):
    change_list_template = "admin/stats/dailystat_change_list.html"
    list_display = ("date", "visitors", "views", "mobile", "desktop", "tablet")
    list_display_links = None
    date_hierarchy = "date"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        try:
            days = int(request.GET.get("days", 30))
        except ValueError:
            days = 30
        days = days if days in PERIODS else 30
        if "days" in request.GET:  # не фильтр модели — убираем, иначе админка ответит ошибкой
            query = request.GET.copy()
            del query["days"]
            request.GET = query
        extra_context = {**(extra_context or {}), **build_dashboard(days)}
        return super().changelist_view(request, extra_context=extra_context)

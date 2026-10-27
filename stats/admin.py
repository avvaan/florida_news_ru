from collections import Counter
from datetime import timedelta

from django.contrib import admin
from django.db.models import Count, Q
from django.urls import Resolver404, resolve
from django.utils import timezone

from .models import DailyStat, Hit, PageView, Source
from .tracking import canonical_host, source_name

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


def first_day(raw: bool):
    """С какого дня есть данные: сигналы из браузера, а в режиме «с ботами» — и старый счётчик."""
    days = [Hit.objects.order_by("date").values_list("date", flat=True).first()]
    if raw:
        days.append(DailyStat.objects.order_by("date").values_list("date", flat=True).first())
    return min((d for d in days if d), default=None)


def average_per_day(total: int, start, today, since) -> int:
    """Среднее за день: делим на дни, когда счётчик уже работал, а не на всю длину периода."""
    if since is None:
        return 0
    days = (today - max(start, since)).days + 1
    return round(total / days) if days > 0 else 0


def build_dashboard(days: int, raw: bool = False) -> dict:
    """Люди — по сигналам из браузера без ботов. raw=True: плюс боты и старый серверный счётчик."""
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    hits = Hit.objects.filter(date__gte=start)
    counted = hits if raw else hits.filter(is_bot=False)
    per_day = {r["date"]: r for r in counted.values("date").annotate(views=Count("id"),
                                                                     visitors=Count("visitor", distinct=True))}
    bots_per_day = dict(hits.filter(is_bot=True).values("date").annotate(n=Count("id")).values_list("date", "n"))
    humans_per_day = dict(hits.filter(is_bot=False).values("date").annotate(n=Count("id")).values_list("date", "n"))
    legacy = {s.date: s for s in DailyStat.objects.filter(date__gte=start)}

    series = []
    for n in range(days):
        day = start + timedelta(days=n)
        row, old = per_day.get(day, {}), legacy.get(day)
        series.append({
            "date": day, "views": row.get("views", 0), "visitors": row.get("visitors", 0),
            "bots": bots_per_day.get(day, 0),
            "legacy_views": old.views if old else 0, "legacy_visitors": old.visitors if old else 0,
        })
    peak = max([d["views"] + d["legacy_views"] for d in series] + [1])
    for d in series:
        d["views_pct"] = round(d["views"] / peak * 100, 1)
        d["visitors_pct"] = round(d["visitors"] / peak * 100, 1)
        d["legacy_pct"] = round(d["legacy_views"] / peak * 100, 1)

    def day_card(day):
        d = next((d for d in series if d["date"] == day), None)
        if d is None:
            return {"views": 0, "visitors": 0}
        extra = (d["legacy_views"], d["legacy_visitors"]) if raw else (0, 0)
        return {"views": d["views"] + extra[0], "visitors": d["visitors"] + extra[1]}

    views = sum(d["views"] + (d["legacy_views"] if raw else 0) for d in series)
    visitors = sum(d["visitors"] + (d["legacy_visitors"] if raw else 0) for d in series)
    bots_today = bots_per_day.get(today, 0)
    seen_today = bots_today + humans_per_day.get(today, 0)
    js_since = first_day(raw=False)

    return {
        "days": days,
        "periods": PERIODS,
        "raw": raw,
        "today": day_card(today),
        "yesterday": day_card(today - timedelta(days=1)),
        "period": {"views": views, "visitors": visitors},
        "avg_visitors": average_per_day(visitors, start, today, first_day(raw)),
        "views_per_visitor": round(views / visitors, 1) if visitors else 0,
        "bots_today": bots_today,
        "bots_today_pct": round(bots_today / seen_today * 100) if seen_today else 0,
        "js_since": js_since,
        "legacy_in_period": sum(d["legacy_views"] for d in series),
        "series": series,
        "table": list(reversed(series)),
        "peak": peak,
        "show_dates": days <= 31,
        "devices": devices(counted, legacy.values() if raw else ()),
        "pages": pages(counted, start, raw),
        "sources": sources(counted, start, raw),
        "bots": list(hits.filter(is_bot=True).values("agent", "bot_reason").annotate(total=Count("id"))
                     .order_by("-total")[:15]),
    }


def devices(hits, legacy_days) -> list[dict]:
    """Устройство — у посетителя за день (не у каждого просмотра)."""
    seen = {}
    for day, visitor, kind in hits.values_list("date", "visitor", "device"):
        seen.setdefault((day, visitor), kind)
    counts = Counter(seen.values())
    for s in legacy_days:
        counts.update({"mobile": s.mobile, "tablet": s.tablet, "desktop": s.desktop})
    total = sum(counts.values()) or 1
    return [{"label": label, "count": counts[key], "pct": round(counts[key] / total * 100)}
            for key, label in (("mobile", "Телефон"), ("desktop", "Компьютер"), ("tablet", "Планшет"))]


def pages(hits, start, raw: bool) -> list[dict]:
    counts = Counter(dict(hits.values("path").annotate(n=Count("id")).values_list("path", "n")))
    if raw:
        for path, n in PageView.objects.filter(date__gte=start).values_list("path", "views"):
            counts[path] += n
    return [{"path": path, "total": n, "title": page_title(path)} for path, n in counts.most_common(25)]


def sources(hits, start, raw: bool) -> list[dict]:
    """Входы на сайт по источникам; метки utm — внутри своего источника («из них по меткам»)."""
    rows = (hits.exclude(source="").values("source")
            .annotate(n=Count("id"), utm=Count("id", filter=~Q(utm_source=""))))
    counts = Counter({r["source"]: r["n"] for r in rows})
    tagged = {r["source"]: r["utm"] for r in rows}
    if raw:  # старые записи: IP-адреса Cloudflare и т.п. — это не сайты, а прямые заходы
        for label, n in Source.objects.filter(date__gte=start).values_list("source", "visits"):
            counts[label if label == Source.DIRECT else canonical_host(label)] += n
    total = sum(counts.values()) or 1
    return [{"source": source_name(s), "total": n, "utm": tagged.get(s, 0), "pct": round(n / total * 100)}
            for s, n in counts.most_common(15)]


@admin.register(DailyStat)
class DailyStatAdmin(admin.ModelAdmin):
    change_list_template = "admin/stats/dailystat_change_list.html"
    list_display = ("date", "visitors", "views", "mobile", "desktop", "tablet")
    list_display_links = None

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
        raw = request.GET.get("bots") == "1"
        if "days" in request.GET or "bots" in request.GET:  # не фильтры модели — иначе админка ответит ошибкой
            query = request.GET.copy()
            query.pop("days", None)
            query.pop("bots", None)
            request.GET = query
        extra_context = {**(extra_context or {}), **build_dashboard(days, raw)}
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(Hit)
class HitAdmin(admin.ModelAdmin):
    """Сырые просмотры — проверить, кого счётчик посчитал ботом и почему."""

    list_display = ("created_at", "path", "source", "device", "is_bot", "bot_reason", "agent")
    list_filter = ("is_bot", "bot_reason", "device", "source", "date")
    search_fields = ("path", "agent", "utm_source", "utm_campaign")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

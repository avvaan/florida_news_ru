import json
import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone

from guides.models import Guide
from news.models import Article, Region

from .models import Program

DATA = Path(__file__).parent / "data"

HURRICANE_GUIDES = ["podgotovka-k-uraganu", "zony-evakuacii", "generator-bez-ugarnogo-gaza", "posle-uragana",
                    "strahovka-doma-i-navodneniya", "zhara-molnii-techeniya-alligatory"]
IMMIGRATION_GUIDES = ["grin-karta", "grazhdanstvo-ssha", "ssn-i-itin", "prava-vo-floride-dlya-priezzhih",
                      "florida-id", "perevod-notarius-apostil", "besplatnyj-anglijskij"]
# Заметки об иммиграции: по словам в заголовке и анонсе (своей рубрики у иммиграции нет).
IMMIGRATION_WORDS = ["иммигра", "мигрант", "USCIS", "TPS", "грин-карт", "гражданств", "депорт", "виз", "parole",
                     "убежищ", "ICE", "U4U", "натурализац", "беженц"]


@lru_cache(maxsize=1)
def hurricane_resources() -> dict:
    """Официальные ссылки штата и округов (hubs/data/hurricane.json). Файл правится вручную и при деплое."""
    path = DATA / "hurricane.json"
    if not path.exists():
        return {"statewide": {}, "counties": []}
    return json.loads(path.read_text(encoding="utf-8"))


def season(today: date | None = None) -> dict:
    """Сезон ураганов в Атлантике: 1 июня — 30 ноября."""
    today = today or timezone.localdate()
    start, end = date(today.year, 6, 1), date(today.year, 11, 30)
    if start <= today <= end:
        return {"active": True, "ends": end, "days_left": (end - today).days}
    next_start = start if today < start else date(today.year + 1, 6, 1)
    return {"active": False, "starts": next_start, "days_to": (next_start - today).days}


def guides_in_order(slugs):
    found = {g.slug: g for g in Guide.objects.published().filter(slug__in=slugs)}
    return [found[s] for s in slugs if s in found]


def hurricanes(request):
    from news.views import active_alerts
    from sources.models import FeedItem

    data = hurricane_resources()
    regions = {r.slug: r for r in Region.objects.filter(is_statewide=False)}
    groups = []
    for slug, region in regions.items():
        counties = [c for c in data.get("counties", []) if c.get("region") == slug]
        if counties:
            groups.append({"region": region, "counties": counties})
    others = [c for c in data.get("counties", []) if c.get("region") not in regions]
    if others:
        groups.append({"region": None, "counties": others})
    nhc = (FeedItem.objects.filter(source__url__icontains="nhc.noaa.gov",
                                   fetched_at__gte=timezone.now() - timedelta(days=7))
           .order_by("-published_at", "-fetched_at")[:8])
    nhc = list(nhc)
    for item in nhc:  # описание из фида NHC приходит с HTML — показываем короткий текст
        item.short = strip_tags_short(item.summary)
    news = Article.objects.published().filter(topic__slug="weather").order_by("-published_at")[:6]
    return render(request, "hubs/hurricanes.html", {
        "alerts": active_alerts(), "nhc": nhc, "news": list(news), "season": season(),
        "statewide": data.get("statewide", {}), "groups": groups,
        "guides": guides_in_order(HURRICANE_GUIDES),
    })


def immigration_news(limit=10):
    since = timezone.now() - timedelta(days=180)
    words = Q()
    for word in IMMIGRATION_WORDS:
        words |= Q(title__icontains=word) | Q(teaser__icontains=word)
    return list(Article.objects.published().filter(published_at__gte=since).filter(words)
                .order_by("-published_at")[:limit])


def immigration(request):
    from directory.models import Listing

    programs = list(Program.objects.published())
    guides = {g.slug: g for g in Guide.objects.published().filter(slug__in=[p.guide_slug for p in programs])}
    for program in programs:
        program.guide = guides.get(program.guide_slug)
    checked = max((p.checked_on for p in programs), default=None)
    lawyers = Listing.objects.active().filter(category__slug="yuristy").filter(
        Q(name__icontains="иммиграц") | Q(description__icontains="иммиграц")).count()
    return render(request, "hubs/immigration.html", {
        "programs": programs, "checked": checked, "news": immigration_news(),
        "guides": guides_in_order(IMMIGRATION_GUIDES), "lawyers": lawyers,
    })


def strip_tags_short(text: str, n: int = 220) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"

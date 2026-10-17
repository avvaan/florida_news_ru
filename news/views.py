from datetime import timedelta

from django.contrib.syndication.views import Feed
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from ads.models import AdBanner
from sources.models import WeatherAlert

from .models import Article, Region, Tag, Topic

PER_PAGE = 16


def published():
    return Article.objects.published().select_related("region", "topic")


def active_alerts():
    alerts = WeatherAlert.objects.filter(is_active=True, is_hidden=False).filter(
        Q(expires__isnull=True) | Q(expires__gte=timezone.now())
    )
    order = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3, "Unknown": 4}
    return sorted(alerts, key=lambda a: (order.get(a.severity, 5), a.expires or timezone.now()))


def ads_for(region=None) -> dict:
    return {
        slot: AdBanner.objects.running(slot, region).first()
        for slot in (AdBanner.Slot.TOP, AdBanner.Slot.SIDEBAR, AdBanner.Slot.INFEED)
    }


def urgent_strip():
    since = timezone.now() - timedelta(hours=24)
    return published().filter(is_urgent=True, published_at__gte=since)[:4]


def _filtered(region=None, topic=None):
    qs = published()
    if region and not region.is_statewide:
        qs = qs.for_region(region)
    elif region:
        qs = qs.filter(region=region)
    if topic:
        qs = qs.filter(topic=topic)
    return qs


def front(request, region=None, topic=None, template="news/front.html", extra=None):
    """Главная и страницы регионов/тем: одна и та же лента с фильтрами."""
    region = region or Region.objects.filter(slug=request.GET.get("region")).first()
    topic = topic or Topic.objects.filter(slug=request.GET.get("topic")).first()
    qs = _filtered(region, topic)

    page_number = request.GET.get("page") or 1
    paginator = Paginator(qs, PER_PAGE)
    page = paginator.get_page(page_number)
    first_page = page.number == 1

    lead, top, feed = None, [], list(page.object_list)
    if first_page and feed:
        # Главная тема: свежее срочное за 12 часов, иначе самое важное за сутки, иначе последнее.
        recent = [a for a in feed if a.published_at >= timezone.now() - timedelta(hours=24)]
        urgent = [a for a in recent if a.is_urgent and a.published_at >= timezone.now() - timedelta(hours=12)]
        lead = (urgent or sorted(recent, key=lambda a: -(a.score or 0)) or feed)[0]
        feed.remove(lead)
        top = feed[:3]
        feed = feed[3:]

    since = timezone.now() - timedelta(hours=24)
    shown = [a.pk for a in ([lead] if lead else []) + top]
    most_important = list(
        qs.filter(published_at__gte=since).exclude(pk__in=shown).order_by("-score", "-published_at")[:5]
    )

    context = {
        "region": region,
        "topic": topic,
        "lead": lead,
        "top": top,
        "feed": feed,
        "page_obj": page,
        "most_important": most_important,
        "alerts": active_alerts(),
        "urgent": urgent_strip(),
        "ads": ads_for(region),
        "is_home": region is None and topic is None and first_page,
        **(extra or {}),
    }
    return render(request, template, context)


def region_view(request, slug):
    region = get_object_or_404(Region, slug=slug)
    return front(request, region=region)


def topic_view(request, slug):
    topic = get_object_or_404(Topic, slug=slug)
    return front(request, topic=topic)


def tag_view(request, slug):
    tag = get_object_or_404(Tag, slug=slug)
    qs = published().filter(tags=tag)
    page = Paginator(qs, PER_PAGE).get_page(request.GET.get("page") or 1)
    return render(request, "news/tag.html", {
        "tag": tag, "feed": page.object_list, "page_obj": page, "ads": ads_for(),
    })


def article_view(request, slug):
    article = get_object_or_404(
        Article.objects.select_related("region", "topic").prefetch_related("tags", "sources"), slug=slug
    )
    is_preview = article.status != Article.Status.PUBLISHED
    if is_preview and not request.user.is_staff:
        raise Http404
    others = published().exclude(pk=article.pk)
    related = list(
        others.filter(Q(topic_id=article.topic_id) | Q(region_id=article.region_id)).order_by("-published_at")[:4]
    )
    if len(related) < 4:  # добираем свежими, чтобы колонка не пустовала
        related += list(others.exclude(pk__in=[a.pk for a in related])[: 4 - len(related)])
    return render(request, "news/article.html", {
        "article": article,
        "related": related,
        "ads": ads_for(article.region),
        "is_preview": is_preview,
        "urgent": urgent_strip(),
    })


class LatestFeed(Feed):
    title = "Флорида Сегодня — новости штата по-русски"
    link = "/"
    description = "Короткие новости Флориды на русском со ссылками на первоисточники"

    def items(self):
        return published()[:30]

    def item_title(self, item):
        return ("🚨 " if item.is_urgent else "") + item.title

    def item_description(self, item):
        return item.teaser

    def item_pubdate(self, item):
        return item.published_at

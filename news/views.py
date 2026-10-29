from datetime import timedelta

from django.conf import settings
from django.contrib.syndication.views import Feed
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from ads.models import AdBanner
from guides.models import Guide
from sources.models import WeatherAlert

from .models import BUSINESS, HIDDEN_IN_NAV, Article, Region, Tag, Topic

PER_PAGE = 20


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
    """Плашка «Срочно»: только пока не истёк срок (expires_at — окончание предупреждения NWS или +6 часов)."""
    now = timezone.now()
    return published().filter(is_urgent=True).filter(
        Q(expires_at__gt=now) | Q(expires_at__isnull=True, published_at__gte=now - timedelta(hours=6))
    )[:4]


def _filtered(region=None, topic=None):
    qs = published()
    if topic is None:
        qs = qs.exclude(topic__slug=BUSINESS)  # у бизнеса своя страница /business/
    if region and not region.is_statewide:
        qs = qs.for_region(region)
    elif region:
        qs = qs.filter(region=region)
    if topic:
        qs = qs.filter(topic__slug__in=topic.page_slugs)  # «ЧП» вместе с «Происшествиями»
    return qs


def front(request, region=None, topic=None, template="news/front.html", extra=None):
    """Главная и страницы регионов/тем: одна и та же лента с фильтрами."""
    region = region or Region.objects.filter(slug=request.GET.get("region")).first()
    topic = topic or Topic.objects.exclude(slug__in=HIDDEN_IN_NAV).filter(slug=request.GET.get("topic")).first()
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
    if first_page and lead:  # дайджест стоит рядом с главной темой — в ленте те же заметки не повторяем
        digest = {a.pk for a in most_important}
        feed = [a for a in feed if a.pk not in digest]

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
        "guides": Guide.objects.featured(),
        "business_latest": list(published().filter(topic__slug=BUSINESS)[:4]) if region is None and topic is None else [],
        "guide_sections": Guide.objects.by_section() if region is None and topic is None and first_page else [],
        **(extra or {}),
    }
    return render(request, template, context)


def region_view(request, slug):
    region = get_object_or_404(Region, slug=slug)
    return front(request, region=region)


def topic_view(request, slug):
    topic = get_object_or_404(Topic, slug=slug)
    if slug == BUSINESS or slug in HIDDEN_IN_NAV:  # одна страница — один адрес: влитые темы ведут в общий раздел
        return redirect(topic.get_absolute_url(), permanent=True)
    return front(request, topic=topic)


BUSINESS_KINDS = {"stocks": "Акции", "deals": "Сделки"}


def business_view(request, kind=None):
    """Раздел «Бизнес: акции и сделки»: обзор с блоками и общая лента; /business/stocks/ и /deals/ — фильтры."""
    if kind is not None and kind not in BUSINESS_KINDS:
        raise Http404
    topic = get_object_or_404(Topic, slug=BUSINESS)
    qs = published().filter(topic__slug__in=topic.page_slugs)  # бизнес вместе с «Деньгами и ценами»
    if kind:
        qs = qs.filter(business_kind=kind)
    page = Paginator(qs, PER_PAGE).get_page(request.GET.get("page") or 1)
    overview = kind is None and page.number == 1
    stocks = list(qs.filter(business_kind="stocks")[:4]) if overview else []
    deals = list(qs.filter(business_kind="deals")[:4]) if overview else []
    shown = {a.pk for a in stocks + deals}
    return render(request, "news/business.html", {
        "topic": topic,
        "kind": kind,
        "kind_name": BUSINESS_KINDS.get(kind, ""),
        "kinds": BUSINESS_KINDS,
        "stocks": stocks,
        "deals": deals,
        "feed": [a for a in page.object_list if a.pk not in shown],  # без повторов блоков
        "page_obj": page,
        "ads": ads_for(),
        "urgent": urgent_strip(),
    })


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
    if article.merged_into_id and article.status == Article.Status.MERGED:
        return redirect(article.merged_into.get_absolute_url(), permanent=True)  # дубль → основная заметка
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
    title = "Florida RU — новости штата по-русски"
    description = "Короткие новости Флориды на русском со ссылками на первоисточники"

    # Ссылки только на канонический домен (SITE_URL), а не на хост, с которого пришёл запрос.
    def link(self):
        return f"{settings.SITE_URL}/"

    def feed_url(self):
        return f"{settings.SITE_URL}{reverse('news:rss')}"

    def item_link(self, item):
        return f"{settings.SITE_URL}{item.get_absolute_url()}"

    def items(self):
        return published()[:30]

    def item_title(self, item):
        return ("🚨 " if item.urgent_now else "") + item.title

    def item_description(self, item):
        return item.teaser

    def item_pubdate(self, item):
        return item.published_at

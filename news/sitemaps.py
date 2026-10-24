from datetime import timedelta

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone

from core.models import Author, Page
from directory.models import Category
from classifieds.models import Ad
from classifieds.models import Category as AdCategory
from events.models import Event
from guides.models import Guide

from .models import HIDDEN_IN_NAV, Article, Region, Topic


class SiteRootSitemap(Sitemap):
    """Sitemap без django.contrib.sites: домен берём из SITE_URL."""

    protocol = "https"

    def get_domain(self, site=None):
        return settings.SITE_URL.split("://", 1)[-1]

    def get_protocol(self, protocol=None):
        return settings.SITE_URL.split("://", 1)[0]

    def images(self, item) -> list[dict]:
        """Картинки страницы для расширения image: sitemap — [{"loc", "title"}]."""
        return []

    def get_urls(self, page=1, site=None, protocol=None):
        urls = super().get_urls(page=page, site=site, protocol=protocol)
        for url in urls:
            url["images"] = self.images(url["item"])
        return urls


def static_url(path: str) -> str:
    return f"{settings.SITE_URL}{static(path)}"


class ArticleSitemap(SiteRootSitemap):
    changefreq = "daily"
    priority = 0.8
    limit = 5000

    def items(self):
        return Article.objects.published().order_by("-published_at")

    def lastmod(self, obj):
        return obj.revised_at or obj.published_at

    def images(self, item):
        return [{"loc": static_url(f"{item.cover}.jpg"), "title": item.title}]


class SectionSitemap(SiteRootSitemap):
    changefreq = "hourly"
    priority = 0.6

    def items(self):
        return ["home", *Region.objects.all(), *Topic.objects.exclude(slug__in=HIDDEN_IN_NAV), "stocks", "deals"]

    def location(self, item):
        if item == "home":
            return reverse("news:home")
        if item in ("stocks", "deals"):
            return reverse("news:business-kind", args=[item])
        return item.get_absolute_url()

    def lastmod(self, item):
        if item == "home":
            latest = Article.objects.published().order_by("-published_at").first()
            return latest.published_at if latest else None
        return None


class PageSitemap(SiteRootSitemap):
    changefreq = "monthly"
    priority = 0.3

    def items(self):
        return Page.objects.exclude(slug="about")  # /p/about/ отдаёт 301 на /about/ — она в LegalSitemap


class LegalSitemap(SiteRootSitemap):
    changefreq = "monthly"
    priority = 0.3

    def items(self):
        return ["guides:list", "core-about", "core-dmca", "core-corrections"]

    def location(self, item):
        return reverse(item)


class GuideSitemap(SiteRootSitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Guide.objects.published().order_by("title")

    def lastmod(self, obj):
        return obj.revised_at or obj.published_at

    def location(self, obj):
        return obj.get_absolute_url()

    def images(self, item):
        return [{"loc": static_url(f"{path}.jpg"), "title": item.title} for path in item.image_paths]


class DirectorySitemap(SiteRootSitemap):
    changefreq = "weekly"
    priority = 0.5

    def items(self):
        # пустые категории закрыты noindex — в sitemap только те, где есть записи
        return ["index", *Category.objects.filter(listings__is_active=True).distinct().order_by("kind", "order")]

    def location(self, item):
        return reverse("directory:index") if item == "index" else item.get_absolute_url()


class EventSitemap(SiteRootSitemap):
    changefreq = "daily"
    priority = 0.6

    def items(self):
        # прошедшие события закрыты noindex — в sitemap только ближайшие
        return ["list", *Event.objects.upcoming()]

    def location(self, item):
        return reverse("events:list") if item == "list" else item.get_absolute_url()

    def lastmod(self, item):
        return None if item == "list" else item.moderated_at

    def images(self, item) -> list[dict]:
        if item == "list" or not item.image_url:
            return []
        return [{"loc": item.image_url, "title": item.title}]


class ClassifiedSitemap(SiteRootSitemap):
    changefreq = "daily"
    priority = 0.5

    def items(self):
        # рубрики без объявлений и истёкшие объявления закрыты noindex — в sitemap их нет
        active = Ad.objects.active()
        used = set(active.values_list("category_id", flat=True))
        used |= set(AdCategory.objects.filter(pk__in=used).values_list("parent_id", flat=True))
        cats = AdCategory.objects.filter(pk__in=used).order_by("parent_id", "order")
        return ["index", *cats, *active.newest().prefetch_related("photos")]

    def location(self, item):
        return reverse("classifieds:index") if item == "index" else item.get_absolute_url()

    def lastmod(self, item):
        return item.moderated_at if isinstance(item, Ad) else None

    def images(self, item) -> list[dict]:
        if not isinstance(item, Ad):
            return []
        return [{"loc": p.url, "title": item.title} for p in item.public_photos()]


class AuthorSitemap(SiteRootSitemap):
    changefreq = "monthly"
    priority = 0.3

    def items(self):
        return Author.objects.filter(is_active=True)


def google_news_items():
    """Google News sitemap: только заметки за последние 48 часов."""
    since = timezone.now() - timedelta(hours=48)
    return Article.objects.published().filter(published_at__gte=since).order_by("-published_at")[:1000]


SITEMAPS = {"sections": SectionSitemap, "articles": ArticleSitemap, "guides": GuideSitemap, "pages": PageSitemap,
            "authors": AuthorSitemap, "legal": LegalSitemap,
            "directory": DirectorySitemap, "events": EventSitemap,
            "classifieds": ClassifiedSitemap}

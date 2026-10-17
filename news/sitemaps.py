from datetime import timedelta

from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.utils import timezone

from core.models import Author, Page
from guides.models import Guide

from .models import Article, Region, Topic


class SiteRootSitemap(Sitemap):
    """Sitemap без django.contrib.sites: домен берём из SITE_URL."""

    protocol = "https"

    def get_domain(self, site=None):
        from django.conf import settings
        return settings.SITE_URL.split("://", 1)[-1]

    def get_protocol(self, protocol=None):
        from django.conf import settings
        return settings.SITE_URL.split("://", 1)[0]


class ArticleSitemap(SiteRootSitemap):
    changefreq = "daily"
    priority = 0.8
    limit = 5000

    def items(self):
        return Article.objects.published().order_by("-published_at")

    def lastmod(self, obj):
        return obj.revised_at or obj.published_at


class SectionSitemap(SiteRootSitemap):
    changefreq = "hourly"
    priority = 0.6

    def items(self):
        return ["home", *Region.objects.all(), *Topic.objects.all()]

    def location(self, item):
        return reverse("news:home") if item == "home" else item.get_absolute_url()


class PageSitemap(SiteRootSitemap):
    changefreq = "monthly"
    priority = 0.3

    def items(self):
        return Page.objects.all()


class LegalSitemap(SiteRootSitemap):
    changefreq = "monthly"
    priority = 0.3

    def items(self):
        return ["guides:list", "core-dmca", "core-corrections"]

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
            "authors": AuthorSitemap, "legal": LegalSitemap}

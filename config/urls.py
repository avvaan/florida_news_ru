from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.shortcuts import render
from django.urls import include, path, re_path
from django.views.static import serve
from django.views.decorators.cache import cache_page

from core import views as core_views
from news.sitemaps import SITEMAPS, google_news_items


def news_sitemap(request):
    return render(
        request, "news/news_sitemap.xml", {"articles": google_news_items()},
        content_type="application/xml; charset=utf-8",
    )


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
    path("sitemap.xml", cache_page(600)(sitemap), {"sitemaps": SITEMAPS},
         name="django.contrib.sitemaps.views.sitemap"),
    path("news-sitemap.xml", cache_page(300)(news_sitemap), name="news_sitemap"),
    path("robots.txt", core_views.robots_txt),
    path("p/<slug:slug>/", core_views.page, name="core-page"),
    path("about/", core_views.about, name="core-about"),
    path("author/<slug:slug>/", core_views.author, name="core-author"),
    path("guides/", include("guides.urls")),
    path("dmca/", core_views.dmca, name="core-dmca"),
    path("corrections/", core_views.corrections, name="core-corrections"),
    path("", include("news.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.SERVE_MEDIA:
    # Картинки рекламы на небольшом сайте без CDN: Django отдаёт их сам.
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]

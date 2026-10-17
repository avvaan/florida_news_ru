from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("articles", views.ArticleViewSet, basename="article")
router.register("sources", views.SourceViewSet)
router.register("alerts", views.WeatherAlertViewSet)
router.register("ads", views.AdBannerViewSet)
router.register("pages", views.PageViewSet)
router.register("regions", views.RegionViewSet)
router.register("topics", views.TopicViewSet)
router.register("pipeline", views.PipelineViewSet)

urlpatterns = [
    path("v1/settings/", views.SettingsView.as_view(), name="api-settings"),
    path("v1/stats/", views.StatsView.as_view(), name="api-stats"),
    path("v1/covers/", views.CoversView.as_view(), name="api-covers"),
    path("v1/", include(router.urls)),
    path("schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
]

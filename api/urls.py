from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from . import content_views as cv
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
router.register("media", cv.MediaViewSet, basename="media")
router.register("events", cv.EventViewSet, basename="event")
router.register("directory/categories", cv.DirectoryCategoryViewSet, basename="directory-category")
router.register("directory/listings", cv.ListingViewSet, basename="listing")
router.register("directory/submissions", cv.SubmissionViewSet, basename="submission")
router.register("guides", cv.GuideViewSet, basename="guide")
router.register("classifieds/categories", cv.AdCategoryViewSet, basename="ad-category")
router.register("classifieds/ads", cv.AdViewSet, basename="classified")
router.register("comments", cv.CommentViewSet, basename="comment")
router.register("tags", cv.TagViewSet, basename="tag")
router.register("authors", cv.AuthorViewSet, basename="author")
router.register("signal-sources", cv.SignalSourceViewSet, basename="signal-source")
router.register("hints", cv.HintViewSet, basename="hint")

urlpatterns = [
    path("v1/settings/", views.SettingsView.as_view(), name="api-settings"),
    path("v1/stats/", views.StatsView.as_view(), name="api-stats"),
    path("v1/covers/", views.CoversView.as_view(), name="api-covers"),
    path("v1/", include(router.urls)),
    path("schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
]

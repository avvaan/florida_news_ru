from django.urls import path

from . import views

app_name = "news"

urlpatterns = [
    path("", views.front, name="home"),
    path("news/<slug:slug>/", views.article_view, name="article"),
    path("region/<slug:slug>/", views.region_view, name="region"),
    path("topic/<slug:slug>/", views.topic_view, name="topic"),
    path("tag/<slug:slug>/", views.tag_view, name="tag"),
    path("rss/", views.LatestFeed(), name="rss"),
]

from django.urls import path

from . import views

app_name = "comments"

urlpatterns = [
    path("report/<int:pk>/", views.report, name="report"),
    path("article/<int:pk>/", views.add, {"kind": "article"}, name="add-article"),
    path("listing/<int:pk>/", views.add, {"kind": "listing"}, name="add-listing"),
]

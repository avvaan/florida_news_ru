from django.urls import path

from . import views

app_name = "directory"

urlpatterns = [
    path("", views.directory_index, name="index"),
    path("add/", views.submit, name="submit"),
    path("add/<uuid:token>/", views.submission_status, name="submission"),
    path("<slug:slug>/", views.directory_category, name="category"),
    path("<slug:slug>/<int:pk>-<slug:item_slug>/", views.listing_detail, name="listing"),
]

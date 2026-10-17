from django.urls import path

from . import views

app_name = "directory"

urlpatterns = [
    path("", views.directory_index, name="index"),
    path("<slug:slug>/", views.directory_category, name="category"),
]

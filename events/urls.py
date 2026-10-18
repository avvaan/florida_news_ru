from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("", views.event_list, name="list"),
    path("add/", views.submit, name="submit"),
    path("add/<uuid:token>/", views.submission_status, name="submission"),
    path("<slug:slug>/", views.event_detail, name="detail"),
]

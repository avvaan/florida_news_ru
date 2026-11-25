from django.urls import path

from . import views

app_name = "places"

# Внутри i18n_patterns: /chto-posetit/… — русская версия, /uk/chto-posetit/… — украинская.
urlpatterns = [
    path("", views.destination_list, name="list"),
    path("<slug:slug>/", views.destination_detail, name="detail"),
]

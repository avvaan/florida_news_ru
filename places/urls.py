from django.urls import path

from . import views

app_name = "places"

urlpatterns = [
    path("chto-posetit/", views.destination_list, {"lang": "ru"}, name="list"),
    path("chto-posetit/<slug:slug>/", views.destination_detail, {"lang": "ru"}, name="detail"),
    path("uk/shcho-vidvidaty/", views.destination_list, {"lang": "uk"}, name="list-uk"),
    path("uk/shcho-vidvidaty/<slug:slug>/", views.destination_detail, {"lang": "uk"}, name="detail-uk"),
]

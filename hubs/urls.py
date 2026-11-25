from django.urls import path

from . import views

app_name = "hubs"

urlpatterns = [
    path("uragany/", views.hurricanes, name="hurricanes"),
    path("immigraciya/", views.immigration, name="immigration"),
]

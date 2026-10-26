from django.urls import path

from . import views

app_name = "classifieds"

urlpatterns = [
    path("", views.index, name="index"),
    path("add/", views.submit, name="submit"),
    path("my/<uuid:token>/", views.manage, name="manage"),
    path("my/<uuid:token>/edit/", views.edit, name="edit"),
    path("my/<uuid:token>/renew/", views.renew, name="renew"),
    path("my/<uuid:token>/close/", views.close, name="close"),
    # объявление — до рубрики: «123-divan» тоже подходит под slug
    path("<int:pk>-<slug:slug>/", views.detail, name="detail"),
    path("<int:pk>/contacts/", views.contacts, name="contacts"),
    path("<int:pk>/report/", views.report, name="report"),
    path("<slug:slug>/", views.category, name="category"),
]

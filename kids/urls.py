from django.urls import path

from . import views

app_name = "kids"

# Служебные адреса (kruzhok, dobavit, stipendii-pep-fes) идут раньше общих <направление>/<город>;
# город с таким адресом создать нельзя (models.RESERVED_SLUGS).
urlpatterns = [
    path("", views.club_list, name="list"),
    path("dobavit/", views.submit, name="submit"),
    path("dobavit/spasibo/", views.submit_done, name="submit-done"),
    path("stipendii-pep-fes/", views.esa_page, name="esa"),
    path("kruzhok/<slug:slug>/", views.club_detail, name="club"),
    path("kruzhok/<slug:slug>/oshibka/", views.report, name="report"),
    path("<slug:first>/", views.club_list, name="section"),
    path("<slug:first>/<slug:second>/", views.club_list, name="section-city"),
]

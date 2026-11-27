from django.urls import path

from . import views

app_name = "immigration"

urlpatterns = [
    path("", views.page, name="page"),
    path("vhod/", views.login_start, name="login"),
    path("vhod/kod/", views.login_code, name="login-code"),
    path("vyhod/", views.logout_view, name="logout"),
    path("region/", views.set_region, name="region"),
    path("otvet/<int:pk>/ocenka/", views.feedback, name="feedback"),
    path("istoriya/udalit/", views.delete_history, name="delete-history"),
    path("akkaunt/udalit/", views.delete_account, name="delete-account"),
]

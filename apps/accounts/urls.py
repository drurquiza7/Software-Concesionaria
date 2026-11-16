from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("ingresar/", views.login_view, name="login"),
    path("salir/", views.logout_view, name="logout"),
    path("concesionarias/", views.seleccionar_concesionaria, name="seleccionar_concesionaria"),
]

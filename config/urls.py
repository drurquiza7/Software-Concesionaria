from django.urls import include, path
from django.views.generic import RedirectView

from apps.accounts.decorators import vista_publica

from . import views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path(
        "",
        vista_publica(RedirectView.as_view(pattern_name="accounts:seleccionar_concesionaria")),
        name="inicio",
    ),
    path("", include("apps.accounts.urls")),
]

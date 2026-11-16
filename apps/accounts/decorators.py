from collections.abc import Callable
from functools import wraps
from typing import Any

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect

from apps.core.exceptions import NoEncontrado

from . import selectors

Vista = Callable[..., HttpResponse]

URL_SELECTOR = "accounts:seleccionar_concesionaria"


def vista_publica(vista: Vista) -> Vista:
    """Marca explícita de vista sin sesión (login, healthz, webhooks)."""

    @wraps(vista)
    def envoltura(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        return vista(request, *args, **kwargs)

    envoltura.es_publica = True
    return envoltura


def requiere_sesion(vista: Vista) -> Vista:
    """Vista para un usuario autenticado que todavía no eligió concesionaria."""

    @wraps(vista)
    def envoltura(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        return vista(request, *args, **kwargs)

    envoltura.requiere_sesion = True
    return envoltura


def requiere_permiso(codigo: str) -> Callable[[Vista], Vista]:
    """Exige sesión, concesionaria activa y el permiso atómico indicado (SRS RF-01 y RF-02)."""

    def decorador(vista: Vista) -> Vista:
        @wraps(vista)
        def envoltura(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.membresia is None:
                return redirect(URL_SELECTOR)
            if not selectors.tiene_permiso(request.membresia, codigo):
                raise PermissionDenied
            try:
                return vista(request, *args, **kwargs)
            except NoEncontrado as error:
                # Otro tenant o fuera de alcance: 404, nunca 403 (SRS RF-03).
                raise Http404 from error

        envoltura.permiso_requerido = codigo
        return envoltura

    return decorador

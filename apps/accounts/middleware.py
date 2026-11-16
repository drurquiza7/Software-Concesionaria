import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.core.context import tenant_context

from . import selectors
from .session import SESSION_TENANT_KEY, desactivar_concesionaria


def _tenant_de_la_sesion(request: HttpRequest) -> uuid.UUID | None:
    valor = request.session.get(SESSION_TENANT_KEY)
    if not valor:
        return None
    try:
        return uuid.UUID(str(valor))
    except ValueError:
        return None


class TenantMiddleware:
    """Único punto del panel que fija el tenant activo (CLAUDE.md 4.3, SRS RF-02).

    Lee el tenant de la sesión y lo acepta solo si el usuario tiene una membresía activa
    en una concesionaria activa (RN-01). Si no, la request sigue sin tenant.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.tenant = None
        request.membresia = None
        if not request.user.is_authenticated:
            return self.get_response(request)
        tenant_id = _tenant_de_la_sesion(request)
        if tenant_id is None:
            desactivar_concesionaria(request)
            return self.get_response(request)
        with tenant_context(tenant_id):
            membresia = selectors.obtener_membresia_activa(request.user)
            if membresia is not None and membresia.tenant.esta_activo:
                request.tenant = membresia.tenant
                request.membresia = membresia
                return self.get_response(request)
        desactivar_concesionaria(request)
        return self.get_response(request)

from django.http import HttpRequest

from .models import Membresia

SESSION_TENANT_KEY = "tenant_id"


def activar_concesionaria(request: HttpRequest, membresia: Membresia) -> None:
    """Guarda en la sesión el tenant elegido. La membresía ya fue validada contra el usuario."""
    request.session[SESSION_TENANT_KEY] = str(membresia.tenant_id)


def desactivar_concesionaria(request: HttpRequest) -> None:
    request.session.pop(SESSION_TENANT_KEY, None)

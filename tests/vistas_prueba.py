"""Vistas mínimas para probar el aislamiento por HTTP.

Las pantallas reales del panel llegan en otra fase; estas vistas usan el mismo decorador,
los mismos selectores y los mismos servicios que usarán aquellas.
"""

import uuid

from django.core.paginator import Paginator
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_POST

from apps.accounts import selectors as accounts_selectors
from apps.accounts import services as accounts_services
from apps.accounts.decorators import requiere_permiso
from apps.core.exceptions import ErrorDeDominio, NoEncontrado
from apps.tenants import selectors as tenants_selectors
from apps.tenants import services as tenants_services


def _error(error: ErrorDeDominio) -> JsonResponse:
    return JsonResponse({"error": error.mensaje}, status=400)


@requiere_permiso("sucursal.gestionar")
def sucursales(request: HttpRequest) -> JsonResponse:
    pagina = Paginator(tenants_selectors.listar_sucursales(), 25).get_page(request.GET.get("p"))
    return JsonResponse({"resultados": [str(sucursal.pk) for sucursal in pagina]})


@requiere_permiso("sucursal.gestionar")
def sucursal_detalle(request: HttpRequest, sucursal_id: uuid.UUID) -> JsonResponse:
    sucursal = tenants_selectors.obtener_sucursal(sucursal_id)
    return JsonResponse({"id": str(sucursal.pk), "nombre": sucursal.nombre})


@requiere_permiso("sucursal.gestionar")
@require_POST
def sucursal_editar(request: HttpRequest, sucursal_id: uuid.UUID) -> JsonResponse:
    try:
        sucursal = tenants_services.actualizar_sucursal(sucursal_id, nombre=request.POST["nombre"])
    except NoEncontrado:
        raise
    except ErrorDeDominio as error:
        return _error(error)
    return JsonResponse({"id": str(sucursal.pk), "nombre": sucursal.nombre})


@requiere_permiso("roles.gestionar")
def roles(request: HttpRequest) -> JsonResponse:
    pagina = Paginator(accounts_selectors.listar_roles(), 25).get_page(request.GET.get("p"))
    return JsonResponse({"resultados": [str(rol.pk) for rol in pagina]})


@requiere_permiso("roles.gestionar")
def rol_detalle(request: HttpRequest, rol_id: uuid.UUID) -> JsonResponse:
    rol = accounts_selectors.obtener_rol(rol_id)
    return JsonResponse({"id": str(rol.pk), "nombre": rol.nombre})


@requiere_permiso("roles.gestionar")
@require_POST
def rol_eliminar(request: HttpRequest, rol_id: uuid.UUID) -> JsonResponse:
    try:
        accounts_services.eliminar_rol(request.membresia, rol_id)
    except NoEncontrado:
        raise
    except ErrorDeDominio as error:
        return _error(error)
    return JsonResponse({"eliminado": True})


@requiere_permiso("miembros.gestionar")
def miembros(request: HttpRequest) -> JsonResponse:
    pagina = Paginator(accounts_selectors.listar_membresias(), 25).get_page(request.GET.get("p"))
    return JsonResponse({"resultados": [str(membresia.pk) for membresia in pagina]})


@requiere_permiso("miembros.gestionar")
def miembro_detalle(request: HttpRequest, membresia_id: uuid.UUID) -> JsonResponse:
    membresia = accounts_selectors.obtener_membresia(membresia_id)
    return JsonResponse({"id": str(membresia.pk), "email": membresia.usuario.email})


@requiere_permiso("miembros.gestionar")
@require_POST
def miembro_suspender(request: HttpRequest, membresia_id: uuid.UUID) -> JsonResponse:
    try:
        accounts_services.suspender_membresia(membresia_id)
    except NoEncontrado:
        raise
    except ErrorDeDominio as error:
        return _error(error)
    return JsonResponse({"suspendida": True})

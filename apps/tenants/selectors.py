import uuid

from django.core.exceptions import ValidationError
from django.db.models import QuerySet

from apps.core.context import tenant_requerido

from .exceptions import SucursalNoEncontrada
from .models import Sucursal, Tenant


def obtener_tenant_activo() -> Tenant:
    return Tenant.objects.get(pk=tenant_requerido())


def listar_sucursales(*, solo_activas: bool = False) -> QuerySet[Sucursal]:
    sucursales = Sucursal.objects.order_by("nombre")
    if solo_activas:
        sucursales = sucursales.filter(activa=True)
    return sucursales


def obtener_sucursal(sucursal_id: uuid.UUID | str) -> Sucursal:
    try:
        return Sucursal.objects.get(pk=sucursal_id)
    except (Sucursal.DoesNotExist, ValidationError) as error:
        raise SucursalNoEncontrada() from error

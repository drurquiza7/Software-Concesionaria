import uuid
from typing import Any

from django.db import transaction

from apps.core.context import tenant_requerido
from apps.core.exceptions import DatosInvalidos
from apps.core.persistence import validar_y_guardar

from .blockers import motivos_de_bloqueo
from .exceptions import SucursalConBloqueos, UltimaSucursalActiva
from .models import Sucursal, Tenant
from .selectors import obtener_sucursal

# `slug` y `estado` quedan afuera a propósito: el slug es inmutable y el estado tiene su servicio.
CAMPOS_EDITABLES_TENANT = frozenset(
    {"nombre", "razon_social", "cuit", "zona_horaria", "moneda_por_defecto"}
)
# `activa` se cambia solo con activar_sucursal / desactivar_sucursal (RN-02 y RN-03).
CAMPOS_EDITABLES_SUCURSAL = frozenset(
    {
        "nombre",
        "slug",
        "direccion",
        "localidad",
        "provincia",
        "telefono",
        "whatsapp",
        "email",
        "meli_ubicacion",
    }
)


def _aplicar_cambios(instancia: Any, cambios: dict[str, Any], permitidos: frozenset[str]) -> None:
    no_permitidos = sorted(set(cambios) - permitidos)
    if no_permitidos:
        raise DatosInvalidos(
            {campo: ["Este dato no se puede modificar."] for campo in no_permitidos}
        )
    for campo, valor in cambios.items():
        setattr(instancia, campo, valor)


def crear_tenant(*, nombre: str, slug: str, **opcionales: Any) -> Tenant:
    tenant = Tenant(nombre=nombre, slug=slug)
    _aplicar_cambios(tenant, opcionales, CAMPOS_EDITABLES_TENANT)
    validar_y_guardar(tenant)
    return tenant


def actualizar_tenant(**cambios: Any) -> Tenant:
    """Edita la concesionaria activa. El tenant sale del contexto, nunca de un parámetro."""
    tenant = Tenant.objects.get(pk=tenant_requerido())
    _aplicar_cambios(tenant, cambios, CAMPOS_EDITABLES_TENANT)
    validar_y_guardar(tenant)
    return tenant


def cambiar_estado_tenant(tenant: Tenant, estado: str) -> Tenant:
    """Operación del personal del SaaS: suspender o reactivar una concesionaria (RN-01)."""
    tenant.estado = estado
    validar_y_guardar(tenant)
    return tenant


def crear_sucursal(*, nombre: str, slug: str, **opcionales: Any) -> Sucursal:
    sucursal = Sucursal(nombre=nombre, slug=slug)
    _aplicar_cambios(sucursal, opcionales, CAMPOS_EDITABLES_SUCURSAL)
    validar_y_guardar(sucursal)
    return sucursal


def actualizar_sucursal(sucursal_id: uuid.UUID | str, **cambios: Any) -> Sucursal:
    sucursal = obtener_sucursal(sucursal_id)
    _aplicar_cambios(sucursal, cambios, CAMPOS_EDITABLES_SUCURSAL)
    validar_y_guardar(sucursal)
    return sucursal


def activar_sucursal(sucursal_id: uuid.UUID | str) -> Sucursal:
    sucursal = obtener_sucursal(sucursal_id)
    if not sucursal.activa:
        sucursal.activa = True
        sucursal.save(update_fields=["activa", "updated_at"])
    return sucursal


@transaction.atomic
def desactivar_sucursal(sucursal_id: uuid.UUID | str) -> Sucursal:
    sucursal = obtener_sucursal(sucursal_id)
    # El lock evita que dos desactivaciones simultáneas dejen el tenant sin sucursal activa.
    activas = set(
        Sucursal.objects.select_for_update().filter(activa=True).values_list("pk", flat=True)
    )
    if sucursal.pk not in activas:
        sucursal.activa = False
        return sucursal
    if len(activas) == 1:
        raise UltimaSucursalActiva()
    motivos = motivos_de_bloqueo(sucursal)
    if motivos:
        raise SucursalConBloqueos(motivos)
    sucursal.activa = False
    sucursal.save(update_fields=["activa", "updated_at"])
    return sucursal

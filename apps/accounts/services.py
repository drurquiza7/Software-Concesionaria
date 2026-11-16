import uuid
from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.crypto import generar_token, hash_sha256
from apps.core.exceptions import DatosInvalidos
from apps.core.permissions import catalogo
from apps.core.permissions import codigos as codigos_del_catalogo
from apps.core.persistence import validar_y_guardar
from apps.tenants.exceptions import SucursalNoEncontrada
from apps.tenants.models import Sucursal

from . import selectors
from .exceptions import (
    EscaladaDePermisos,
    JerarquiaInsuficiente,
    MiembroYaExiste,
    PermisoInexistente,
    RolNoEncontrado,
    SoloPropietario,
    UltimoPropietario,
)
from .models import Membresia, MembresiaRol, MembresiaSucursal, Permiso, Rol, RolPermiso, Usuario

CAMPOS_EDITABLES_ROL = frozenset({"nombre", "color"})

# RN-11. Los códigos de otras apps van como texto: `accounts` no puede importarlas.
# De mayor a menor jerarquía; None = todos los permisos del catálogo.
ROLES_PREDETERMINADOS: tuple[tuple[str, tuple[str, ...] | None], ...] = (
    ("Administrador", None),
    (
        "Vendedor",
        (
            "vehicle.ver",
            "vehicle.crear",
            "vehicle.editar",
            "vehicle.cambiar_estado",
            "media.gestionar",
        ),
    ),
    ("Publicador", ("vehicle.ver", "media.gestionar", "meli.publicar", "meli.pausar")),
)


# --- Catálogo de permisos -----------------------------------------------------------------


@transaction.atomic
def sincronizar_permisos() -> None:
    """Lleva a la tabla Permiso el catálogo declarado en código. No borra permisos viejos."""
    for definicion in catalogo():
        Permiso.objects.update_or_create(
            codigo=definicion.codigo,
            defaults={
                "modulo": definicion.modulo,
                "nombre": definicion.nombre,
                "sensible": definicion.sensible,
            },
        )


def _permisos_por_codigo(codigos: Iterable[str]) -> list[Permiso]:
    pedidos = set(codigos)
    permisos = list(Permiso.objects.filter(codigo__in=pedidos))
    if len(permisos) != len(pedidos):
        raise PermisoInexistente()
    return permisos


# --- Reglas de jerarquía y anti-escalada --------------------------------------------------


def _verificar_jerarquia(actor: Membresia, rol: Rol) -> None:
    """RN-09: solo se gestionan roles por debajo del rol más alto propio."""
    if actor.es_propietario:
        return
    maxima = selectors.posicion_maxima(actor)
    if maxima is None or rol.posicion >= maxima:
        raise JerarquiaInsuficiente()


def _verificar_anti_escalada(actor: Membresia, codigos: Iterable[str]) -> None:
    """RN-10: nadie otorga un permiso que no posee."""
    if actor.es_propietario:
        return
    if set(codigos) - selectors.permisos_efectivos(actor):
        raise EscaladaDePermisos()


def _membresias_con_rol(rol: Rol) -> list[uuid.UUID]:
    return list(MembresiaRol.objects.filter(rol=rol).values_list("membresia_id", flat=True))


def _reemplazar_permisos(rol: Rol, permisos: Iterable[Permiso]) -> None:
    deseados = {permiso.pk: permiso for permiso in permisos}
    actuales = set(RolPermiso.objects.filter(rol=rol).values_list("permiso_id", flat=True))
    RolPermiso.objects.filter(rol=rol).exclude(permiso_id__in=deseados).delete()
    for permiso_id, permiso in deseados.items():
        if permiso_id not in actuales:
            validar_y_guardar(RolPermiso(rol=rol, permiso=permiso))
    selectors.invalidar_permisos(_membresias_con_rol(rol))


def _bloquear_roles() -> list[Rol]:
    return list(Rol.objects.select_for_update().order_by("posicion"))


# --- Roles --------------------------------------------------------------------------------


@transaction.atomic
def crear_roles_predeterminados() -> list[Rol]:
    """RN-11: roles iniciales del tenant activo. Se llama una sola vez, en el alta."""
    todos = codigos_del_catalogo()
    roles = []
    for indice, (nombre, codigos) in enumerate(ROLES_PREDETERMINADOS):
        rol = Rol(
            nombre=nombre,
            posicion=len(ROLES_PREDETERMINADOS) - indice,
            es_predeterminado=True,
        )
        validar_y_guardar(rol)
        _reemplazar_permisos(rol, _permisos_por_codigo(todos if codigos is None else codigos))
        roles.append(rol)
    return roles


@transaction.atomic
def crear_rol(
    actor: Membresia, *, nombre: str, color: str | None = None, permisos: Iterable[str] = ()
) -> Rol:
    """Crea el rol en el escalón más bajo; se sube después con mover_rol."""
    codigos = set(permisos)
    if not actor.es_propietario and selectors.posicion_maxima(actor) is None:
        raise JerarquiaInsuficiente()
    _verificar_anti_escalada(actor, codigos)
    objetos = _permisos_por_codigo(codigos)
    _bloquear_roles()
    Rol.objects.update(posicion=F("posicion") + 1)
    rol = Rol(nombre=nombre, color=color, posicion=1)
    validar_y_guardar(rol)
    _reemplazar_permisos(rol, objetos)
    return rol


@transaction.atomic
def actualizar_rol(
    actor: Membresia,
    rol_id: uuid.UUID | str,
    *,
    permisos: Iterable[str] | None = None,
    **cambios: Any,
) -> Rol:
    rol = selectors.obtener_rol(rol_id)
    _verificar_jerarquia(actor, rol)
    no_permitidos = sorted(set(cambios) - CAMPOS_EDITABLES_ROL)
    if no_permitidos:
        raise DatosInvalidos(
            {campo: ["Este dato no se puede modificar."] for campo in no_permitidos}
        )
    for campo, valor in cambios.items():
        setattr(rol, campo, valor)
    validar_y_guardar(rol)
    if permisos is not None:
        nuevos = set(permisos)
        # Quitar un permiso no es otorgarlo: la anti-escalada mira solo los que se agregan.
        _verificar_anti_escalada(actor, nuevos - selectors.codigos_de_rol(rol))
        _reemplazar_permisos(rol, _permisos_por_codigo(nuevos))
    return rol


@transaction.atomic
def eliminar_rol(actor: Membresia, rol_id: uuid.UUID | str) -> None:
    rol = selectors.obtener_rol(rol_id)
    _verificar_jerarquia(actor, rol)
    afectadas = _membresias_con_rol(rol)
    rol.delete()
    selectors.invalidar_permisos(afectadas)


@transaction.atomic
def mover_rol(actor: Membresia, rol_id: uuid.UUID | str, nueva_posicion: int) -> Rol:
    """Reubica el rol y renumera el resto de forma contigua desde 1."""
    roles = _bloquear_roles()
    rol = next((candidato for candidato in roles if str(candidato.pk) == str(rol_id)), None)
    if rol is None:
        raise RolNoEncontrado()
    _verificar_jerarquia(actor, rol)
    if not 1 <= nueva_posicion <= len(roles):
        raise DatosInvalidos({"posicion": [f"Elegí una posición entre 1 y {len(roles)}."]})
    if not actor.es_propietario:
        # El destino se compara contra la jerarquía actual: nadie sube un rol hasta su altura.
        ocupante = roles[nueva_posicion - 1]
        _verificar_jerarquia(actor, ocupante)
    roles.remove(rol)
    roles.insert(nueva_posicion - 1, rol)
    cambiados = []
    for posicion, candidato in enumerate(roles, start=1):
        if candidato.posicion != posicion:
            candidato.posicion = posicion
            cambiados.append(candidato)
    Rol.objects.bulk_update(cambiados, ["posicion"])
    return rol


# --- Membresías ---------------------------------------------------------------------------


def _verificar_no_ultimo_propietario(membresia: Membresia) -> None:
    """RN-04: siempre queda al menos un propietario con membresía activa."""
    if not (membresia.es_propietario and membresia.esta_activa):
        return
    otros = list(
        Membresia.objects.select_for_update()
        .filter(es_propietario=True, estado=Membresia.Estado.ACTIVA)
        .exclude(pk=membresia.pk)
        .values_list("pk", flat=True)
    )
    if not otros:
        raise UltimoPropietario()


@transaction.atomic
def asignar_roles(
    actor: Membresia, membresia_id: uuid.UUID | str, rol_ids: Iterable[uuid.UUID | str]
) -> Membresia:
    """Deja a la membresía exactamente con los roles indicados."""
    membresia = selectors.obtener_membresia(membresia_id)
    pedidos = {str(rol_id) for rol_id in rol_ids}
    deseados = {str(rol.pk): rol for rol in Rol.objects.filter(pk__in=pedidos)}
    # RN-06: un rol de otra concesionaria no existe para el manager del tenant activo.
    if len(deseados) != len(pedidos):
        raise RolNoEncontrado()
    asignaciones = {
        str(asignacion.rol_id): asignacion
        for asignacion in MembresiaRol.objects.filter(membresia=membresia).select_related("rol")
    }
    for clave, rol in deseados.items():
        if clave not in asignaciones:
            _verificar_jerarquia(actor, rol)
    for clave, asignacion in asignaciones.items():
        if clave not in deseados:
            _verificar_jerarquia(actor, asignacion.rol)
            asignacion.delete()
    for clave, rol in deseados.items():
        if clave not in asignaciones:
            validar_y_guardar(MembresiaRol(membresia=membresia, rol=rol))
    selectors.invalidar_permisos([membresia.pk])
    return membresia


@transaction.atomic
def asignar_sucursales(
    membresia_id: uuid.UUID | str,
    *,
    todas_las_sucursales: bool,
    sucursal_ids: Iterable[uuid.UUID | str] = (),
) -> Membresia:
    """Define el alcance por sucursal (RN-07). Con todas=True la lista se vacía."""
    membresia = selectors.obtener_membresia(membresia_id)
    pedidas = set() if todas_las_sucursales else {str(sucursal_id) for sucursal_id in sucursal_ids}
    deseadas = {str(sucursal.pk): sucursal for sucursal in Sucursal.objects.filter(pk__in=pedidas)}
    if len(deseadas) != len(pedidas):
        raise SucursalNoEncontrada()
    actuales = {
        str(asignacion.sucursal_id): asignacion
        for asignacion in MembresiaSucursal.objects.filter(membresia=membresia)
    }
    for clave, asignacion in actuales.items():
        if clave not in deseadas:
            asignacion.delete()
    for clave, sucursal in deseadas.items():
        if clave not in actuales:
            validar_y_guardar(MembresiaSucursal(membresia=membresia, sucursal=sucursal))
    membresia.todas_las_sucursales = todas_las_sucursales
    membresia.save(update_fields=["todas_las_sucursales", "updated_at"])
    return membresia


@transaction.atomic
def crear_membresia_propietario(usuario: Usuario) -> Membresia:
    """Primer propietario de una concesionaria recién creada."""
    membresia = Membresia(usuario=usuario, estado=Membresia.Estado.ACTIVA, es_propietario=True)
    validar_y_guardar(membresia)
    return membresia


@transaction.atomic
def invitar_miembro(
    actor: Membresia,
    *,
    email: str,
    nombre: str,
    apellido: str,
    rol_ids: Iterable[uuid.UUID | str] = (),
) -> tuple[Membresia, str]:
    """Crea la membresía en estado invitada. Devuelve el token en claro por única vez."""
    email = email.strip().lower()
    usuario = Usuario.objects.filter(email__iexact=email).first()
    if usuario is None:
        usuario = Usuario(email=email, nombre=nombre, apellido=apellido)
        usuario.set_unusable_password()
        validar_y_guardar(usuario)
    if Membresia.objects.filter(usuario=usuario).exists():
        raise MiembroYaExiste()
    token = generar_token()
    membresia = Membresia(
        usuario=usuario,
        estado=Membresia.Estado.INVITADA,
        invitado_por=actor.usuario,
        invitacion_token_hash=hash_sha256(token),
        invitacion_expira_at=timezone.now() + timedelta(days=settings.INVITACION_VIGENCIA_DIAS),
    )
    validar_y_guardar(membresia)
    asignar_roles(actor, membresia.pk, rol_ids)
    return membresia, token


@transaction.atomic
def suspender_membresia(membresia_id: uuid.UUID | str) -> Membresia:
    membresia = selectors.obtener_membresia(membresia_id)
    _verificar_no_ultimo_propietario(membresia)
    membresia.estado = Membresia.Estado.SUSPENDIDA
    membresia.save(update_fields=["estado", "updated_at"])
    return membresia


@transaction.atomic
def reactivar_membresia(membresia_id: uuid.UUID | str) -> Membresia:
    membresia = selectors.obtener_membresia(membresia_id)
    if membresia.estado == Membresia.Estado.SUSPENDIDA:
        membresia.estado = Membresia.Estado.ACTIVA
        membresia.save(update_fields=["estado", "updated_at"])
    return membresia


@transaction.atomic
def eliminar_membresia(membresia_id: uuid.UUID | str) -> None:
    membresia = selectors.obtener_membresia(membresia_id)
    _verificar_no_ultimo_propietario(membresia)
    eliminada_id = membresia.pk
    membresia.delete()
    selectors.invalidar_permisos([eliminada_id])


@transaction.atomic
def establecer_propietario(
    actor: Membresia, membresia_id: uuid.UUID | str, es_propietario: bool
) -> Membresia:
    """Solo un propietario nombra o quita propietarios: es el permiso total (RN-05)."""
    if not actor.es_propietario:
        raise SoloPropietario()
    membresia = selectors.obtener_membresia(membresia_id)
    if not es_propietario:
        _verificar_no_ultimo_propietario(membresia)
    membresia.es_propietario = es_propietario
    membresia.save(update_fields=["es_propietario", "updated_at"])
    return membresia

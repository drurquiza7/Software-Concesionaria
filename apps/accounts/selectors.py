import uuid
from collections.abc import Iterable

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Max, QuerySet

from apps.core.permissions import codigos as codigos_del_catalogo
from apps.tenants.models import Sucursal, Tenant

from .exceptions import MembresiaNoEncontrada, RolNoEncontrado
from .models import Membresia, MembresiaRol, Rol, RolPermiso, Usuario

# Red de seguridad: la invalidación explícita es la que mantiene el caché al día.
_TTL_PERMISOS = 15 * 60


def _clave_permisos(membresia_id: uuid.UUID) -> str:
    return f"accounts:permisos:{membresia_id}"


def invalidar_permisos(membresia_ids: Iterable[uuid.UUID]) -> None:
    cache.delete_many([_clave_permisos(membresia_id) for membresia_id in membresia_ids])


def membresias_de_usuario(usuario: Usuario) -> list[Membresia]:
    """Membresías activas del usuario en concesionarias activas, para el login y el selector.

    Única consulta del panel que cruza tenants: se hace antes de que exista un tenant activo
    y siempre acotada al usuario autenticado (excepción documentada en CLAUDE.md 4.2).
    """
    # all_tenants: login y selector de concesionaria, antes de fijar el tenant de la sesión
    membresias = Membresia.all_tenants.filter(
        usuario=usuario,
        estado=Membresia.Estado.ACTIVA,
        tenant__estado=Tenant.Estado.ACTIVO,
    )
    return list(membresias.select_related("tenant").order_by("tenant__nombre"))


def obtener_membresia_activa(usuario: Usuario) -> Membresia | None:
    """Membresía activa del usuario en el tenant del contexto, con el tenant cargado."""
    return (
        Membresia.objects.filter(usuario=usuario, estado=Membresia.Estado.ACTIVA)
        .select_related("tenant")
        .first()
    )


def permisos_efectivos(membresia: Membresia) -> frozenset[str]:
    """Unión de los permisos de todos los roles (RN-08). El propietario tiene todos (RN-05)."""
    if membresia.es_propietario:
        return codigos_del_catalogo()
    clave = _clave_permisos(membresia.pk)
    en_cache = cache.get(clave)
    if en_cache is not None:
        return frozenset(en_cache)
    permisos = frozenset(
        RolPermiso.objects.filter(rol__asignaciones__membresia=membresia)
        .values_list("permiso__codigo", flat=True)
        .distinct()
    )
    cache.set(clave, sorted(permisos), _TTL_PERMISOS)
    return permisos


def tiene_permiso(membresia: Membresia, codigo: str) -> bool:
    return codigo in permisos_efectivos(membresia)


def posicion_maxima(membresia: Membresia) -> int | None:
    """Posición del rol más alto de la membresía, o None si no tiene roles."""
    return MembresiaRol.objects.filter(membresia=membresia).aggregate(maxima=Max("rol__posicion"))[
        "maxima"
    ]


def sucursales_visibles(membresia: Membresia) -> QuerySet[Sucursal]:
    """Alcance por sucursal de la membresía (RN-07). Se aplica además del filtro por tenant."""
    if membresia.todas_las_sucursales:
        return Sucursal.objects.all()
    return Sucursal.objects.filter(
        pk__in=membresia.sucursales_asignadas.values_list("sucursal_id", flat=True)
    )


def listar_roles() -> QuerySet[Rol]:
    return Rol.objects.order_by("-posicion").prefetch_related("permisos_asignados__permiso")


def obtener_rol(rol_id: uuid.UUID | str) -> Rol:
    try:
        return Rol.objects.get(pk=rol_id)
    except (Rol.DoesNotExist, ValidationError) as error:
        raise RolNoEncontrado() from error


def codigos_de_rol(rol: Rol) -> frozenset[str]:
    return frozenset(RolPermiso.objects.filter(rol=rol).values_list("permiso__codigo", flat=True))


def listar_membresias() -> QuerySet[Membresia]:
    return (
        Membresia.objects.select_related("usuario")
        .prefetch_related("roles_asignados__rol")
        .order_by("usuario__apellido", "usuario__nombre")
    )


def obtener_membresia(membresia_id: uuid.UUID | str) -> Membresia:
    try:
        return Membresia.objects.select_related("usuario").get(pk=membresia_id)
    except (Membresia.DoesNotExist, ValidationError) as error:
        raise MembresiaNoEncontrada() from error

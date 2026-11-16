import pytest

from apps.accounts import services
from apps.accounts.models import Permiso
from apps.core.permissions import DefinicionPermiso, catalogo, codigos, registrar_permisos

# SRS 2.7: catálogo inicial del MVP -> si es sensible.
CATALOGO_SRS = {
    "tenant.configurar": True,
    "sucursal.gestionar": False,
    "miembros.gestionar": True,
    "roles.gestionar": True,
    "vehicle.ver": False,
    "vehicle.crear": False,
    "vehicle.editar": False,
    "vehicle.editar_precio": False,
    "vehicle.cambiar_estado": False,
    "media.gestionar": False,
    "stock.ver_costo": True,
    "stock.editar_costo": True,
    "stock.ver_consignacion": True,
    "stock.editar_consignacion": True,
    "meli.conectar": True,
    "meli.publicar": False,
    "meli.pausar": False,
    "apikey.gestionar": True,
    "auditoria.ver": True,
}


def test_el_catalogo_en_codigo_es_exactamente_el_del_srs() -> None:
    assert {d.codigo: d.sensible for d in catalogo()} == CATALOGO_SRS


def test_registrar_un_codigo_con_otros_datos_falla() -> None:
    with pytest.raises(ValueError):
        registrar_permisos(DefinicionPermiso("vehicle.ver", "Otro nombre"))


def test_los_roles_predeterminados_usan_codigos_del_catalogo() -> None:
    for _, permisos in services.ROLES_PREDETERMINADOS:
        assert permisos is None or set(permisos) <= codigos()


@pytest.mark.django_db
def test_la_migracion_deja_la_tabla_sincronizada_con_el_catalogo() -> None:
    en_base = {p.codigo: (p.modulo, p.nombre, p.sensible) for p in Permiso.objects.all()}
    assert en_base == {d.codigo: (d.modulo, d.nombre, d.sensible) for d in catalogo()}


@pytest.mark.django_db
def test_sincronizar_es_idempotente_y_corrige_cambios() -> None:
    Permiso.objects.filter(codigo="vehicle.ver").update(nombre="Viejo", sensible=True)
    services.sincronizar_permisos()
    services.sincronizar_permisos()
    permiso = Permiso.objects.get(codigo="vehicle.ver")
    assert (permiso.nombre, permiso.sensible) == (
        "Ver el listado y la ficha pública del vehículo",
        False,
    )
    assert Permiso.objects.count() == len(CATALOGO_SRS)

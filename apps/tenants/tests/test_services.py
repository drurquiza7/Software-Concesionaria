from collections.abc import Iterator

import pytest

from apps.core.context import tenant_context
from apps.core.exceptions import DatosInvalidos, TenantNoDefinido
from apps.tenants import blockers, selectors, services
from apps.tenants.exceptions import SucursalConBloqueos, UltimaSucursalActiva
from apps.tenants.models import Sucursal, Tenant
from tests.factories import SucursalFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def bloqueador_con_stock() -> Iterator[None]:
    """Simula lo que registrará `inventory`: la sucursal tiene vehículos en venta."""

    def bloqueador(sucursal: Sucursal) -> str | None:
        return "La sucursal tiene vehículos disponibles o reservados." if sucursal.activa else None

    blockers.registrar_bloqueador_desactivacion(bloqueador)
    yield
    blockers.quitar_bloqueador_desactivacion(bloqueador)


def test_crear_sucursal_queda_en_el_tenant_activo(en_tenant_a: Tenant) -> None:
    sucursal = services.crear_sucursal(nombre="Anexo", slug="anexo", localidad="Baradero")
    assert sucursal.tenant_id == en_tenant_a.pk
    assert sucursal.activa is True
    assert selectors.obtener_sucursal(sucursal.pk).localidad == "Baradero"


def test_crear_sucursal_sin_tenant_activo_falla() -> None:
    with pytest.raises(TenantNoDefinido):
        services.crear_sucursal(nombre="Anexo", slug="anexo")


def test_actualizar_sucursal(en_tenant_a: Tenant, sucursal_a: Sucursal) -> None:
    services.actualizar_sucursal(sucursal_a.pk, nombre="Central", telefono="+543329000000")
    assert selectors.obtener_sucursal(sucursal_a.pk).nombre == "Central"


@pytest.mark.parametrize("campo", ["activa", "tenant", "tenant_id", "id"])
def test_actualizar_sucursal_no_acepta_campos_protegidos(
    en_tenant_a: Tenant, sucursal_a: Sucursal, campo: str
) -> None:
    with pytest.raises(DatosInvalidos):
        services.actualizar_sucursal(sucursal_a.pk, **{campo: False})


def test_rn02_no_se_desactiva_la_ultima_sucursal_activa(
    en_tenant_a: Tenant, sucursal_a: Sucursal
) -> None:
    with pytest.raises(UltimaSucursalActiva):
        services.desactivar_sucursal(sucursal_a.pk)
    assert selectors.obtener_sucursal(sucursal_a.pk).activa is True


def test_rn02_con_otra_activa_si_se_puede(en_tenant_a: Tenant, sucursal_a: Sucursal) -> None:
    otra = SucursalFactory(tenant=en_tenant_a)
    services.desactivar_sucursal(sucursal_a.pk)
    assert selectors.obtener_sucursal(sucursal_a.pk).activa is False
    assert list(selectors.listar_sucursales(solo_activas=True)) == [otra]
    with pytest.raises(UltimaSucursalActiva):
        services.desactivar_sucursal(otra.pk)


def test_rn02_las_sucursales_de_otro_tenant_no_cuentan(
    en_tenant_a: Tenant, sucursal_a: Sucursal, sucursal_b: Sucursal
) -> None:
    with pytest.raises(UltimaSucursalActiva):
        services.desactivar_sucursal(sucursal_a.pk)


def test_rn03_un_bloqueador_registrado_impide_desactivar(
    en_tenant_a: Tenant, sucursal_a: Sucursal, bloqueador_con_stock: None
) -> None:
    SucursalFactory(tenant=en_tenant_a)
    with pytest.raises(SucursalConBloqueos) as error:
        services.desactivar_sucursal(sucursal_a.pk)
    assert "vehículos" in error.value.mensaje
    assert selectors.obtener_sucursal(sucursal_a.pk).activa is True


def test_activar_sucursal(en_tenant_a: Tenant, sucursal_a: Sucursal) -> None:
    SucursalFactory(tenant=en_tenant_a)
    services.desactivar_sucursal(sucursal_a.pk)
    services.activar_sucursal(sucursal_a.pk)
    assert selectors.obtener_sucursal(sucursal_a.pk).activa is True


def test_actualizar_tenant_usa_el_del_contexto(tenant_a: Tenant, tenant_b: Tenant) -> None:
    with tenant_context(tenant_a.pk):
        services.actualizar_tenant(nombre="Nuevo nombre", moneda_por_defecto="ARS")
        assert selectors.obtener_tenant_activo().nombre == "Nuevo nombre"
    assert Tenant.objects.get(pk=tenant_b.pk).nombre == "Concesionaria B"


@pytest.mark.parametrize("campo", ["slug", "estado", "id"])
def test_actualizar_tenant_no_acepta_campos_protegidos(en_tenant_a: Tenant, campo: str) -> None:
    with pytest.raises(DatosInvalidos):
        services.actualizar_tenant(**{campo: "otro"})


def test_suspender_y_reactivar_tenant(tenant_a: Tenant) -> None:
    services.cambiar_estado_tenant(tenant_a, Tenant.Estado.SUSPENDIDO)
    assert Tenant.objects.get(pk=tenant_a.pk).esta_activo is False
    with pytest.raises(DatosInvalidos):
        services.cambiar_estado_tenant(tenant_a, "borrado")

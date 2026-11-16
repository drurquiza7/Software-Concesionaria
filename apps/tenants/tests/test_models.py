import pytest
from django.db import IntegrityError, transaction

from apps.core.context import tenant_context
from apps.core.exceptions import DatosInvalidos
from apps.tenants import services
from apps.tenants.exceptions import SlugInmutable
from apps.tenants.models import Sucursal, Tenant
from tests.factories import SucursalFactory, TenantFactory

pytestmark = pytest.mark.django_db

CUIT_VALIDO = "33693450239"


def _falla_en_la_base(**campos: object) -> None:
    """La restricción vive en PostgreSQL: se guarda salteando la validación de Python."""
    with pytest.raises(IntegrityError), transaction.atomic():
        TenantFactory(**campos)


def test_valores_por_defecto() -> None:
    tenant = services.crear_tenant(nombre="Autos Sur", slug="autos-sur")
    assert tenant.estado == "activo"
    assert tenant.zona_horaria == "America/Argentina/Buenos_Aires"
    assert tenant.moneda_por_defecto == "USD"
    assert tenant.cuit is None


@pytest.mark.parametrize("slug", ["Autos-Sur", "autos sur", "autos_sur", "áutos"])
def test_slug_con_formato_invalido(slug: str) -> None:
    with pytest.raises(DatosInvalidos) as error:
        services.crear_tenant(nombre="Autos Sur", slug=slug)
    assert "slug" in error.value.errores
    _falla_en_la_base(slug=slug)


def test_slug_unico() -> None:
    TenantFactory(slug="repetido")
    with pytest.raises(DatosInvalidos):
        services.crear_tenant(nombre="Otro", slug="repetido")
    _falla_en_la_base(slug="repetido")


def test_slug_inmutable() -> None:
    tenant = TenantFactory(slug="original")
    tenant.slug = "cambiado"
    with pytest.raises(SlugInmutable):
        tenant.save()
    desde_base = Tenant.objects.get(pk=tenant.pk)
    desde_base.slug = "cambiado"
    with pytest.raises(SlugInmutable):
        desde_base.save()
    assert Tenant.objects.get(pk=tenant.pk).slug == "original"


def test_cuit_null_se_puede_repetir_pero_un_valor_no() -> None:
    TenantFactory(cuit=None)
    TenantFactory(cuit=None)
    TenantFactory(cuit=CUIT_VALIDO)
    _falla_en_la_base(cuit=CUIT_VALIDO)


def test_cuit_con_digito_verificador_invalido() -> None:
    with pytest.raises(DatosInvalidos) as error:
        services.crear_tenant(nombre="Autos Sur", slug="autos-sur", cuit="33693450230")
    assert "cuit" in error.value.errores


def test_cuit_que_no_son_once_digitos_lo_rechaza_la_base() -> None:
    _falla_en_la_base(cuit="33-6934502")


def test_estado_y_moneda_invalidos_los_rechaza_la_base() -> None:
    _falla_en_la_base(estado="borrado")
    _falla_en_la_base(moneda_por_defecto="EUR")


def test_sucursal_mismo_nombre_y_slug_en_dos_tenants(tenant_a: Tenant, tenant_b: Tenant) -> None:
    SucursalFactory(tenant=tenant_a, nombre="Norte", slug="norte")
    SucursalFactory(tenant=tenant_b, nombre="Norte", slug="norte")
    assert Sucursal.all_tenants.filter(slug="norte").count() == 2


def test_sucursal_nombre_y_slug_unicos_dentro_del_tenant(tenant_a: Tenant) -> None:
    SucursalFactory(tenant=tenant_a, nombre="Norte", slug="norte")
    with pytest.raises(IntegrityError), transaction.atomic():
        SucursalFactory(tenant=tenant_a, nombre="Norte", slug="otro")
    with pytest.raises(IntegrityError), transaction.atomic():
        SucursalFactory(tenant=tenant_a, nombre="Otro", slug="norte")
    with tenant_context(tenant_a.pk), pytest.raises(DatosInvalidos):
        services.crear_sucursal(nombre="Norte", slug="norte-2")


def test_sucursal_whatsapp_en_e164(tenant_a: Tenant) -> None:
    SucursalFactory(tenant=tenant_a, whatsapp="+5493329000000")
    with pytest.raises(IntegrityError), transaction.atomic():
        SucursalFactory(tenant=tenant_a, whatsapp="15-000000")
    with tenant_context(tenant_a.pk), pytest.raises(DatosInvalidos):
        services.crear_sucursal(nombre="Sur", slug="sur", whatsapp="15-000000")


def test_sucursal_slug_con_formato_invalido_lo_rechaza_la_base(tenant_a: Tenant) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        SucursalFactory(tenant=tenant_a, slug="Con Espacios")

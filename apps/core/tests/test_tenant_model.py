"""Comportamiento de TenantModel y sus managers, probado sobre Sucursal."""

import pytest

from apps.core.context import tenant_context
from apps.core.exceptions import TenantIncorrecto, TenantNoDefinido
from apps.tenants.models import Sucursal, Tenant
from tests.factories import SucursalFactory

pytestmark = pytest.mark.django_db


def test_objects_solo_devuelve_el_tenant_activo(
    tenant_a: Tenant, tenant_b: Tenant, sucursal_a: Sucursal, sucursal_b: Sucursal
) -> None:
    with tenant_context(tenant_a.pk):
        assert list(Sucursal.objects.all()) == [sucursal_a]
    with tenant_context(tenant_b.pk):
        assert list(Sucursal.objects.all()) == [sucursal_b]


def test_all_tenants_ve_todo(sucursal_a: Sucursal, sucursal_b: Sucursal) -> None:
    assert set(Sucursal.all_tenants.all()) == {sucursal_a, sucursal_b}


def test_guardar_asigna_el_tenant_activo(tenant_a: Tenant) -> None:
    with tenant_context(tenant_a.pk):
        sucursal = Sucursal(nombre="Anexo", slug="anexo")
        sucursal.save()
    assert sucursal.tenant_id == tenant_a.pk


def test_guardar_sin_tenant_activo_falla(tenant_a: Tenant) -> None:
    with pytest.raises(TenantNoDefinido):
        Sucursal(nombre="Anexo", slug="anexo", tenant=tenant_a).save()


def test_guardar_un_objeto_de_otro_tenant_falla(tenant_a: Tenant, sucursal_b: Sucursal) -> None:
    sucursal_b.nombre = "Tomada"
    with tenant_context(tenant_a.pk), pytest.raises(TenantIncorrecto):
        sucursal_b.save()
    assert Sucursal.all_tenants.get(pk=sucursal_b.pk).nombre == "Casa Central"


def test_crear_con_el_tenant_de_otro_falla(tenant_a: Tenant, tenant_b: Tenant) -> None:
    with tenant_context(tenant_a.pk), pytest.raises(TenantIncorrecto):
        Sucursal(nombre="Anexo", slug="anexo", tenant=tenant_b).save()


def test_borrar_un_objeto_de_otro_tenant_falla(tenant_a: Tenant, sucursal_b: Sucursal) -> None:
    with tenant_context(tenant_a.pk), pytest.raises(TenantIncorrecto):
        sucursal_b.delete()
    assert Sucursal.all_tenants.filter(pk=sucursal_b.pk).exists()


def test_update_y_delete_masivos_no_tocan_otro_tenant(
    tenant_a: Tenant, sucursal_a: Sucursal, sucursal_b: Sucursal
) -> None:
    SucursalFactory(tenant=tenant_a)
    with tenant_context(tenant_a.pk):
        assert Sucursal.objects.update(localidad="Baradero") == 2
        Sucursal.objects.exclude(pk=sucursal_a.pk).delete()
    intacta = Sucursal.all_tenants.get(pk=sucursal_b.pk)
    assert intacta.localidad is None


def test_bulk_create_asigna_y_valida_el_tenant(tenant_a: Tenant, tenant_b: Tenant) -> None:
    with tenant_context(tenant_a.pk):
        creadas = Sucursal.objects.bulk_create([Sucursal(nombre="Uno", slug="uno")])
        assert creadas[0].tenant_id == tenant_a.pk
        with pytest.raises(TenantIncorrecto):
            Sucursal.objects.bulk_create([Sucursal(nombre="Dos", slug="dos", tenant=tenant_b)])


def test_get_de_un_objeto_de_otro_tenant_no_existe(tenant_a: Tenant, sucursal_b: Sucursal) -> None:
    with tenant_context(tenant_a.pk), pytest.raises(Sucursal.DoesNotExist):
        Sucursal.objects.get(pk=sucursal_b.pk)

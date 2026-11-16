"""Los cuatro tests de aislamiento de CLAUDE.md 4.5 para sucursales."""

import uuid

import pytest
from django.test import Client

from apps.core.context import tenant_context
from apps.tenants import selectors, services
from apps.tenants.exceptions import SucursalNoEncontrada
from apps.tenants.models import Sucursal, Tenant
from tests.factories import SucursalFactory

pytestmark = [pytest.mark.django_db, pytest.mark.urls("tests.urls_prueba")]


def _en_base(sucursal: Sucursal) -> Sucursal:
    with tenant_context(sucursal.tenant_id):
        return Sucursal.objects.get(pk=sucursal.pk)


def test_lectura_cruzada_responde_404(
    cliente_a: Client, sucursal_a: Sucursal, sucursal_b: Sucursal
) -> None:
    assert cliente_a.get(f"/prueba/sucursales/{sucursal_a.pk}/").status_code == 200
    respuesta = cliente_a.get(f"/prueba/sucursales/{sucursal_b.pk}/")
    assert respuesta.status_code == 404
    assert "Casa Central" not in respuesta.content.decode()


def test_un_id_inexistente_responde_lo_mismo_que_uno_ajeno(cliente_a: Client) -> None:
    assert cliente_a.get(f"/prueba/sucursales/{uuid.uuid4()}/").status_code == 404


def test_lectura_cruzada_por_selector(en_tenant_a: Tenant, sucursal_b: Sucursal) -> None:
    with pytest.raises(SucursalNoEncontrada):
        selectors.obtener_sucursal(sucursal_b.pk)
    with pytest.raises(SucursalNoEncontrada):
        selectors.obtener_sucursal("no-es-un-uuid")


def test_el_listado_no_incluye_objetos_de_otro_tenant(
    cliente_a: Client, tenant_b: Tenant, sucursal_a: Sucursal, sucursal_b: Sucursal
) -> None:
    extra_b = SucursalFactory(tenant=tenant_b)
    ids = cliente_a.get("/prueba/sucursales/").json()["resultados"]
    assert ids == [str(sucursal_a.pk)]
    assert str(sucursal_b.pk) not in ids and str(extra_b.pk) not in ids


def test_escritura_cruzada_deja_el_objeto_intacto(
    cliente_a: Client, sucursal_a: Sucursal, sucursal_b: Sucursal
) -> None:
    respuesta = cliente_a.post(f"/prueba/sucursales/{sucursal_b.pk}/editar/", {"nombre": "Tomada"})
    assert respuesta.status_code == 404
    assert _en_base(sucursal_b).nombre == "Casa Central"
    propia = cliente_a.post(f"/prueba/sucursales/{sucursal_a.pk}/editar/", {"nombre": "Central"})
    assert propia.status_code == 200
    assert _en_base(sucursal_a).nombre == "Central"


def test_escritura_cruzada_por_servicio(
    en_tenant_a: Tenant, tenant_b: Tenant, sucursal_b: Sucursal
) -> None:
    SucursalFactory(tenant=tenant_b)
    for operacion in (
        lambda: services.actualizar_sucursal(sucursal_b.pk, nombre="Tomada"),
        lambda: services.desactivar_sucursal(sucursal_b.pk),
        lambda: services.activar_sucursal(sucursal_b.pk),
    ):
        with pytest.raises(SucursalNoEncontrada):
            operacion()
    intacta = _en_base(sucursal_b)
    assert (intacta.nombre, intacta.activa) == ("Casa Central", True)


def test_el_tenant_no_se_puede_elegir_desde_el_cliente(
    cliente_a: Client, tenant_b: Tenant, sucursal_a: Sucursal
) -> None:
    respuesta = cliente_a.get(
        "/prueba/sucursales/", {"tenant_id": str(tenant_b.pk)}, HTTP_X_TENANT_ID=str(tenant_b.pk)
    )
    assert respuesta.json()["resultados"] == [str(sucursal_a.pk)]

"""Orden de evaluación de SRS RF-02: sesión, membresía activa, tenant activo, permiso."""

import pytest
from django.test import Client

from apps.accounts.models import Membresia, Rol, Usuario
from apps.accounts.session import SESSION_TENANT_KEY
from apps.core.context import tenant_actual, tenant_context
from apps.tenants import services as tenants_services
from apps.tenants.models import Sucursal, Tenant
from tests.factories import MembresiaFactory, UsuarioFactory
from tests.fixtures import cliente_con_sesion

pytestmark = [pytest.mark.django_db, pytest.mark.urls("tests.urls_prueba")]

URL = "/prueba/sucursales/"
URL_LOGIN = "/ingresar/"
URL_SELECTOR = "/concesionarias/"


def _redirige_a(respuesta, destino: str) -> bool:
    return respuesta.status_code == 302 and respuesta["Location"].startswith(destino)


def test_sin_sesion_va_al_login() -> None:
    assert _redirige_a(Client().get(URL), URL_LOGIN)


def test_con_sesion_pero_sin_concesionaria_va_al_selector(usuario_a: Usuario) -> None:
    assert _redirige_a(cliente_con_sesion(usuario_a).get(URL), URL_SELECTOR)


def test_con_concesionaria_activa_accede_a_sus_datos(
    cliente_a: Client, sucursal_a: Sucursal
) -> None:
    respuesta = cliente_a.get(URL)
    assert respuesta.status_code == 200
    assert respuesta.json()["resultados"] == [str(sucursal_a.pk)]


def test_el_contexto_no_queda_fijado_despues_de_la_request(cliente_a: Client) -> None:
    cliente_a.get(URL)
    assert tenant_actual() is None
    cliente_a.get(f"{URL}00000000-0000-0000-0000-000000000000/")
    assert tenant_actual() is None


def test_la_sesion_no_alcanza_para_entrar_a_otro_tenant(
    usuario_a: Usuario, tenant_b: Tenant, sucursal_b: Sucursal
) -> None:
    cliente = cliente_con_sesion(usuario_a, tenant_b)
    assert _redirige_a(cliente.get(URL), URL_SELECTOR)
    assert _redirige_a(cliente.get(f"{URL}{sucursal_b.pk}/"), URL_SELECTOR)
    assert SESSION_TENANT_KEY not in cliente.session


@pytest.mark.parametrize("estado", [Membresia.Estado.SUSPENDIDA, Membresia.Estado.INVITADA])
def test_membresia_no_activa_pierde_el_acceso(tenant_a: Tenant, estado: str) -> None:
    usuario = UsuarioFactory()
    MembresiaFactory(tenant=tenant_a, usuario=usuario, estado=estado, es_propietario=True)
    cliente = cliente_con_sesion(usuario, tenant_a)
    assert _redirige_a(cliente.get(URL), URL_SELECTOR)
    assert SESSION_TENANT_KEY not in cliente.session


def test_rn01_un_tenant_suspendido_no_opera_el_panel(cliente_a: Client, tenant_a: Tenant) -> None:
    assert cliente_a.get(URL).status_code == 200
    tenants_services.cambiar_estado_tenant(tenant_a, Tenant.Estado.SUSPENDIDO)
    assert _redirige_a(cliente_a.get(URL), URL_SELECTOR)
    assert SESSION_TENANT_KEY not in cliente_a.session


def test_un_valor_basura_en_la_sesion_no_rompe_ni_da_acceso(usuario_a: Usuario) -> None:
    cliente = cliente_con_sesion(usuario_a)
    sesion = cliente.session
    sesion[SESSION_TENANT_KEY] = "no-es-un-uuid"
    sesion.save()
    assert _redirige_a(cliente.get(URL), URL_SELECTOR)


def test_un_usuario_desactivado_pierde_la_sesion(cliente_a: Client, usuario_a: Usuario) -> None:
    Usuario.objects.filter(pk=usuario_a.pk).update(is_active=False)
    assert _redirige_a(cliente_a.get(URL), URL_LOGIN)


def test_sin_el_permiso_responde_403_y_no_envia_datos(
    tenant_a: Tenant, sucursal_a: Sucursal
) -> None:
    with tenant_context(tenant_a.pk):
        publicador = Rol.objects.get(nombre="Publicador")
    usuario = UsuarioFactory()
    MembresiaFactory(tenant=tenant_a, usuario=usuario, roles=[publicador])
    respuesta = cliente_con_sesion(usuario, tenant_a).get(URL)
    assert respuesta.status_code == 403
    assert str(sucursal_a.pk) not in respuesta.content.decode()


def test_el_permiso_se_evalua_antes_de_revelar_si_el_objeto_existe(
    tenant_a: Tenant, sucursal_b: Sucursal
) -> None:
    usuario = UsuarioFactory()
    MembresiaFactory(tenant=tenant_a, usuario=usuario)
    cliente = cliente_con_sesion(usuario, tenant_a)
    assert cliente.get(f"{URL}{sucursal_b.pk}/").status_code == 403


def test_is_staff_no_da_permisos_dentro_de_un_tenant(tenant_a: Tenant) -> None:
    staff = Usuario.objects.create_superuser(
        "staff@example.com", "una-clave-larga", nombre="Staff", apellido="SaaS"
    )
    assert _redirige_a(cliente_con_sesion(staff, tenant_a).get(URL), URL_SELECTOR)

import pytest
from django.test import Client
from pytest_django import Settings

from apps.accounts.models import Membresia, Usuario
from apps.accounts.session import SESSION_TENANT_KEY
from apps.tenants import services as tenants_services
from apps.tenants.models import Tenant
from tests.factories import CLAVE_DE_PRUEBA, MembresiaFactory, UsuarioFactory
from tests.fixtures import cliente_con_sesion

pytestmark = pytest.mark.django_db

URL_LOGIN = "/ingresar/"
URL_LOGOUT = "/salir/"
URL_SELECTOR = "/concesionarias/"


@pytest.fixture(autouse=True)
def _sin_proxy(settings: Settings) -> None:
    settings.TRUSTED_PROXY_COUNT = 0


def _ingresar(cliente: Client, email: str, password: str = CLAVE_DE_PRUEBA, **extra):
    return cliente.post(URL_LOGIN, {"email": email, "password": password}, **extra)


# --- Login --------------------------------------------------------------------------------


def test_login_muestra_el_formulario() -> None:
    respuesta = Client().get(URL_LOGIN)
    assert respuesta.status_code == 200
    assert "csrfmiddlewaretoken" in respuesta.content.decode()


def test_login_exige_csrf(usuario_a: Usuario) -> None:
    cliente = Client(enforce_csrf_checks=True)
    assert _ingresar(cliente, usuario_a.email).status_code == 403


def test_login_correcto_con_una_sola_concesionaria_la_activa(
    usuario_a: Usuario, tenant_a: Tenant
) -> None:
    cliente = Client()
    respuesta = _ingresar(cliente, usuario_a.email.upper())
    assert respuesta.status_code == 302 and respuesta["Location"] == URL_SELECTOR
    assert cliente.session[SESSION_TENANT_KEY] == str(tenant_a.pk)


def test_login_con_varias_concesionarias_no_elige_por_el_usuario(
    usuario_a: Usuario, tenant_b: Tenant
) -> None:
    MembresiaFactory(tenant=tenant_b, usuario=usuario_a)
    cliente = Client()
    _ingresar(cliente, usuario_a.email)
    assert SESSION_TENANT_KEY not in cliente.session


def test_login_fallido_responde_igual_para_cualquier_motivo(usuario_a: Usuario) -> None:
    inactivo = UsuarioFactory(is_active=False)
    respuestas = [
        _ingresar(Client(), usuario_a.email, "clave-incorrecta"),
        _ingresar(Client(), "nadie@example.com"),
        _ingresar(Client(), inactivo.email),
        _ingresar(Client(), "no-es-un-email"),
    ]
    assert {r.status_code for r in respuestas} == {401}
    assert len({r.context["error"] for r in respuestas}) == 1
    assert all("_auth_user_id" not in r.client.session for r in respuestas)


def test_login_no_devuelve_la_clave_en_el_html(usuario_a: Usuario) -> None:
    respuesta = _ingresar(Client(), usuario_a.email, "clave-incorrecta-123")
    assert "clave-incorrecta-123" not in respuesta.content.decode()


@pytest.mark.parametrize("destino", ["https://malo.example.com/", "//malo.example.com"])
def test_login_ignora_un_next_externo(usuario_a: Usuario, destino: str) -> None:
    respuesta = Client().post(
        URL_LOGIN, {"email": usuario_a.email, "password": CLAVE_DE_PRUEBA, "next": destino}
    )
    assert respuesta["Location"] == URL_SELECTOR


def test_login_respeta_un_next_interno(usuario_a: Usuario) -> None:
    respuesta = Client().post(
        URL_LOGIN, {"email": usuario_a.email, "password": CLAVE_DE_PRUEBA, "next": "/healthz"}
    )
    assert respuesta["Location"] == "/healthz"


def test_rs16_limite_de_intentos_por_email(usuario_a: Usuario) -> None:
    for intento in range(5):
        respuesta = _ingresar(
            Client(), usuario_a.email, "clave-incorrecta", REMOTE_ADDR=f"10.0.0.{intento}"
        )
        assert respuesta.status_code == 401
    bloqueado = _ingresar(Client(), usuario_a.email.upper(), REMOTE_ADDR="10.0.0.99")
    assert bloqueado.status_code == 429
    assert bloqueado["Retry-After"] == "60"
    assert "_auth_user_id" not in bloqueado.client.session
    otro = UsuarioFactory()
    assert _ingresar(Client(), otro.email, REMOTE_ADDR="10.0.0.99").status_code == 302


def test_rs16_limite_de_intentos_por_ip(usuario_a: Usuario) -> None:
    for intento in range(5):
        _ingresar(Client(), f"persona{intento}@example.com", REMOTE_ADDR="10.0.0.7")
    assert _ingresar(Client(), usuario_a.email, REMOTE_ADDR="10.0.0.7").status_code == 429
    assert _ingresar(Client(), usuario_a.email, REMOTE_ADDR="10.0.0.8").status_code == 302


# --- Logout -------------------------------------------------------------------------------


def test_logout_cierra_la_sesion(cliente_a: Client) -> None:
    assert cliente_a.get(URL_LOGOUT).status_code == 405
    respuesta = cliente_a.post(URL_LOGOUT)
    assert respuesta.status_code == 302 and respuesta["Location"] == URL_LOGIN
    assert "_auth_user_id" not in cliente_a.session
    assert SESSION_TENANT_KEY not in cliente_a.session


# --- Selector de concesionaria ------------------------------------------------------------


def test_selector_sin_sesion_va_al_login() -> None:
    respuesta = Client().get(URL_SELECTOR)
    assert respuesta.status_code == 302 and respuesta["Location"].startswith(URL_LOGIN)


def test_selector_lista_solo_las_concesionarias_propias(
    usuario_a: Usuario, tenant_a: Tenant, tenant_b: Tenant, usuario_b: Usuario
) -> None:
    respuesta = cliente_con_sesion(usuario_a).get(URL_SELECTOR)
    html = respuesta.content.decode()
    assert tenant_a.nombre in html
    assert tenant_b.nombre not in html
    assert [m.tenant_id for m in respuesta.context["membresias"]] == [tenant_a.pk]


def test_selector_no_lista_membresias_inactivas_ni_tenants_suspendidos(
    usuario_a: Usuario, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    MembresiaFactory(tenant=tenant_b, usuario=usuario_a, estado=Membresia.Estado.SUSPENDIDA)
    tenants_services.cambiar_estado_tenant(tenant_a, Tenant.Estado.SUSPENDIDO)
    respuesta = cliente_con_sesion(usuario_a).get(URL_SELECTOR)
    assert respuesta.context["membresias"] == []
    assert "no tiene acceso" in respuesta.content.decode()


def test_elegir_una_concesionaria_propia(
    usuario_a: Usuario, membresia_a: Membresia, tenant_a: Tenant, tenant_b: Tenant
) -> None:
    otra = MembresiaFactory(tenant=tenant_b, usuario=usuario_a)
    cliente = cliente_con_sesion(usuario_a)
    assert cliente.post(URL_SELECTOR, {"membresia": str(otra.pk)}).status_code == 302
    assert cliente.session[SESSION_TENANT_KEY] == str(tenant_b.pk)
    cliente.post(URL_SELECTOR, {"membresia": str(membresia_a.pk)})
    assert cliente.session[SESSION_TENANT_KEY] == str(tenant_a.pk)
    assert cliente.get(URL_SELECTOR).context["tenant_activo"] == tenant_a


@pytest.mark.parametrize("valor", ["ajena", "tenant", "basura", ""])
def test_no_se_puede_elegir_una_concesionaria_ajena(
    usuario_a: Usuario, tenant_a: Tenant, tenant_b: Tenant, membresia_b: Membresia, valor: str
) -> None:
    pedido = {"ajena": str(membresia_b.pk), "tenant": str(tenant_b.pk)}.get(valor, valor)
    cliente = cliente_con_sesion(usuario_a, tenant_a)
    assert cliente.post(URL_SELECTOR, {"membresia": pedido}).status_code == 404
    assert cliente.session[SESSION_TENANT_KEY] == str(tenant_a.pk)


def test_la_raiz_lleva_al_selector() -> None:
    respuesta = Client().get("/")
    assert respuesta.status_code == 302 and respuesta["Location"] == URL_SELECTOR

from collections.abc import Iterator

import pytest
from django.core.cache import cache
from django.test import Client

from apps.accounts import services as accounts_services
from apps.accounts.models import Membresia, Rol, Usuario
from apps.accounts.session import SESSION_TENANT_KEY
from apps.core.context import tenant_context
from apps.tenants.models import Sucursal, Tenant

from .factories import MembresiaFactory, SucursalFactory, TenantFactory, UsuarioFactory


@pytest.fixture(autouse=True)
def _cache_limpio() -> Iterator[None]:
    cache.clear()
    yield
    cache.clear()


def _crear_concesionaria(sufijo: str) -> Tenant:
    tenant = TenantFactory(nombre=f"Concesionaria {sufijo.upper()}", slug=f"tenant-{sufijo}")
    SucursalFactory(tenant=tenant, nombre="Casa Central", slug="casa-central")
    with tenant_context(tenant.pk):
        accounts_services.crear_roles_predeterminados()
    return tenant


def _crear_propietario(tenant: Tenant) -> Usuario:
    usuario = UsuarioFactory()
    MembresiaFactory(tenant=tenant, usuario=usuario, es_propietario=True)
    return usuario


def _membresia(tenant: Tenant, usuario: Usuario) -> Membresia:
    with tenant_context(tenant.pk):
        return Membresia.objects.select_related("usuario").get(usuario=usuario)


def cliente_con_sesion(usuario: Usuario, tenant: Tenant | None = None) -> Client:
    cliente = Client()
    cliente.force_login(usuario)
    if tenant is not None:
        sesion = cliente.session
        sesion[SESSION_TENANT_KEY] = str(tenant.pk)
        sesion.save()
    return cliente


@pytest.fixture
def tenant_a(db: None) -> Tenant:
    return _crear_concesionaria("a")


@pytest.fixture
def tenant_b(db: None) -> Tenant:
    return _crear_concesionaria("b")


@pytest.fixture
def usuario_a(tenant_a: Tenant) -> Usuario:
    """Propietario del tenant A."""
    return _crear_propietario(tenant_a)


@pytest.fixture
def usuario_b(tenant_b: Tenant) -> Usuario:
    """Propietario del tenant B."""
    return _crear_propietario(tenant_b)


@pytest.fixture
def membresia_a(tenant_a: Tenant, usuario_a: Usuario) -> Membresia:
    return _membresia(tenant_a, usuario_a)


@pytest.fixture
def membresia_b(tenant_b: Tenant, usuario_b: Usuario) -> Membresia:
    return _membresia(tenant_b, usuario_b)


@pytest.fixture
def sucursal_a(tenant_a: Tenant) -> Sucursal:
    with tenant_context(tenant_a.pk):
        return Sucursal.objects.get(slug="casa-central")


@pytest.fixture
def sucursal_b(tenant_b: Tenant) -> Sucursal:
    with tenant_context(tenant_b.pk):
        return Sucursal.objects.get(slug="casa-central")


@pytest.fixture
def rol_b(tenant_b: Tenant) -> Rol:
    with tenant_context(tenant_b.pk):
        return Rol.objects.get(nombre="Vendedor")


@pytest.fixture
def cliente_a(usuario_a: Usuario, tenant_a: Tenant) -> Client:
    return cliente_con_sesion(usuario_a, tenant_a)


@pytest.fixture
def cliente_b(usuario_b: Usuario, tenant_b: Tenant) -> Client:
    return cliente_con_sesion(usuario_b, tenant_b)


@pytest.fixture
def en_tenant_a(tenant_a: Tenant) -> Iterator[Tenant]:
    """Corre el test con el tenant A activo, como lo dejaría el middleware."""
    with tenant_context(tenant_a.pk):
        yield tenant_a

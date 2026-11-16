from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import Membresia, Rol, Usuario
from apps.core.context import tenant_actual, tenant_context
from apps.tenants.models import Sucursal, Tenant
from tests.factories import UsuarioFactory

pytestmark = pytest.mark.django_db


def _crear(**opciones: str) -> str:
    salida = StringIO()
    argumentos = {
        "nombre": "Autos del Sur",
        "slug": "autos-del-sur",
        "email": "duena@example.com",
        "nombre_propietario": "Ana",
        "apellido_propietario": "Pérez",
        **opciones,
    }
    call_command("crear_concesionaria", stdout=salida, **argumentos)
    return salida.getvalue()


def test_crea_tenant_sucursal_roles_y_propietario() -> None:
    salida = _crear()
    tenant = Tenant.objects.get(slug="autos-del-sur")
    with tenant_context(tenant.pk):
        assert [s.slug for s in Sucursal.objects.filter(activa=True)] == ["casa-central"]
        assert set(Rol.objects.values_list("nombre", flat=True)) == {
            "Administrador",
            "Vendedor",
            "Publicador",
        }
        membresia = Membresia.objects.get()
    assert (membresia.estado, membresia.es_propietario) == (Membresia.Estado.ACTIVA, True)
    assert membresia.usuario.email == "duena@example.com"
    assert membresia.usuario.has_usable_password() is False
    assert "changepassword duena@example.com" in salida
    assert tenant_actual() is None


def test_reutiliza_un_usuario_existente_sin_tocar_su_clave() -> None:
    existente = UsuarioFactory(email="duena@example.com")
    salida = _crear(email="DUENA@example.com")
    assert Usuario.objects.count() == 1
    assert Membresia.all_tenants.get().usuario == existente
    assert "changepassword" not in salida


@pytest.mark.parametrize("opciones", [{"slug": "Slug Inválido"}, {"sucursal_slug": "Mal Slug"}])
def test_si_algo_falla_no_queda_nada_creado(opciones: dict[str, str]) -> None:
    with pytest.raises(CommandError):
        _crear(**opciones)
    assert Tenant.objects.count() == 0
    assert Usuario.objects.count() == 0
    assert Sucursal.all_tenants.count() == 0


def test_no_se_repite_el_slug() -> None:
    _crear()
    with pytest.raises(CommandError):
        _crear(email="otra@example.com")
    assert Tenant.objects.count() == 1

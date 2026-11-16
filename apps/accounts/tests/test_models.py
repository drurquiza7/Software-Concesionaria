import pytest
from django.db import IntegrityError, connection, transaction

from apps.accounts.models import Membresia, Rol, Usuario
from apps.core.context import tenant_context
from apps.core.crypto import hash_sha256
from apps.tenants.models import Tenant
from tests.factories import MembresiaFactory, RolFactory, UsuarioFactory

pytestmark = pytest.mark.django_db


def test_crear_usuario_normaliza_el_email_y_hashea_la_clave() -> None:
    usuario = Usuario.objects.create_user(
        "Ana.Perez@Example.COM", "una-clave-larga", nombre="Ana", apellido="Pérez"
    )
    assert usuario.email == "ana.perez@example.com"
    assert usuario.password != "una-clave-larga"
    assert usuario.check_password("una-clave-larga")
    assert (usuario.is_active, usuario.is_staff, usuario.is_superuser) == (True, False, False)


def test_usuario_sin_clave_no_puede_ingresar() -> None:
    usuario = Usuario.objects.create_user("ana@example.com", nombre="Ana", apellido="Pérez")
    assert usuario.has_usable_password() is False


def test_email_unico_sin_distinguir_mayusculas() -> None:
    UsuarioFactory(email="ana@example.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        Usuario(email="ANA@example.com", nombre="Otra", apellido="Ana").save()


def test_login_por_email_no_distingue_mayusculas() -> None:
    usuario = UsuarioFactory(email="ana@example.com")
    assert Usuario.objects.get_by_natural_key("ANA@Example.com") == usuario


def test_superusuario_no_tiene_membresias() -> None:
    admin = Usuario.objects.create_superuser(
        "staff@example.com", "una-clave-larga", nombre="Staff", apellido="SaaS"
    )
    assert admin.is_staff and admin.is_superuser
    assert Membresia.all_tenants.filter(usuario=admin).count() == 0


def test_repr_no_expone_datos_sensibles(tenant_a: Tenant) -> None:
    membresia = MembresiaFactory(
        tenant=tenant_a, invitacion_token_hash=hash_sha256("token-secreto")
    )
    for texto in (repr(membresia), str(membresia), repr(membresia.usuario)):
        assert membresia.invitacion_token_hash not in texto
        assert membresia.usuario.email not in texto


def test_un_usuario_tiene_una_sola_membresia_por_tenant(tenant_a: Tenant, tenant_b: Tenant) -> None:
    usuario = UsuarioFactory()
    MembresiaFactory(tenant=tenant_a, usuario=usuario)
    MembresiaFactory(tenant=tenant_b, usuario=usuario)
    with pytest.raises(IntegrityError), transaction.atomic():
        MembresiaFactory(tenant=tenant_a, usuario=usuario)


def test_estado_de_membresia_invalido_lo_rechaza_la_base(tenant_a: Tenant) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        MembresiaFactory(tenant=tenant_a, estado="eliminada")


def test_nombre_de_rol_unico_por_tenant(tenant_a: Tenant, tenant_b: Tenant) -> None:
    RolFactory(tenant=tenant_a, nombre="Gerente")
    RolFactory(tenant=tenant_b, nombre="Gerente")
    with pytest.raises(IntegrityError), transaction.atomic():
        RolFactory(tenant=tenant_a, nombre="Gerente")


def test_color_de_rol_invalido_lo_rechaza_la_base(tenant_a: Tenant) -> None:
    RolFactory(tenant=tenant_a, color="#1F5FBF")
    with pytest.raises(IntegrityError), transaction.atomic():
        RolFactory(tenant=tenant_a, color="azul")


def test_posicion_de_rol_unica_por_tenant(tenant_a: Tenant, tenant_b: Tenant) -> None:
    RolFactory(tenant=tenant_a, posicion=50)
    RolFactory(tenant=tenant_b, posicion=50)
    RolFactory(tenant=tenant_a, posicion=50)
    # La restricción es diferible: se evalúa al cerrar la transacción.
    with pytest.raises(IntegrityError):
        connection.check_constraints()


def test_la_posicion_diferible_permite_intercambiar_dos_roles(tenant_a: Tenant) -> None:
    alto = RolFactory(tenant=tenant_a, posicion=51)
    bajo = RolFactory(tenant=tenant_a, posicion=50)
    with tenant_context(tenant_a.pk):
        Rol.objects.filter(pk=alto.pk).update(posicion=50)
        Rol.objects.filter(pk=bajo.pk).update(posicion=51)
    connection.check_constraints()

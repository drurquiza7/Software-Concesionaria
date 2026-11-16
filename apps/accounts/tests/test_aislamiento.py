"""Los cuatro tests de aislamiento de CLAUDE.md 4.5 para roles y membresías."""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from apps.accounts import selectors, services
from apps.accounts.exceptions import MembresiaNoEncontrada, RolNoEncontrado
from apps.accounts.models import Membresia, MembresiaRol, Rol, RolPermiso
from apps.core.context import tenant_context
from apps.tenants.models import Tenant

pytestmark = [pytest.mark.django_db, pytest.mark.urls("tests.urls_prueba")]


def _rol_en_base(rol: Rol) -> Rol | None:
    with tenant_context(rol.tenant_id):
        return Rol.objects.filter(pk=rol.pk).first()


def _membresia_en_base(membresia: Membresia) -> Membresia:
    with tenant_context(membresia.tenant_id):
        return Membresia.objects.get(pk=membresia.pk)


# --- 1. Lectura cruzada -------------------------------------------------------------------


def test_lectura_cruzada_de_rol_responde_404(
    cliente_a: Client, tenant_a: Tenant, rol_b: Rol
) -> None:
    with tenant_context(tenant_a.pk):
        propio = Rol.objects.get(nombre="Vendedor")
    assert cliente_a.get(f"/prueba/roles/{propio.pk}/").status_code == 200
    assert cliente_a.get(f"/prueba/roles/{rol_b.pk}/").status_code == 404


def test_lectura_cruzada_de_membresia_responde_404(
    cliente_a: Client, membresia_a: Membresia, membresia_b: Membresia
) -> None:
    assert cliente_a.get(f"/prueba/miembros/{membresia_a.pk}/").status_code == 200
    respuesta = cliente_a.get(f"/prueba/miembros/{membresia_b.pk}/")
    assert respuesta.status_code == 404
    assert membresia_b.usuario.email not in respuesta.content.decode()


def test_lectura_cruzada_por_selector(
    en_tenant_a: Tenant, rol_b: Rol, membresia_b: Membresia
) -> None:
    with pytest.raises(RolNoEncontrado):
        selectors.obtener_rol(rol_b.pk)
    with pytest.raises(MembresiaNoEncontrada):
        selectors.obtener_membresia(membresia_b.pk)
    assert selectors.obtener_membresia_activa(membresia_b.usuario) is None
    assert selectors.codigos_de_rol(rol_b) == frozenset()


# --- 2. Listado ---------------------------------------------------------------------------


def test_los_listados_no_incluyen_objetos_de_otro_tenant(
    cliente_a: Client,
    tenant_a: Tenant,
    tenant_b: Tenant,
    membresia_a: Membresia,
    membresia_b: Membresia,
) -> None:
    with tenant_context(tenant_a.pk):
        roles_a = {str(pk) for pk in Rol.objects.values_list("pk", flat=True)}
    with tenant_context(tenant_b.pk):
        roles_b = {str(pk) for pk in Rol.objects.values_list("pk", flat=True)}
    listados = set(cliente_a.get("/prueba/roles/").json()["resultados"])
    assert listados == roles_a and not listados & roles_b
    assert cliente_a.get("/prueba/miembros/").json()["resultados"] == [str(membresia_a.pk)]


def test_las_membresias_de_un_usuario_no_incluyen_las_de_otros(
    membresia_a: Membresia, membresia_b: Membresia
) -> None:
    assert selectors.membresias_de_usuario(membresia_a.usuario) == [membresia_a]
    assert selectors.membresias_de_usuario(membresia_b.usuario) == [membresia_b]


# --- 3. Escritura cruzada -----------------------------------------------------------------


def test_escritura_cruzada_de_rol_lo_deja_intacto(cliente_a: Client, rol_b: Rol) -> None:
    assert cliente_a.post(f"/prueba/roles/{rol_b.pk}/eliminar/").status_code == 404
    intacto = _rol_en_base(rol_b)
    assert intacto is not None and intacto.nombre == "Vendedor"


def test_escritura_cruzada_de_membresia_la_deja_intacta(
    cliente_a: Client, membresia_b: Membresia
) -> None:
    assert cliente_a.post(f"/prueba/miembros/{membresia_b.pk}/suspender/").status_code == 404
    assert _membresia_en_base(membresia_b).estado == Membresia.Estado.ACTIVA


def test_escritura_cruzada_por_servicio(
    en_tenant_a: Tenant, membresia_a: Membresia, rol_b: Rol, membresia_b: Membresia
) -> None:
    permisos_antes = _permisos(rol_b)
    for operacion in (
        lambda: services.actualizar_rol(membresia_a, rol_b.pk, nombre="Tomado", permisos=[]),
        lambda: services.eliminar_rol(membresia_a, rol_b.pk),
        lambda: services.mover_rol(membresia_a, rol_b.pk, 1),
    ):
        with pytest.raises(RolNoEncontrado):
            operacion()
    for operacion in (
        lambda: services.asignar_roles(membresia_a, membresia_b.pk, []),
        lambda: services.suspender_membresia(membresia_b.pk),
        lambda: services.eliminar_membresia(membresia_b.pk),
        lambda: services.establecer_propietario(membresia_a, membresia_b.pk, False),
        lambda: services.asignar_sucursales(membresia_b.pk, todas_las_sucursales=False),
    ):
        with pytest.raises(MembresiaNoEncontrada):
            operacion()
    intacto = _rol_en_base(rol_b)
    assert intacto is not None and intacto.nombre == "Vendedor"
    assert _permisos(rol_b) == permisos_antes
    intacta = _membresia_en_base(membresia_b)
    assert (intacta.estado, intacta.es_propietario, intacta.todas_las_sucursales) == (
        Membresia.Estado.ACTIVA,
        True,
        True,
    )


def _permisos(rol: Rol) -> set[str]:
    with tenant_context(rol.tenant_id):
        return set(RolPermiso.objects.filter(rol=rol).values_list("permiso__codigo", flat=True))


def test_crear_un_rol_en_a_no_mueve_las_posiciones_de_b(
    en_tenant_a: Tenant, membresia_a: Membresia, rol_b: Rol
) -> None:
    services.crear_rol(membresia_a, nombre="Nuevo")
    assert _rol_en_base(rol_b).posicion == rol_b.posicion


# --- 4. FK cruzada ------------------------------------------------------------------------


def test_fk_cruzada_falla(
    en_tenant_a: Tenant, membresia_a: Membresia, rol_b: Rol, membresia_b: Membresia
) -> None:
    with tenant_context(en_tenant_a.pk):
        rol_a = Rol.objects.get(nombre="Vendedor")
    with pytest.raises(RolNoEncontrado):
        services.asignar_roles(membresia_a, membresia_a.pk, [rol_b.pk])
    with pytest.raises(ValidationError):
        MembresiaRol(membresia=membresia_a, rol=rol_b).save()
    with pytest.raises(ValidationError):
        MembresiaRol(membresia=membresia_b, rol=rol_a).save()
    assert MembresiaRol.all_tenants.count() == 0

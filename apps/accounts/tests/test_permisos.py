import pytest

from apps.accounts import selectors, services
from apps.accounts.models import Membresia, Rol
from apps.core.permissions import codigos
from apps.tenants.models import Tenant
from tests.factories import MembresiaFactory, RolFactory

pytestmark = pytest.mark.django_db


def test_rn05_el_propietario_tiene_todos_los_permisos_sin_roles(
    en_tenant_a: Tenant, membresia_a: Membresia
) -> None:
    assert selectors.posicion_maxima(membresia_a) is None
    assert selectors.permisos_efectivos(membresia_a) == codigos()
    assert selectors.tiene_permiso(membresia_a, "stock.ver_costo")


def test_sin_roles_no_hay_permisos(en_tenant_a: Tenant) -> None:
    miembro = MembresiaFactory(tenant=en_tenant_a)
    assert selectors.permisos_efectivos(miembro) == frozenset()
    assert not selectors.tiene_permiso(miembro, "vehicle.ver")


def test_rn08_los_permisos_son_la_union_de_los_roles(en_tenant_a: Tenant) -> None:
    uno = RolFactory(tenant=en_tenant_a, permisos=["vehicle.ver", "vehicle.crear"])
    otro = RolFactory(tenant=en_tenant_a, permisos=["vehicle.ver", "meli.publicar"])
    miembro = MembresiaFactory(tenant=en_tenant_a, roles=[uno, otro])
    assert selectors.permisos_efectivos(miembro) == {
        "vehicle.ver",
        "vehicle.crear",
        "meli.publicar",
    }
    assert selectors.posicion_maxima(miembro) == max(uno.posicion, otro.posicion)


def test_los_permisos_se_resuelven_en_una_consulta_y_despues_salen_del_cache(
    en_tenant_a: Tenant, django_assert_num_queries
) -> None:
    rol = RolFactory(tenant=en_tenant_a, permisos=["vehicle.ver"])
    miembro = MembresiaFactory(tenant=en_tenant_a, roles=[rol, RolFactory(tenant=en_tenant_a)])
    with django_assert_num_queries(1):
        selectors.permisos_efectivos(miembro)
    with django_assert_num_queries(0):
        assert selectors.permisos_efectivos(miembro) == {"vehicle.ver"}


def test_el_cache_se_invalida_al_cambiar_los_permisos_del_rol(
    en_tenant_a: Tenant, membresia_a: Membresia
) -> None:
    rol = RolFactory(tenant=en_tenant_a, permisos=["vehicle.ver"])
    miembro = MembresiaFactory(tenant=en_tenant_a, roles=[rol])
    assert selectors.permisos_efectivos(miembro) == {"vehicle.ver"}
    services.actualizar_rol(membresia_a, rol.pk, permisos=["vehicle.ver", "media.gestionar"])
    assert selectors.permisos_efectivos(miembro) == {"vehicle.ver", "media.gestionar"}
    services.actualizar_rol(membresia_a, rol.pk, permisos=[])
    assert selectors.permisos_efectivos(miembro) == frozenset()


def test_el_cache_se_invalida_al_cambiar_los_roles_de_la_membresia(
    en_tenant_a: Tenant, membresia_a: Membresia
) -> None:
    rol = RolFactory(tenant=en_tenant_a, permisos=["vehicle.ver"])
    miembro = MembresiaFactory(tenant=en_tenant_a)
    assert selectors.permisos_efectivos(miembro) == frozenset()
    services.asignar_roles(membresia_a, miembro.pk, [rol.pk])
    assert selectors.permisos_efectivos(miembro) == {"vehicle.ver"}
    services.asignar_roles(membresia_a, miembro.pk, [])
    assert selectors.permisos_efectivos(miembro) == frozenset()


def test_el_cache_se_invalida_al_eliminar_el_rol(
    en_tenant_a: Tenant, membresia_a: Membresia
) -> None:
    rol = RolFactory(tenant=en_tenant_a, permisos=["vehicle.ver"])
    miembro = MembresiaFactory(tenant=en_tenant_a, roles=[rol])
    assert selectors.permisos_efectivos(miembro) == {"vehicle.ver"}
    services.eliminar_rol(membresia_a, rol.pk)
    assert selectors.permisos_efectivos(miembro) == frozenset()


def test_listados_sin_n_mas_uno(en_tenant_a: Tenant, django_assert_num_queries) -> None:
    for _ in range(4):
        rol = RolFactory(tenant=en_tenant_a, permisos=["vehicle.ver", "media.gestionar"])
        MembresiaFactory(tenant=en_tenant_a, roles=[rol])
    with django_assert_num_queries(3):
        roles = list(selectors.listar_roles())
        assert all(
            len(rol.permisos_asignados.all()) >= 2 for rol in roles if not rol.es_predeterminado
        )
    with django_assert_num_queries(3):
        for membresia in selectors.listar_membresias():
            assert membresia.usuario.email
            assert [asignacion.rol.nombre for asignacion in membresia.roles_asignados.all()]


def test_rn11_roles_predeterminados(en_tenant_a: Tenant) -> None:
    roles = {rol.nombre: rol for rol in Rol.objects.all()}
    assert set(roles) == {"Administrador", "Vendedor", "Publicador"}
    assert all(rol.es_predeterminado for rol in roles.values())
    assert selectors.codigos_de_rol(roles["Administrador"]) == codigos()
    assert selectors.codigos_de_rol(roles["Vendedor"]) == {
        "vehicle.ver",
        "vehicle.crear",
        "vehicle.editar",
        "vehicle.cambiar_estado",
        "media.gestionar",
    }
    assert selectors.codigos_de_rol(roles["Publicador"]) == {
        "vehicle.ver",
        "media.gestionar",
        "meli.publicar",
        "meli.pausar",
    }
    assert (
        roles["Administrador"].posicion > roles["Vendedor"].posicion > roles["Publicador"].posicion
    )

"""Jerarquía (RN-09) y anti-escalada (RN-10) en los servicios de roles."""

import pytest
from django.db import connection

from apps.accounts import selectors, services
from apps.accounts.exceptions import (
    EscaladaDePermisos,
    JerarquiaInsuficiente,
    PermisoInexistente,
    RolNoEncontrado,
)
from apps.accounts.models import Membresia, Rol
from apps.core.exceptions import DatosInvalidos
from apps.tenants.models import Tenant
from tests.factories import MembresiaFactory

pytestmark = pytest.mark.django_db


def _rol(nombre: str) -> Rol:
    return Rol.objects.get(nombre=nombre)


def _posiciones() -> dict[str, int]:
    return dict(Rol.objects.values_list("nombre", "posicion"))


@pytest.fixture
def administrador(en_tenant_a: Tenant) -> Membresia:
    """Miembro no propietario con el rol más alto."""
    return MembresiaFactory(tenant=en_tenant_a, roles=[_rol("Administrador")])


@pytest.fixture
def gestor(en_tenant_a: Tenant, membresia_a: Membresia) -> Membresia:
    """Miembro con un rol intermedio que puede gestionar roles pero tiene pocos permisos."""
    rol = services.crear_rol(
        membresia_a,
        nombre="Gestor",
        permisos=["roles.gestionar", "miembros.gestionar", "vehicle.ver"],
    )
    services.mover_rol(membresia_a, rol.pk, 3)
    return MembresiaFactory(tenant=en_tenant_a, roles=[rol])


def test_el_propietario_crea_un_rol_en_el_escalon_mas_bajo(
    en_tenant_a: Tenant, membresia_a: Membresia
) -> None:
    rol = services.crear_rol(
        membresia_a, nombre="Gerente", color="#112233", permisos=["stock.ver_costo"]
    )
    assert selectors.codigos_de_rol(rol) == {"stock.ver_costo"}
    assert rol.es_predeterminado is False
    assert _posiciones() == {"Administrador": 4, "Vendedor": 3, "Publicador": 2, "Gerente": 1}
    connection.check_constraints()


def test_crear_rol_con_datos_invalidos(en_tenant_a: Tenant, membresia_a: Membresia) -> None:
    with pytest.raises(DatosInvalidos):
        services.crear_rol(membresia_a, nombre="Vendedor")
    with pytest.raises(DatosInvalidos):
        services.crear_rol(membresia_a, nombre="Nuevo", color="rojo")
    with pytest.raises(PermisoInexistente):
        services.crear_rol(membresia_a, nombre="Nuevo", permisos=["no.existe"])
    assert set(_posiciones()) == {"Administrador", "Vendedor", "Publicador"}


def test_rn09_no_se_edita_ni_elimina_un_rol_igual_o_superior(
    en_tenant_a: Tenant, administrador: Membresia, gestor: Membresia
) -> None:
    for actor, nombre in (
        (administrador, "Administrador"),
        (gestor, "Administrador"),
        (gestor, "Gestor"),
    ):
        with pytest.raises(JerarquiaInsuficiente):
            services.actualizar_rol(actor, _rol(nombre).pk, nombre="Tomado")
        with pytest.raises(JerarquiaInsuficiente):
            services.eliminar_rol(actor, _rol(nombre).pk)
        with pytest.raises(JerarquiaInsuficiente):
            services.mover_rol(actor, _rol(nombre).pk, 1)
    assert {"Administrador", "Gestor"} <= set(_posiciones())


def test_rn09_si_se_gestiona_un_rol_inferior(en_tenant_a: Tenant, gestor: Membresia) -> None:
    services.actualizar_rol(gestor, _rol("Publicador").pk, nombre="Publicaciones", color="#00AA00")
    assert _rol("Publicaciones").color == "#00AA00"
    services.eliminar_rol(gestor, _rol("Publicaciones").pk)
    assert "Publicaciones" not in _posiciones()


def test_rn09_el_propietario_no_tiene_limite(en_tenant_a: Tenant, membresia_a: Membresia) -> None:
    services.actualizar_rol(membresia_a, _rol("Administrador").pk, nombre="Admin")
    services.eliminar_rol(membresia_a, _rol("Admin").pk)
    assert "Admin" not in _posiciones()


def test_rn09_un_miembro_sin_roles_no_gestiona_nada(en_tenant_a: Tenant) -> None:
    sin_roles = MembresiaFactory(tenant=en_tenant_a)
    with pytest.raises(JerarquiaInsuficiente):
        services.crear_rol(sin_roles, nombre="Nuevo")
    with pytest.raises(JerarquiaInsuficiente):
        services.actualizar_rol(sin_roles, _rol("Publicador").pk, nombre="Tomado")


def test_rn09_asignar_roles_respeta_la_jerarquia(en_tenant_a: Tenant, gestor: Membresia) -> None:
    miembro = MembresiaFactory(tenant=en_tenant_a)
    services.asignar_roles(gestor, miembro.pk, [_rol("Vendedor").pk])
    for rol_alto in ("Administrador", "Gestor"):
        with pytest.raises(JerarquiaInsuficiente):
            services.asignar_roles(gestor, miembro.pk, [_rol("Vendedor").pk, _rol(rol_alto).pk])
    assert selectors.posicion_maxima(miembro) == _rol("Vendedor").posicion


def test_rn09_no_se_le_quita_a_otro_un_rol_superior(
    en_tenant_a: Tenant, gestor: Membresia, administrador: Membresia
) -> None:
    with pytest.raises(JerarquiaInsuficiente):
        services.asignar_roles(gestor, administrador.pk, [])
    # Conservar el rol superior y sumar uno inferior sí está permitido.
    services.asignar_roles(
        gestor, administrador.pk, [_rol("Administrador").pk, _rol("Vendedor").pk]
    )
    assert selectors.posicion_maxima(administrador) == _rol("Administrador").posicion


def test_rn09_no_se_escala_asignandose_un_rol_superior(
    en_tenant_a: Tenant, gestor: Membresia
) -> None:
    with pytest.raises(JerarquiaInsuficiente):
        services.asignar_roles(gestor, gestor.pk, [_rol("Gestor").pk, _rol("Administrador").pk])


def test_rn10_no_se_crea_un_rol_con_permisos_que_no_se_tienen(
    en_tenant_a: Tenant, gestor: Membresia
) -> None:
    with pytest.raises(EscaladaDePermisos):
        services.crear_rol(gestor, nombre="Costos", permisos=["vehicle.ver", "stock.ver_costo"])
    assert "Costos" not in _posiciones()
    rol = services.crear_rol(gestor, nombre="Lectura", permisos=["vehicle.ver"])
    assert selectors.codigos_de_rol(rol) == {"vehicle.ver"}


def test_rn10_no_se_agrega_a_un_rol_un_permiso_que_no_se_tiene(
    en_tenant_a: Tenant, gestor: Membresia
) -> None:
    publicador = _rol("Publicador")
    originales = selectors.codigos_de_rol(publicador)
    with pytest.raises(EscaladaDePermisos):
        services.actualizar_rol(gestor, publicador.pk, permisos=[*originales, "apikey.gestionar"])
    assert selectors.codigos_de_rol(publicador) == originales


def test_rn10_quitar_un_permiso_ajeno_no_es_escalada(
    en_tenant_a: Tenant, gestor: Membresia
) -> None:
    publicador = _rol("Publicador")
    assert "meli.publicar" not in selectors.permisos_efectivos(gestor)
    services.actualizar_rol(gestor, publicador.pk, permisos=["vehicle.ver", "meli.pausar"])
    assert selectors.codigos_de_rol(publicador) == {"vehicle.ver", "meli.pausar"}


def test_rn10_el_propietario_otorga_cualquier_permiso(
    en_tenant_a: Tenant, membresia_a: Membresia
) -> None:
    services.actualizar_rol(membresia_a, _rol("Publicador").pk, permisos=["stock.editar_costo"])
    assert selectors.codigos_de_rol(_rol("Publicador")) == {"stock.editar_costo"}


def test_actualizar_rol_no_acepta_campos_protegidos(
    en_tenant_a: Tenant, membresia_a: Membresia
) -> None:
    for campo in ("posicion", "tenant_id", "es_predeterminado"):
        with pytest.raises(DatosInvalidos):
            services.actualizar_rol(membresia_a, _rol("Vendedor").pk, **{campo: 99})


def test_mover_rol_renumera_de_forma_contigua(en_tenant_a: Tenant, membresia_a: Membresia) -> None:
    services.mover_rol(membresia_a, _rol("Publicador").pk, 3)
    assert _posiciones() == {"Publicador": 3, "Administrador": 2, "Vendedor": 1}
    connection.check_constraints()
    with pytest.raises(DatosInvalidos):
        services.mover_rol(membresia_a, _rol("Vendedor").pk, 4)
    with pytest.raises(RolNoEncontrado):
        services.mover_rol(membresia_a, "00000000-0000-0000-0000-000000000000", 1)


def test_rn09_no_se_sube_un_rol_hasta_la_altura_propia(
    en_tenant_a: Tenant, gestor: Membresia
) -> None:
    # Gestor está en la posición 3; Administrador en la 4.
    assert _posiciones()["Gestor"] == 3
    for destino in (3, 4):
        with pytest.raises(JerarquiaInsuficiente):
            services.mover_rol(gestor, _rol("Publicador").pk, destino)
    services.mover_rol(gestor, _rol("Publicador").pk, 2)
    posiciones = _posiciones()
    assert posiciones["Publicador"] == 2 and posiciones["Gestor"] == 3

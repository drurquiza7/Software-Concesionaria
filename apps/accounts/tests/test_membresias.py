from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts import selectors, services
from apps.accounts.exceptions import (
    JerarquiaInsuficiente,
    MiembroYaExiste,
    RolNoEncontrado,
    SoloPropietario,
    UltimoPropietario,
)
from apps.accounts.models import Membresia, MembresiaRol, MembresiaSucursal, Rol, Usuario
from apps.core.crypto import hash_sha256
from apps.tenants.exceptions import SucursalNoEncontrada
from apps.tenants.models import Sucursal, Tenant
from tests.factories import MembresiaFactory, SucursalFactory, UsuarioFactory

pytestmark = pytest.mark.django_db


def _estado(membresia: Membresia) -> str:
    return selectors.obtener_membresia(membresia.pk).estado


# --- RN-04: último propietario ------------------------------------------------------------


def test_rn04_no_se_suspende_al_ultimo_propietario(
    en_tenant_a: Tenant, membresia_a: Membresia
) -> None:
    with pytest.raises(UltimoPropietario):
        services.suspender_membresia(membresia_a.pk)
    assert _estado(membresia_a) == Membresia.Estado.ACTIVA


def test_rn04_no_se_elimina_al_ultimo_propietario(
    en_tenant_a: Tenant, membresia_a: Membresia
) -> None:
    with pytest.raises(UltimoPropietario):
        services.eliminar_membresia(membresia_a.pk)
    assert _estado(membresia_a) == Membresia.Estado.ACTIVA


def test_rn04_no_se_le_quita_la_propiedad_al_ultimo_propietario(
    en_tenant_a: Tenant, membresia_a: Membresia
) -> None:
    with pytest.raises(UltimoPropietario):
        services.establecer_propietario(membresia_a, membresia_a.pk, False)
    assert selectors.obtener_membresia(membresia_a.pk).es_propietario is True


def test_rn04_un_propietario_suspendido_o_de_otro_tenant_no_cuenta(
    en_tenant_a: Tenant, membresia_a: Membresia, membresia_b: Membresia
) -> None:
    MembresiaFactory(tenant=en_tenant_a, es_propietario=True, estado=Membresia.Estado.SUSPENDIDA)
    with pytest.raises(UltimoPropietario):
        services.suspender_membresia(membresia_a.pk)


def test_rn04_con_otro_propietario_activo_si_se_puede(
    en_tenant_a: Tenant, membresia_a: Membresia
) -> None:
    otro = MembresiaFactory(tenant=en_tenant_a)
    services.establecer_propietario(membresia_a, otro.pk, True)
    services.suspender_membresia(membresia_a.pk)
    assert _estado(membresia_a) == Membresia.Estado.SUSPENDIDA
    with pytest.raises(UltimoPropietario):
        services.eliminar_membresia(otro.pk)
    services.reactivar_membresia(membresia_a.pk)
    services.eliminar_membresia(otro.pk)
    assert [m.pk for m in selectors.listar_membresias()] == [membresia_a.pk]


def test_solo_un_propietario_nombra_propietarios(en_tenant_a: Tenant) -> None:
    admin = MembresiaFactory(tenant=en_tenant_a, roles=[Rol.objects.get(nombre="Administrador")])
    with pytest.raises(SoloPropietario):
        services.establecer_propietario(admin, admin.pk, True)
    assert selectors.obtener_membresia(admin.pk).es_propietario is False


def test_suspender_y_reactivar_a_un_miembro_comun(en_tenant_a: Tenant) -> None:
    miembro = MembresiaFactory(tenant=en_tenant_a)
    services.suspender_membresia(miembro.pk)
    assert _estado(miembro) == Membresia.Estado.SUSPENDIDA
    services.reactivar_membresia(miembro.pk)
    assert _estado(miembro) == Membresia.Estado.ACTIVA


# --- RN-06: roles y sucursales del mismo tenant -------------------------------------------


def test_rn06_no_se_asigna_un_rol_de_otro_tenant(
    en_tenant_a: Tenant, membresia_a: Membresia, rol_b: Rol
) -> None:
    miembro = MembresiaFactory(tenant=en_tenant_a)
    with pytest.raises(RolNoEncontrado):
        services.asignar_roles(membresia_a, miembro.pk, [rol_b.pk])
    assert selectors.posicion_maxima(miembro) is None


def test_rn06_no_se_asigna_una_sucursal_de_otro_tenant(
    en_tenant_a: Tenant, sucursal_b: Sucursal
) -> None:
    miembro = MembresiaFactory(tenant=en_tenant_a)
    with pytest.raises(SucursalNoEncontrada):
        services.asignar_sucursales(
            miembro.pk, todas_las_sucursales=False, sucursal_ids=[sucursal_b.pk]
        )
    assert selectors.obtener_membresia(miembro.pk).todas_las_sucursales is True


def test_rn06_fk_cruzada_falla_aunque_se_saltee_el_servicio(
    en_tenant_a: Tenant, membresia_a: Membresia, rol_b: Rol, sucursal_b: Sucursal
) -> None:
    with pytest.raises(ValidationError):
        MembresiaRol(membresia=membresia_a, rol=rol_b).save()
    with pytest.raises(ValidationError):
        MembresiaRol(membresia=membresia_a, rol_id=rol_b.pk).full_clean()
    # add() abre su propia transacción sin savepoint: el savepoint lo pone el test.
    with pytest.raises(ValidationError), transaction.atomic():
        membresia_a.roles.add(rol_b)
    with pytest.raises(ValidationError):
        MembresiaSucursal(membresia=membresia_a, sucursal_id=sucursal_b.pk).save()
    with pytest.raises(ValidationError):
        MembresiaSucursal.objects.bulk_create(
            [MembresiaSucursal(membresia=membresia_a, sucursal=sucursal_b)]
        )
    assert MembresiaRol.all_tenants.filter(rol=rol_b).count() == 0
    assert MembresiaSucursal.all_tenants.filter(sucursal=sucursal_b).count() == 0


# --- RN-07: alcance por sucursal ----------------------------------------------------------


def test_rn07_alcance_por_sucursal(
    en_tenant_a: Tenant, sucursal_a: Sucursal, sucursal_b: Sucursal
) -> None:
    norte = SucursalFactory(tenant=en_tenant_a, nombre="Norte")
    miembro = MembresiaFactory(tenant=en_tenant_a)
    assert set(selectors.sucursales_visibles(miembro)) == {sucursal_a, norte}

    miembro = services.asignar_sucursales(
        miembro.pk, todas_las_sucursales=False, sucursal_ids=[norte.pk]
    )
    assert list(selectors.sucursales_visibles(miembro)) == [norte]

    miembro = services.asignar_sucursales(miembro.pk, todas_las_sucursales=False, sucursal_ids=[])
    assert list(selectors.sucursales_visibles(miembro)) == []

    miembro = services.asignar_sucursales(miembro.pk, todas_las_sucursales=True)
    assert set(selectors.sucursales_visibles(miembro)) == {sucursal_a, norte}
    assert miembro.sucursales_asignadas.count() == 0


# --- Invitaciones -------------------------------------------------------------------------


def test_invitar_crea_usuario_y_membresia_invitada(
    en_tenant_a: Tenant, membresia_a: Membresia
) -> None:
    vendedor = Rol.objects.get(nombre="Vendedor")
    membresia, token = services.invitar_miembro(
        membresia_a,
        email="Nuevo@Example.com",
        nombre="Nuevo",
        apellido="Vendedor",
        rol_ids=[vendedor.pk],
    )
    assert membresia.estado == Membresia.Estado.INVITADA
    assert membresia.es_propietario is False
    assert membresia.invitado_por == membresia_a.usuario
    assert membresia.usuario.email == "nuevo@example.com"
    assert membresia.usuario.has_usable_password() is False
    # Solo se guarda el SHA-256: el token en claro no queda en ningún campo.
    assert membresia.invitacion_token_hash == hash_sha256(token)
    assert token not in str(Membresia.objects.filter(pk=membresia.pk).values().get())
    assert timedelta(days=6) < membresia.invitacion_expira_at - timezone.now() <= timedelta(days=7)
    assert selectors.posicion_maxima(membresia) == vendedor.posicion


def test_una_invitacion_pendiente_no_da_acceso(en_tenant_a: Tenant, membresia_a: Membresia) -> None:
    membresia, _ = services.invitar_miembro(
        membresia_a, email="nuevo@example.com", nombre="Nuevo", apellido="Miembro"
    )
    assert selectors.obtener_membresia_activa(membresia.usuario) is None
    assert selectors.membresias_de_usuario(membresia.usuario) == []


def test_invitar_reutiliza_un_usuario_existente(
    en_tenant_a: Tenant, membresia_a: Membresia, usuario_b: Usuario
) -> None:
    membresia, _ = services.invitar_miembro(
        membresia_a, email=usuario_b.email.upper(), nombre="Otro", apellido="Nombre"
    )
    assert membresia.usuario == usuario_b
    assert Usuario.objects.filter(email__iexact=usuario_b.email).count() == 1
    assert Usuario.objects.get(pk=usuario_b.pk).nombre == usuario_b.nombre


def test_no_se_invita_dos_veces_a_la_misma_persona(
    en_tenant_a: Tenant, membresia_a: Membresia
) -> None:
    existente = UsuarioFactory()
    MembresiaFactory(tenant=en_tenant_a, usuario=existente)
    with pytest.raises(MiembroYaExiste):
        services.invitar_miembro(
            membresia_a, email=existente.email, nombre="Nombre", apellido="Apellido"
        )


def test_invitar_con_un_rol_superior_no_deja_nada_creado(en_tenant_a: Tenant) -> None:
    vendedor = MembresiaFactory(tenant=en_tenant_a, roles=[Rol.objects.get(nombre="Vendedor")])
    admin = Rol.objects.get(nombre="Administrador")
    with pytest.raises(JerarquiaInsuficiente):
        services.invitar_miembro(
            vendedor, email="colado@example.com", nombre="Co", apellido="Lado", rol_ids=[admin.pk]
        )
    assert not Usuario.objects.filter(email="colado@example.com").exists()

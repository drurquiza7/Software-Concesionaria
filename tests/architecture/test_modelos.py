import pytest
from django.apps import apps
from django.db import models

from apps.core.exceptions import TenantNoDefinido
from apps.core.managers import TenantManager
from apps.core.models import TenantModel

# CLAUDE.md 4.1: únicos modelos que no pertenecen a una concesionaria.
MODELOS_GLOBALES = {
    "tenants.Tenant",
    "accounts.Usuario",
    "accounts.Permiso",
    "meli.MeliCategoriaAtributo",
}

MODELOS_PROPIOS = [m for m in apps.get_models() if m.__module__.startswith("apps.")]
MODELOS_DE_TENANT = [m for m in MODELOS_PROPIOS if issubclass(m, TenantModel)]


def _ids(modelos: list[type[models.Model]]) -> list[str]:
    return [modelo._meta.label for modelo in modelos]


def test_hay_modelos_para_revisar() -> None:
    assert len(MODELOS_DE_TENANT) >= 5


@pytest.mark.parametrize("modelo", MODELOS_PROPIOS, ids=_ids(MODELOS_PROPIOS))
def test_todo_modelo_es_de_tenant_o_global_declarado(modelo: type[models.Model]) -> None:
    assert issubclass(modelo, TenantModel) or modelo._meta.label in MODELOS_GLOBALES


@pytest.mark.parametrize("modelo", MODELOS_DE_TENANT, ids=_ids(MODELOS_DE_TENANT))
def test_consultar_sin_tenant_activo_lanza_tenant_no_definido(modelo: type[TenantModel]) -> None:
    for consulta in (
        lambda: modelo.objects.all(),
        lambda: modelo.objects.count(),
        lambda: modelo.objects.filter(pk=None),
        lambda: modelo.objects.get(pk=None),
    ):
        with pytest.raises(TenantNoDefinido):
            consulta()


@pytest.mark.parametrize("modelo", MODELOS_DE_TENANT, ids=_ids(MODELOS_DE_TENANT))
def test_el_manager_por_defecto_filtra_por_tenant(modelo: type[TenantModel]) -> None:
    assert isinstance(modelo._default_manager, TenantManager)
    assert modelo._default_manager.name == "objects"
    assert modelo._meta.get_field("tenant").remote_field.on_delete is models.PROTECT


@pytest.mark.parametrize("modelo", MODELOS_PROPIOS, ids=_ids(MODELOS_PROPIOS))
def test_las_m2m_usan_through_explicito_con_tenant(modelo: type[models.Model]) -> None:
    for campo in modelo._meta.local_many_to_many:
        intermedia = campo.remote_field.through
        assert not intermedia._meta.auto_created, f"{campo} necesita through explícito"
        assert issubclass(intermedia, TenantModel)


@pytest.mark.parametrize("modelo", MODELOS_DE_TENANT, ids=_ids(MODELOS_DE_TENANT))
def test_la_unicidad_incluye_tenant(modelo: type[TenantModel]) -> None:
    for restriccion in modelo._meta.constraints:
        if isinstance(restriccion, models.UniqueConstraint):
            assert "tenant" in restriccion.fields, f"{restriccion.name} no incluye tenant"
    for campo in modelo._meta.local_fields:
        # Las PK son únicas por naturaleza; cualquier otro unique=True sería global.
        assert campo.primary_key or not campo.unique, f"{modelo._meta.label}.{campo.name}"


@pytest.mark.parametrize("modelo", MODELOS_PROPIOS, ids=_ids(MODELOS_PROPIOS))
def test_pk_uuid_y_timestamps(modelo: type[models.Model]) -> None:
    assert isinstance(modelo._meta.pk, models.UUIDField)
    assert {"created_at", "updated_at"} <= {campo.name for campo in modelo._meta.fields}

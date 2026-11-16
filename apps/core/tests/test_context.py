import uuid

import pytest

from apps.core.context import tenant_actual, tenant_context, tenant_requerido
from apps.core.exceptions import TenantNoDefinido


def test_sin_contexto_no_hay_tenant() -> None:
    assert tenant_actual() is None
    with pytest.raises(TenantNoDefinido):
        tenant_requerido()


def test_el_contexto_fija_y_restaura_el_tenant() -> None:
    tenant_id = uuid.uuid4()
    with tenant_context(tenant_id) as activo:
        assert activo == tenant_id
        assert tenant_requerido() == tenant_id
    assert tenant_actual() is None


def test_acepta_texto_y_lo_normaliza_a_uuid() -> None:
    tenant_id = uuid.uuid4()
    with tenant_context(str(tenant_id)):
        assert tenant_actual() == tenant_id


def test_contextos_anidados_restauran_el_anterior() -> None:
    externo, interno = uuid.uuid4(), uuid.uuid4()
    with tenant_context(externo):
        with tenant_context(interno):
            assert tenant_actual() == interno
        assert tenant_actual() == externo


def test_se_restaura_aunque_haya_un_error() -> None:
    with pytest.raises(RuntimeError), tenant_context(uuid.uuid4()):
        raise RuntimeError
    assert tenant_actual() is None


@pytest.mark.parametrize("invalido", ["no-es-uuid", ""])
def test_un_identificador_invalido_no_fija_nada(invalido: str) -> None:
    with pytest.raises(ValueError), tenant_context(invalido):
        pass
    assert tenant_actual() is None


def test_none_lanza_tenant_no_definido() -> None:
    with pytest.raises(TenantNoDefinido), tenant_context(None):
        pass

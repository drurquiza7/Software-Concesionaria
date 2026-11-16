import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from .exceptions import TenantNoDefinido

_tenant_activo: ContextVar[uuid.UUID | None] = ContextVar("tenant_activo", default=None)


def tenant_actual() -> uuid.UUID | None:
    return _tenant_activo.get()


def tenant_requerido() -> uuid.UUID:
    tenant_id = _tenant_activo.get()
    if tenant_id is None:
        raise TenantNoDefinido()
    return tenant_id


@contextmanager
def tenant_context(tenant_id: uuid.UUID | str) -> Iterator[uuid.UUID]:
    """Fija el tenant activo. Solo se usa en los puntos de entrada de CLAUDE.md 4.3."""
    if tenant_id is None:
        raise TenantNoDefinido()
    normalizado = tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))
    token = _tenant_activo.set(normalizado)
    try:
        yield normalizado
    finally:
        _tenant_activo.reset(token)

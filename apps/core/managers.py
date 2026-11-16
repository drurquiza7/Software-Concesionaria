from collections.abc import Iterable
from typing import Any

from django.db import models

from .context import tenant_requerido


class TenantQuerySet(models.QuerySet):
    def bulk_create(self, objs: Iterable[Any], *args: Any, **kwargs: Any) -> list[Any]:
        # bulk_create no pasa por save(): se aplican acá las mismas validaciones de tenant.
        objetos = list(objs)
        for objeto in objetos:
            objeto.preparar_para_guardar()
        return super().bulk_create(objetos, *args, **kwargs)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Filtra siempre por el tenant activo y falla si no hay ninguno."""

    def get_queryset(self) -> TenantQuerySet:
        return super().get_queryset().filter(tenant_id=tenant_requerido())

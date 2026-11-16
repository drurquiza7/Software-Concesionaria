from typing import Any

from django.core.exceptions import ValidationError
from django.db import models

from .context import tenant_requerido
from .exceptions import TenantIncorrecto
from .ids import nuevo_id
from .managers import TenantManager


class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=nuevo_id, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantModel(BaseModel):
    """Base de todo modelo con datos de una concesionaria."""

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="+")

    objects = TenantManager()
    all_tenants = models.Manager()  # noqa: DJ012

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.preparar_para_guardar()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.tenant_id != tenant_requerido():
            raise TenantIncorrecto()
        return super().delete(*args, **kwargs)

    def clean_fields(self, exclude: Any = None) -> None:
        if self.tenant_id is None:
            self.tenant_id = tenant_requerido()
        super().clean_fields(exclude=exclude)

    def clean(self) -> None:
        super().clean()
        self._validar_fks_mismo_tenant()

    def preparar_para_guardar(self) -> None:
        activo = tenant_requerido()
        if self.tenant_id is None:
            self.tenant_id = activo
        elif self.tenant_id != activo:
            raise TenantIncorrecto()
        self._validar_fks_mismo_tenant()

    def _validar_fks_mismo_tenant(self) -> None:
        errores: dict[str, str] = {}
        for campo in self._meta.concrete_fields:
            modelo = campo.related_model
            if campo.name == "tenant" or not isinstance(modelo, type):
                continue
            if not issubclass(modelo, TenantModel):
                continue
            relacionado_id = getattr(self, campo.attname)
            if relacionado_id is None:
                continue
            if campo.is_cached(self):
                mismo_tenant = getattr(self, campo.name).tenant_id == self.tenant_id
            else:
                # `objects` solo ve el tenant activo: si no aparece, es de otra concesionaria.
                mismo_tenant = modelo.objects.filter(pk=relacionado_id).exists()
            if not mismo_tenant:
                errores[campo.name] = "El registro relacionado no pertenece a esta concesionaria."
        if errores:
            raise ValidationError(errores)

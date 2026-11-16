from typing import Any

from django.db import models
from django.db.models import Q

from apps.core import validators
from apps.core.choices import Moneda
from apps.core.models import BaseModel, TenantModel

from .exceptions import SlugInmutable


class Tenant(BaseModel):
    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        SUSPENDIDO = "suspendido", "Suspendido"

    nombre = models.CharField(max_length=120)
    slug = models.CharField(max_length=60, unique=True, validators=[validators.validar_slug])
    razon_social = models.CharField(max_length=160, null=True, blank=True)
    cuit = models.CharField(
        max_length=11, null=True, blank=True, unique=True, validators=[validators.validar_cuit]
    )
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.ACTIVO)
    zona_horaria = models.CharField(
        max_length=40,
        default="America/Argentina/Buenos_Aires",
        validators=[validators.validar_zona_horaria],
    )
    moneda_por_defecto = models.CharField(max_length=3, choices=Moneda.choices, default=Moneda.USD)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(slug__regex=validators.PATRON_SLUG), name="tenant_slug_formato"
            ),
            models.CheckConstraint(
                condition=Q(cuit__isnull=True) | Q(cuit__regex=validators.PATRON_CUIT),
                name="tenant_cuit_formato",
            ),
            models.CheckConstraint(
                condition=Q(estado__in=["activo", "suspendido"]), name="tenant_estado_valido"
            ),
            models.CheckConstraint(
                condition=Q(moneda_por_defecto__in=["ARS", "USD"]), name="tenant_moneda_valida"
            ),
        ]

    def __str__(self) -> str:
        return self.nombre

    def save(self, *args: Any, **kwargs: Any) -> None:
        original = getattr(self, "_slug_original", None)
        if not self._state.adding and original is not None and original != self.slug:
            raise SlugInmutable()
        super().save(*args, **kwargs)
        self._slug_original = self.slug

    @classmethod
    def from_db(cls, db: Any, field_names: Any, values: Any) -> "Tenant":
        instancia = super().from_db(db, field_names, values)
        if "slug" in field_names:
            instancia._slug_original = instancia.slug
        return instancia

    @property
    def esta_activo(self) -> bool:
        return self.estado == self.Estado.ACTIVO


class Sucursal(TenantModel):
    nombre = models.CharField(max_length=100)
    slug = models.CharField(max_length=60, validators=[validators.validar_slug])
    direccion = models.CharField(max_length=200, null=True, blank=True)
    localidad = models.CharField(max_length=100, null=True, blank=True)
    provincia = models.CharField(max_length=60, null=True, blank=True)
    telefono = models.CharField(max_length=30, null=True, blank=True)
    whatsapp = models.CharField(
        max_length=30, null=True, blank=True, validators=[validators.validar_e164]
    )
    email = models.EmailField(max_length=254, null=True, blank=True)
    # [VALIDAR] La forma de `location` que pide Mercado Libre no está confirmada (SRS 8.2).
    meli_ubicacion = models.JSONField(null=True, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "nombre"], name="sucursal_nombre_unico"),
            models.UniqueConstraint(fields=["tenant", "slug"], name="sucursal_slug_unico"),
            models.CheckConstraint(
                condition=Q(slug__regex=validators.PATRON_SLUG), name="sucursal_slug_formato"
            ),
            models.CheckConstraint(
                condition=Q(whatsapp__isnull=True) | Q(whatsapp__regex=validators.PATRON_E164),
                name="sucursal_whatsapp_e164",
            ),
        ]

    def __str__(self) -> str:
        return self.nombre

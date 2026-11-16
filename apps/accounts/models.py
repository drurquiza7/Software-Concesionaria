from typing import Any

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.core import validators
from apps.core.models import BaseModel, TenantModel


class UsuarioManager(BaseUserManager):
    def _crear(self, email: str, password: str | None, **extra: Any) -> "Usuario":
        if not email:
            raise ValueError("El email es obligatorio.")
        usuario = self.model(email=self.normalize_email(email).lower(), **extra)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> "Usuario":
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._crear(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> "Usuario":
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._crear(email, password, **extra)

    def get_by_natural_key(self, email: str) -> "Usuario":
        return self.get(email__iexact=email)


class Usuario(BaseModel, AbstractBaseUser):
    """Usuario global. No tiene tenant: accede a datos solo a través de una Membresia."""

    email = models.EmailField(max_length=254, unique=True)
    nombre = models.CharField(max_length=80)
    apellido = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)
    # is_staff / is_superuser habilitan solo el admin interno; no dan permisos en ningún tenant.
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    email_verificado_at = models.DateTimeField(null=True, blank=True)

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nombre", "apellido"]

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="usuario_email_unico_ci"),
        ]

    def __str__(self) -> str:
        return self.email

    def __repr__(self) -> str:
        return f"<Usuario {self.pk}>"

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.apellido}".strip()


class Permiso(BaseModel):
    """Catálogo global, definido en código y sincronizado en cada migración."""

    codigo = models.CharField(max_length=60, unique=True)
    modulo = models.CharField(max_length=30)
    nombre = models.CharField(max_length=100)
    descripcion = models.CharField(max_length=250, null=True, blank=True)
    sensible = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(codigo__regex=r"^[a-z_]+\.[a-z_]+$"), name="permiso_codigo_formato"
            ),
        ]

    def __str__(self) -> str:
        return self.codigo


class Rol(TenantModel):
    nombre = models.CharField(max_length=60)
    color = models.CharField(
        max_length=7, null=True, blank=True, validators=[validators.validar_color_hex]
    )
    posicion = models.IntegerField()
    es_predeterminado = models.BooleanField(default=False)
    permisos = models.ManyToManyField(Permiso, through="RolPermiso", related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "nombre"], name="rol_nombre_unico"),
            # Diferible: reordenar roles intercambia posiciones dentro de una transacción.
            models.UniqueConstraint(
                fields=["tenant", "posicion"],
                name="rol_posicion_unica",
                deferrable=models.Deferrable.DEFERRED,
            ),
            models.CheckConstraint(
                condition=Q(color__isnull=True) | Q(color__regex=validators.PATRON_COLOR_HEX),
                name="rol_color_hex",
            ),
        ]

    def __str__(self) -> str:
        return self.nombre


class RolPermiso(TenantModel):
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, related_name="permisos_asignados")
    permiso = models.ForeignKey(Permiso, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "rol", "permiso"], name="rolpermiso_unico"),
        ]

    def __str__(self) -> str:
        return f"{self.rol_id}:{self.permiso_id}"


class Membresia(TenantModel):
    class Estado(models.TextChoices):
        INVITADA = "invitada", "Invitada"
        ACTIVA = "activa", "Activa"
        SUSPENDIDA = "suspendida", "Suspendida"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="membresias"
    )
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.INVITADA)
    es_propietario = models.BooleanField(default=False)
    todas_las_sucursales = models.BooleanField(default=True)
    sucursales = models.ManyToManyField(
        "tenants.Sucursal", through="MembresiaSucursal", related_name="+"
    )
    roles = models.ManyToManyField(Rol, through="MembresiaRol", related_name="+")
    invitado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    invitacion_token_hash = models.CharField(max_length=64, null=True, blank=True)
    invitacion_expira_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["usuario", "tenant"], name="membresia_unica"),
            models.CheckConstraint(
                condition=Q(estado__in=["invitada", "activa", "suspendida"]),
                name="membresia_estado_valido",
            ),
        ]

    def __str__(self) -> str:
        return f"Membresía {self.pk}"

    def __repr__(self) -> str:
        return f"<Membresia {self.pk} estado={self.estado}>"

    @property
    def esta_activa(self) -> bool:
        return self.estado == self.Estado.ACTIVA


class MembresiaRol(TenantModel):
    membresia = models.ForeignKey(
        Membresia, on_delete=models.CASCADE, related_name="roles_asignados"
    )
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, related_name="asignaciones")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "membresia", "rol"], name="membresiarol_unico"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.membresia_id}:{self.rol_id}"


class MembresiaSucursal(TenantModel):
    membresia = models.ForeignKey(
        Membresia, on_delete=models.CASCADE, related_name="sucursales_asignadas"
    )
    sucursal = models.ForeignKey("tenants.Sucursal", on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "membresia", "sucursal"], name="membresiasucursal_unico"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.membresia_id}:{self.sucursal_id}"

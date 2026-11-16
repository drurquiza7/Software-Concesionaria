from typing import Any

import factory
from factory.django import DjangoModelFactory

from apps.accounts.models import Membresia, MembresiaRol, Permiso, Rol, RolPermiso, Usuario
from apps.core.context import tenant_context
from apps.tenants.models import Sucursal, Tenant

CLAVE_DE_PRUEBA = "clave-solo-para-tests"


class TenantFactory(DjangoModelFactory):
    class Meta:
        model = Tenant

    nombre = factory.Sequence(lambda n: f"Concesionaria {n}")
    slug = factory.Sequence(lambda n: f"concesionaria-{n}")


class UsuarioFactory(DjangoModelFactory):
    class Meta:
        model = Usuario

    email = factory.Sequence(lambda n: f"usuario{n}@example.com")
    nombre = "Nombre"
    apellido = factory.Sequence(lambda n: f"Apellido{n}")
    password = factory.django.Password(CLAVE_DE_PRUEBA)


class TenantModelFactory(DjangoModelFactory):
    """Crea el objeto dentro del contexto de su tenant, como exige TenantModel.save()."""

    class Meta:
        abstract = True

    tenant = factory.SubFactory(TenantFactory)

    @classmethod
    def _create(cls, model_class: type, *args: Any, **kwargs: Any) -> Any:
        with tenant_context(kwargs["tenant"].pk):
            instancia = model_class(*args, **kwargs)
            instancia.save()
        return instancia


class SucursalFactory(TenantModelFactory):
    class Meta:
        model = Sucursal

    nombre = factory.Sequence(lambda n: f"Sucursal {n}")
    slug = factory.Sequence(lambda n: f"sucursal-{n}")


class RolFactory(TenantModelFactory):
    class Meta:
        model = Rol
        skip_postgeneration_save = True

    nombre = factory.Sequence(lambda n: f"Rol {n}")
    posicion = factory.Sequence(lambda n: 100 + n)

    @factory.post_generation
    def permisos(self, create: bool, codigos: Any, **kwargs: Any) -> None:
        if not create or not codigos:
            return
        with tenant_context(self.tenant_id):
            for permiso in Permiso.objects.filter(codigo__in=codigos):
                RolPermiso(rol=self, permiso=permiso).save()


class MembresiaFactory(TenantModelFactory):
    class Meta:
        model = Membresia
        skip_postgeneration_save = True

    usuario = factory.SubFactory(UsuarioFactory)
    estado = Membresia.Estado.ACTIVA

    @factory.post_generation
    def roles(self, create: bool, roles: Any, **kwargs: Any) -> None:
        if not create or not roles:
            return
        with tenant_context(self.tenant_id):
            for rol in roles:
                MembresiaRol(membresia=self, rol=rol).save()

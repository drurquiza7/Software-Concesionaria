from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from apps.accounts import services
from apps.accounts.models import Usuario
from apps.core.context import tenant_context
from apps.core.exceptions import DatosInvalidos
from apps.core.persistence import validar_y_guardar
from apps.tenants import services as tenants_services


class Command(BaseCommand):
    help = (
        "Da de alta una concesionaria con su primera sucursal, los roles predeterminados "
        "y un propietario (RN-02, RN-04 y RN-11)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--nombre", required=True, help="Nombre comercial")
        parser.add_argument("--slug", required=True, help="Identificador único e inmutable")
        parser.add_argument("--sucursal", default="Casa Central", help="Nombre de la sucursal")
        parser.add_argument("--sucursal-slug", default="casa-central")
        parser.add_argument("--email", required=True, help="Email del propietario")
        parser.add_argument("--nombre-propietario", required=True)
        parser.add_argument("--apellido-propietario", required=True)

    def handle(self, *args: Any, **opciones: Any) -> None:
        email = opciones["email"].strip().lower()
        try:
            with transaction.atomic():
                tenant = tenants_services.crear_tenant(
                    nombre=opciones["nombre"], slug=opciones["slug"]
                )
                usuario = Usuario.objects.filter(email__iexact=email).first()
                usuario_nuevo = usuario is None
                if usuario is None:
                    usuario = Usuario(
                        email=email,
                        nombre=opciones["nombre_propietario"],
                        apellido=opciones["apellido_propietario"],
                    )
                    usuario.set_unusable_password()
                    validar_y_guardar(usuario)
                # Alta de concesionaria: todavía no hay sesión ni API Key que fije el tenant.
                with tenant_context(tenant.pk):
                    tenants_services.crear_sucursal(
                        nombre=opciones["sucursal"], slug=opciones["sucursal_slug"]
                    )
                    services.crear_roles_predeterminados()
                    services.crear_membresia_propietario(usuario)
        except DatosInvalidos as error:
            detalle = "; ".join(
                f"{campo}: {' '.join(mensajes)}" for campo, mensajes in error.errores.items()
            )
            raise CommandError(f"No se pudo crear la concesionaria. {detalle}") from error

        self.stdout.write(
            self.style.SUCCESS(f"Concesionaria creada: {tenant.nombre} ({tenant.slug})")
        )
        if usuario_nuevo:
            self.stdout.write(
                f"El propietario no tiene contraseña. Definila con: "
                f"python manage.py changepassword {email}"
            )

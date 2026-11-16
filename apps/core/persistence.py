from django.core.exceptions import ValidationError
from django.db import models

from .exceptions import DatosInvalidos


def validar_y_guardar(instancia: models.Model, update_fields: list[str] | None = None) -> None:
    """Corre full_clean() y guarda. Traduce los errores de validación al dominio."""
    try:
        instancia.full_clean()
    except ValidationError as error:
        raise DatosInvalidos(error.message_dict) from error
    instancia.save(update_fields=update_fields)

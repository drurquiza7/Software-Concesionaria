from typing import Any

from django.db import models

from .crypto import cifrar, descifrar


class EncryptedTextField(models.TextField):
    """Texto cifrado con Fernet en la base. No admite búsquedas por valor."""

    def get_prep_value(self, value: Any) -> str | None:
        value = super().get_prep_value(value)
        if value is None:
            return None
        return cifrar(value)

    def from_db_value(self, value: str | None, expression: Any, connection: Any) -> str | None:
        if value is None:
            return None
        return descifrar(value)

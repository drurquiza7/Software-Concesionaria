import re
import zoneinfo

from django.core.exceptions import ValidationError

PATRON_SLUG = r"^[a-z0-9-]+$"
PATRON_CUIT = r"^[0-9]{11}$"
PATRON_E164 = r"^\+[1-9][0-9]{6,14}$"
PATRON_COLOR_HEX = r"^#[0-9A-Fa-f]{6}$"

_PESOS_CUIT = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def digito_verificador_cuit(primeros_diez: str) -> int | None:
    """Devuelve el dígito verificador, o None si la combinación no admite ninguno."""
    suma = sum(int(digito) * peso for digito, peso in zip(primeros_diez, _PESOS_CUIT, strict=True))
    resto = 11 - (suma % 11)
    if resto == 11:
        return 0
    if resto == 10:
        return None
    return resto


def validar_slug(valor: str) -> None:
    if not re.fullmatch(PATRON_SLUG, valor):
        raise ValidationError("Usá solo minúsculas, números y guiones.")


def validar_cuit(valor: str) -> None:
    if not re.fullmatch(PATRON_CUIT, valor):
        raise ValidationError("El CUIT son 11 dígitos, sin guiones ni espacios.")
    if digito_verificador_cuit(valor[:10]) != int(valor[10]):
        raise ValidationError("El CUIT no es válido: revisá el dígito verificador.")


def validar_e164(valor: str) -> None:
    if not re.fullmatch(PATRON_E164, valor):
        raise ValidationError("Usá el formato internacional, por ejemplo +5493329000000.")


def validar_color_hex(valor: str) -> None:
    if not re.fullmatch(PATRON_COLOR_HEX, valor):
        raise ValidationError("El color va en formato #RRGGBB.")


def validar_zona_horaria(valor: str) -> None:
    try:
        zoneinfo.ZoneInfo(valor)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError) as error:
        raise ValidationError("La zona horaria no existe.") from error

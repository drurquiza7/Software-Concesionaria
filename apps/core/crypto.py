import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .exceptions import ErrorDeCifrado


def _fernet() -> MultiFernet:
    claves = settings.FIELD_ENCRYPTION_KEYS
    if not claves:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS no tiene ninguna clave.")
    return MultiFernet([Fernet(clave) for clave in claves])


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def descifrar(cifrado: str) -> str:
    try:
        return _fernet().decrypt(cifrado.encode()).decode()
    except InvalidToken as error:
        raise ErrorDeCifrado() from error


def rotar(cifrado: str) -> str:
    """Vuelve a cifrar con la clave principal un valor cifrado con una clave anterior."""
    try:
        return _fernet().rotate(cifrado.encode()).decode()
    except InvalidToken as error:
        raise ErrorDeCifrado() from error


def generar_token() -> str:
    return secrets.token_urlsafe(32)


def hash_sha256(valor: str) -> str:
    return hashlib.sha256(valor.encode()).hexdigest()


def hashes_iguales(hash_a: str, hash_b: str) -> bool:
    return hmac.compare_digest(hash_a, hash_b)

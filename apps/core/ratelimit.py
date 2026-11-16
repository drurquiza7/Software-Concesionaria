from django.core.cache import cache

from .crypto import hash_sha256


def registrar_intento(ambito: str, identificador: str, limite: int, ventana_segundos: int) -> bool:
    """Cuenta un intento en una ventana fija. Devuelve False si se superó el límite."""
    # El identificador se hashea: puede ser un email y no debe quedar en claro en Redis.
    clave = f"ratelimit:{ambito}:{hash_sha256(identificador)}"
    if cache.add(clave, 1, ventana_segundos):
        return True
    try:
        intentos = cache.incr(clave)
    except ValueError:
        # La clave venció entre el add y el incr: arranca una ventana nueva.
        cache.set(clave, 1, ventana_segundos)
        return True
    return intentos <= limite

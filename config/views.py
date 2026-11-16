from django.core.cache import cache
from django.db import DatabaseError, connection
from django.http import HttpRequest, JsonResponse
from redis.exceptions import RedisError

from apps.accounts.decorators import vista_publica


def _base_de_datos_ok() -> bool:
    try:
        connection.ensure_connection()
        return connection.is_usable()
    except DatabaseError:
        return False


def _redis_ok() -> bool:
    try:
        cache.set("healthz", "ok", 5)
        return cache.get("healthz") == "ok"
    except (RedisError, OSError):
        return False


@vista_publica
def healthz(request: HttpRequest) -> JsonResponse:
    chequeos = {"database": _base_de_datos_ok(), "redis": _redis_ok()}
    todo_ok = all(chequeos.values())
    return JsonResponse(
        {"status": "ok" if todo_ok else "error", **chequeos},
        status=200 if todo_ok else 503,
    )

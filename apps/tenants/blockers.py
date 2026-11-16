from collections.abc import Callable

from .models import Sucursal

# Un bloqueador recibe la sucursal y devuelve el motivo que impide desactivarla, o None.
BloqueadorDesactivacion = Callable[[Sucursal], str | None]

_bloqueadores: list[BloqueadorDesactivacion] = []


def registrar_bloqueador_desactivacion(bloqueador: BloqueadorDesactivacion) -> None:
    """Punto de extensión de RN-03: `tenants` no puede importar a las apps que la bloquean."""
    if bloqueador not in _bloqueadores:
        _bloqueadores.append(bloqueador)


def quitar_bloqueador_desactivacion(bloqueador: BloqueadorDesactivacion) -> None:
    if bloqueador in _bloqueadores:
        _bloqueadores.remove(bloqueador)


def motivos_de_bloqueo(sucursal: Sucursal) -> list[str]:
    motivos = (bloqueador(sucursal) for bloqueador in _bloqueadores)
    return [motivo for motivo in motivos if motivo]

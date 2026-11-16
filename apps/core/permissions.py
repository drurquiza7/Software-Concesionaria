from dataclasses import dataclass


@dataclass(frozen=True)
class DefinicionPermiso:
    codigo: str
    nombre: str
    sensible: bool = False

    @property
    def modulo(self) -> str:
        return self.codigo.split(".", 1)[0]


_registro: dict[str, DefinicionPermiso] = {}


def registrar_permisos(*definiciones: DefinicionPermiso) -> None:
    for definicion in definiciones:
        existente = _registro.get(definicion.codigo)
        if existente is not None and existente != definicion:
            raise ValueError(f"El permiso {definicion.codigo} ya está registrado con otros datos.")
        _registro[definicion.codigo] = definicion


def catalogo() -> tuple[DefinicionPermiso, ...]:
    return tuple(sorted(_registro.values(), key=lambda definicion: definicion.codigo))


def codigos() -> frozenset[str]:
    return frozenset(_registro)


# El registro de auditoría todavía no tiene app propia; su permiso se declara acá.
AUDITORIA_VER = "auditoria.ver"

registrar_permisos(
    DefinicionPermiso(AUDITORIA_VER, "Consultar el registro de auditoría", sensible=True),
)

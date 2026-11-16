class ErrorDeDominio(Exception):
    """Base de las excepciones de negocio. `mensaje` es apto para mostrar al usuario."""

    mensaje = "No se pudo completar la operación."

    def __init__(self, mensaje: str | None = None) -> None:
        if mensaje is not None:
            self.mensaje = mensaje
        super().__init__(self.mensaje)


class NoEncontrado(ErrorDeDominio):
    """El objeto no existe, es de otro tenant o está fuera de alcance. Se traduce a 404."""

    mensaje = "No encontramos lo que buscabas."


class DatosInvalidos(ErrorDeDominio):
    mensaje = "Revisá los datos ingresados."

    def __init__(self, errores: dict[str, list[str]], mensaje: str | None = None) -> None:
        self.errores = errores
        super().__init__(mensaje)


class TenantNoDefinido(ErrorDeDominio):
    mensaje = "No hay una concesionaria activa para esta operación."


class TenantIncorrecto(ErrorDeDominio):
    mensaje = "El registro pertenece a otra concesionaria."


class ErrorDeCifrado(ErrorDeDominio):
    mensaje = "No se pudo leer un dato protegido."

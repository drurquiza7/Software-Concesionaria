from apps.core.exceptions import ErrorDeDominio, NoEncontrado


class SucursalNoEncontrada(NoEncontrado):
    mensaje = "No encontramos esa sucursal."


class SlugInmutable(ErrorDeDominio):
    mensaje = "El identificador de la concesionaria no se puede cambiar después del alta."


class UltimaSucursalActiva(ErrorDeDominio):
    mensaje = "No podés desactivar la única sucursal activa. Activá otra primero."


class SucursalConBloqueos(ErrorDeDominio):
    mensaje = "La sucursal no se puede desactivar todavía."

    def __init__(self, motivos: list[str]) -> None:
        self.motivos = motivos
        super().__init__(" ".join(motivos))

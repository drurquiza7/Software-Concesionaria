from apps.core.exceptions import ErrorDeDominio, NoEncontrado


class RolNoEncontrado(NoEncontrado):
    mensaje = "No encontramos ese rol."


class MembresiaNoEncontrada(NoEncontrado):
    mensaje = "No encontramos a ese miembro."


class PermisoInexistente(ErrorDeDominio):
    mensaje = "Alguno de los permisos elegidos no existe."


class JerarquiaInsuficiente(ErrorDeDominio):
    mensaje = "Solo podés gestionar roles que estén por debajo de tu rol más alto."


class EscaladaDePermisos(ErrorDeDominio):
    mensaje = "No podés otorgar permisos que vos no tenés."


class UltimoPropietario(ErrorDeDominio):
    mensaje = "La concesionaria necesita al menos un propietario activo. Nombrá otro primero."


class SoloPropietario(ErrorDeDominio):
    mensaje = "Solo un propietario puede hacer este cambio."


class MiembroYaExiste(ErrorDeDominio):
    mensaje = "Esa persona ya es miembro o ya tiene una invitación pendiente."

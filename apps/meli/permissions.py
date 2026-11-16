from apps.core.permissions import DefinicionPermiso, registrar_permisos

MELI_CONECTAR = "meli.conectar"
MELI_PUBLICAR = "meli.publicar"
MELI_PAUSAR = "meli.pausar"

registrar_permisos(
    DefinicionPermiso(MELI_CONECTAR, "Vincular o desvincular la cuenta de ML", sensible=True),
    DefinicionPermiso(MELI_PUBLICAR, "Publicar y editar publicaciones"),
    DefinicionPermiso(MELI_PAUSAR, "Pausar, reactivar y cerrar publicaciones"),
)

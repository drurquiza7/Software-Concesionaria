from apps.core.permissions import DefinicionPermiso, registrar_permisos

MEDIA_GESTIONAR = "media.gestionar"

registrar_permisos(
    DefinicionPermiso(MEDIA_GESTIONAR, "Subir, ordenar y eliminar imágenes"),
)

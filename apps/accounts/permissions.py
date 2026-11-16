from apps.core.permissions import DefinicionPermiso, registrar_permisos

MIEMBROS_GESTIONAR = "miembros.gestionar"
ROLES_GESTIONAR = "roles.gestionar"

registrar_permisos(
    DefinicionPermiso(
        MIEMBROS_GESTIONAR, "Invitar, suspender y asignar roles a usuarios", sensible=True
    ),
    DefinicionPermiso(ROLES_GESTIONAR, "Crear, editar y eliminar roles", sensible=True),
)

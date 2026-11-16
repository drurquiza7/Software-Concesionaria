from apps.core.permissions import DefinicionPermiso, registrar_permisos

APIKEY_GESTIONAR = "apikey.gestionar"

registrar_permisos(
    DefinicionPermiso(APIKEY_GESTIONAR, "Crear y revocar API Keys", sensible=True),
)

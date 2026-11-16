from apps.core.permissions import DefinicionPermiso, registrar_permisos

TENANT_CONFIGURAR = "tenant.configurar"
SUCURSAL_GESTIONAR = "sucursal.gestionar"

registrar_permisos(
    DefinicionPermiso(TENANT_CONFIGURAR, "Editar datos de la concesionaria", sensible=True),
    DefinicionPermiso(SUCURSAL_GESTIONAR, "Crear, editar y desactivar sucursales"),
)

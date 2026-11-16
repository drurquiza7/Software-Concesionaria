from apps.core.permissions import DefinicionPermiso, registrar_permisos

VEHICLE_VER = "vehicle.ver"
VEHICLE_CREAR = "vehicle.crear"
VEHICLE_EDITAR = "vehicle.editar"
VEHICLE_EDITAR_PRECIO = "vehicle.editar_precio"
VEHICLE_CAMBIAR_ESTADO = "vehicle.cambiar_estado"
STOCK_VER_COSTO = "stock.ver_costo"
STOCK_EDITAR_COSTO = "stock.editar_costo"
STOCK_VER_CONSIGNACION = "stock.ver_consignacion"
STOCK_EDITAR_CONSIGNACION = "stock.editar_consignacion"

registrar_permisos(
    DefinicionPermiso(VEHICLE_VER, "Ver el listado y la ficha pública del vehículo"),
    DefinicionPermiso(VEHICLE_CREAR, "Dar de alta vehículos"),
    DefinicionPermiso(VEHICLE_EDITAR, "Editar datos públicos"),
    DefinicionPermiso(VEHICLE_EDITAR_PRECIO, "Modificar el precio de venta"),
    DefinicionPermiso(VEHICLE_CAMBIAR_ESTADO, "Reservar, marcar vendido, dar de baja"),
    DefinicionPermiso(STOCK_VER_COSTO, "Ver toma, gastos, costo total y margen", sensible=True),
    DefinicionPermiso(STOCK_EDITAR_COSTO, "Editar toma, gastos y margen mínimo", sensible=True),
    DefinicionPermiso(STOCK_VER_CONSIGNACION, "Ver datos del dueño anterior", sensible=True),
    DefinicionPermiso(STOCK_EDITAR_CONSIGNACION, "Editar datos del dueño anterior", sensible=True),
)

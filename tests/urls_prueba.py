from django.urls import include, path

from . import vistas_prueba as vistas

urlpatterns = [
    path("", include("config.urls")),
    path("prueba/sucursales/", vistas.sucursales),
    path("prueba/sucursales/<uuid:sucursal_id>/", vistas.sucursal_detalle),
    path("prueba/sucursales/<uuid:sucursal_id>/editar/", vistas.sucursal_editar),
    path("prueba/roles/", vistas.roles),
    path("prueba/roles/<uuid:rol_id>/", vistas.rol_detalle),
    path("prueba/roles/<uuid:rol_id>/eliminar/", vistas.rol_eliminar),
    path("prueba/miembros/", vistas.miembros),
    path("prueba/miembros/<uuid:membresia_id>/", vistas.miembro_detalle),
    path("prueba/miembros/<uuid:membresia_id>/suspender/", vistas.miembro_suspender),
]

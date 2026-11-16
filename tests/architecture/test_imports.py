import ast

import pytest

from ._codigo import APPS, RAIZ, arbol, archivos_de_aplicacion, modulos_importados, relativa

# CLAUDE.md 3: una app solo importa de las que tiene a su derecha.
DEPENDENCIAS_PERMITIDAS = {
    "core": set(),
    "tenants": {"core"},
    "accounts": {"tenants", "core"},
    "inventory": {"tenants", "accounts", "core"},
    "media": {"inventory", "tenants", "core"},
    "meli": {"inventory", "media", "tenants", "core"},
    "public_api": {"inventory", "media", "tenants", "core"},
}


def test_el_mapa_cubre_todas_las_apps() -> None:
    carpetas = {ruta.name for ruta in (RAIZ / "apps").iterdir() if (ruta / "apps.py").exists()}
    assert carpetas == set(APPS) == set(DEPENDENCIAS_PERMITIDAS)


@pytest.mark.parametrize("app", APPS)
def test_direccion_de_dependencias_entre_apps(app: str) -> None:
    infracciones = []
    for ruta in archivos_de_aplicacion(f"apps/{app}"):
        for modulo in modulos_importados(ruta):
            partes = modulo.split(".")
            if partes[0] != "apps" or len(partes) < 2 or partes[1] == app:
                continue
            if partes[1] not in DEPENDENCIAS_PERMITIDAS[app]:
                infracciones.append(f"{relativa(ruta)} importa {modulo}")
    assert not infracciones, "\n".join(infracciones)


def test_public_api_no_importa_inventory_internal() -> None:
    infracciones = [
        f"{relativa(ruta)} importa {modulo}"
        for ruta in archivos_de_aplicacion("apps/public_api")
        for modulo in modulos_importados(ruta)
        if modulo.startswith("apps.inventory.internal")
    ]
    assert not infracciones, "\n".join(infracciones)


def test_inventory_internal_solo_lo_importa_inventory() -> None:
    infracciones = [
        f"{relativa(ruta)} importa {modulo}"
        for ruta in archivos_de_aplicacion("apps")
        for modulo in modulos_importados(ruta)
        if modulo.startswith("apps.inventory.internal")
        and not relativa(ruta).startswith("apps/inventory/")
    ]
    assert not infracciones, "\n".join(infracciones)


def test_ninguna_vista_ni_api_importa_el_cliente_http_de_meli() -> None:
    infracciones = [
        f"{relativa(ruta)} importa {modulo}"
        for ruta in archivos_de_aplicacion()
        if ruta.name in {"views.py", "api.py"}
        for modulo in modulos_importados(ruta)
        if modulo.startswith("apps.meli.client")
    ]
    assert not infracciones, "\n".join(infracciones)


def test_no_hay_imports_dentro_de_funciones() -> None:
    """Un import tardío suele tapar un ciclo. Única excepción: apps.py, por la carga de Django."""
    infracciones = []
    for ruta in archivos_de_aplicacion():
        if ruta.name in {"apps.py", "manage.py"}:
            continue
        for nodo in ast.walk(arbol(ruta)):
            if not isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for interno in ast.walk(nodo):
                if isinstance(interno, ast.Import | ast.ImportFrom):
                    infracciones.append(f"{relativa(ruta)}:{interno.lineno}")
    assert not infracciones, "\n".join(infracciones)

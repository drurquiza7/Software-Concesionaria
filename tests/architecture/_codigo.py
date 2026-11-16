"""Utilidades para inspeccionar el código fuente en los tests de arquitectura."""

import ast
from collections.abc import Iterator
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
APPS = ("core", "tenants", "accounts", "inventory", "media", "meli", "public_api")


def archivos_de_aplicacion(*carpetas: str) -> Iterator[Path]:
    """Archivos .py de producción: sin tests ni migraciones."""
    for carpeta in carpetas or ("apps", "config"):
        for ruta in sorted((RAIZ / carpeta).rglob("*.py")):
            partes = ruta.relative_to(RAIZ).parts
            if "tests" in partes or "migrations" in partes:
                continue
            yield ruta


def relativa(ruta: Path) -> str:
    return ruta.relative_to(RAIZ).as_posix()


def arbol(ruta: Path) -> ast.Module:
    return ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))


def modulos_importados(ruta: Path) -> set[str]:
    """Módulos importados por el archivo, con los imports relativos ya resueltos."""
    paquete = list(ruta.relative_to(RAIZ).with_suffix("").parts[:-1])
    importados: set[str] = set()
    for nodo in ast.walk(arbol(ruta)):
        if isinstance(nodo, ast.Import):
            importados.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            base = paquete[: len(paquete) - (nodo.level - 1)] if nodo.level else []
            modulo = ".".join([*base, *(nodo.module.split(".") if nodo.module else [])])
            importados.add(modulo)
            importados.update(f"{modulo}.{alias.name}" for alias in nodo.names)
    return importados

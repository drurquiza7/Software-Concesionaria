from collections.abc import Callable, Iterator

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

from apps.core.permissions import codigos

MARCAS = ("permiso_requerido", "es_publica", "requiere_sesion")


def _vistas(urlconf: str) -> Iterator[tuple[str, Callable]]:
    def recorrer(patrones: list, prefijo: str) -> Iterator[tuple[str, Callable]]:
        for patron in patrones:
            ruta = prefijo + str(patron.pattern)
            if isinstance(patron, URLResolver):
                yield from recorrer(patron.url_patterns, ruta)
            elif isinstance(patron, URLPattern):
                yield ruta, patron.callback

    yield from recorrer(get_resolver(urlconf).url_patterns, "/")


@pytest.mark.parametrize("urlconf", ["config.urls", "tests.urls_prueba"])
def test_toda_vista_declara_permiso_o_marca_explicita(urlconf: str) -> None:
    vistas = list(_vistas(urlconf))
    assert vistas
    sin_declarar = [ruta for ruta, vista in vistas if not any(hasattr(vista, m) for m in MARCAS)]
    assert not sin_declarar, f"Vistas sin permiso declarado: {sin_declarar}"


@pytest.mark.parametrize("urlconf", ["config.urls", "tests.urls_prueba"])
def test_los_permisos_declarados_existen_en_el_catalogo(urlconf: str) -> None:
    declarados = {
        vista.permiso_requerido
        for _, vista in _vistas(urlconf)
        if hasattr(vista, "permiso_requerido")
    }
    assert declarados <= codigos()


def test_las_vistas_publicas_son_las_esperadas() -> None:
    publicas = {ruta for ruta, vista in _vistas("config.urls") if hasattr(vista, "es_publica")}
    assert publicas == {"/healthz", "/", "/ingresar/"}

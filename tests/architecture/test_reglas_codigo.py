import ast
import re

from ._codigo import arbol, archivos_de_aplicacion, relativa

# CLAUDE.md 4.2: accesos que esquivan el manager filtrado por tenant.
PATRONES_PROHIBIDOS = {
    "_base_manager": re.compile(r"\b_base_manager\b"),
    "_default_manager": re.compile(r"\b_default_manager\b"),
    "raw()": re.compile(r"\.raw\("),
    "cursor.execute": re.compile(r"cursor\(\)|\.execute\("),
    "extra()": re.compile(r"\.extra\("),
}

USO_ALL_TENANTS = re.compile(r"\.all_tenants\b")
COMENTARIO_ALL_TENANTS = re.compile(r"#\s*all_tenants:\s*\S+")
USO_TENANT_CONTEXT = re.compile(r"\btenant_context\(")


def _puede_usar_all_tenants(ruta: str) -> bool:
    return (
        "/management/commands/" in ruta
        or ruta.endswith(("/tasks.py", "/admin.py"))
        # Excepción aprobada: login y selector de concesionaria (membresias_de_usuario).
        or ruta == "apps/accounts/selectors.py"
    )


def _puede_fijar_tenant(ruta: str) -> bool:
    return (
        ruta == "apps/core/context.py"
        or ruta == "apps/accounts/middleware.py"
        or ruta == "apps/public_api/auth.py"
        or ruta.endswith("/tasks.py")
        # Excepción aprobada: el alta de una concesionaria.
        or ruta == "apps/accounts/management/commands/crear_concesionaria.py"
    )


def test_no_se_usan_accesos_sin_filtro_de_tenant() -> None:
    infracciones = []
    for ruta in archivos_de_aplicacion():
        for numero, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), start=1):
            for nombre, patron in PATRONES_PROHIBIDOS.items():
                if patron.search(linea):
                    infracciones.append(f"{relativa(ruta)}:{numero} usa {nombre}")
    assert not infracciones, "\n".join(infracciones)


def test_all_tenants_solo_donde_esta_permitido_y_con_motivo() -> None:
    infracciones = []
    usos = 0
    for ruta in archivos_de_aplicacion():
        lineas = ruta.read_text(encoding="utf-8").splitlines()
        for indice, linea in enumerate(lineas):
            if not USO_ALL_TENANTS.search(linea.split("#")[0]):
                continue
            usos += 1
            lugar = f"{relativa(ruta)}:{indice + 1}"
            if not _puede_usar_all_tenants(relativa(ruta)):
                infracciones.append(f"{lugar} no puede usar all_tenants")
            anterior = lineas[indice - 1] if indice else ""
            if not (
                COMENTARIO_ALL_TENANTS.search(linea) or COMENTARIO_ALL_TENANTS.search(anterior)
            ):
                infracciones.append(f"{lugar} no explica el motivo con '# all_tenants: ...'")
    assert not infracciones, "\n".join(infracciones)
    assert usos == 1, "Un uso nuevo de all_tenants exige revisar este test a conciencia."


def test_el_tenant_activo_solo_se_fija_en_los_puntos_de_entrada() -> None:
    infracciones = [
        relativa(ruta)
        for ruta in archivos_de_aplicacion()
        if USO_TENANT_CONTEXT.search(ruta.read_text(encoding="utf-8"))
        and not _puede_fijar_tenant(relativa(ruta))
    ]
    assert not infracciones, "\n".join(infracciones)


def test_no_se_tragan_excepciones_genericas() -> None:
    infracciones = []
    for ruta in archivos_de_aplicacion():
        for nodo in ast.walk(arbol(ruta)):
            if not isinstance(nodo, ast.ExceptHandler):
                continue
            generica = nodo.type is None or (
                isinstance(nodo.type, ast.Name) and nodo.type.id in {"Exception", "BaseException"}
            )
            relanza = any(isinstance(interno, ast.Raise) for interno in ast.walk(nodo))
            solo_pass = all(isinstance(sentencia, ast.Pass) for sentencia in nodo.body)
            if (generica and not relanza) or solo_pass:
                infracciones.append(f"{relativa(ruta)}:{nodo.lineno}")
    assert not infracciones, "\n".join(infracciones)

"""Catálogo de topes por usuario y su uso en los routers (S3-W0-2; S3-D59, S3-D69, E2).

Reglas, por AST sobre `app/modules/*/router.py`:
- ningún router llama a `ratelimit.enforce` (ni a `enforce`) con `kind="user"`: el límite por
  usuario pasa siempre por `enforce_user_limit(request, bucket, user_id)`, que toma el tope de
  `app.state.user_limits` (E10);
- el bucket de cada `enforce_user_limit` es un literal que es clave de `USER_LIMITS` o el nombre
  `PII_SEARCH_BUCKET`; nunca una expresión;
- el conjunto de rutas que llaman a `enforce_user_limit` es exactamente `CON_LIMITE` (la misma
  constante de `test_error_codes_per_route.py`) menos las de `auth`, que usan `rate_limit` o
  el límite por cuenta;
- toda clave de `USER_LIMITS` tiene al menos una ruta, salvo las de `CLAVES_SIN_RUTA_TODAVIA`:
  cada slice que publica la ruta de un bucket la saca de ese conjunto en su Rojo (E2).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from app.core.ratelimit import PII_SEARCH_BUCKET, USER_LIMITS
from app.main import API_PREFIX
from tests.architecture.test_error_codes_per_route import CON_LIMITE

MODULES = Path(__file__).resolve().parents[2] / "src" / "app" / "modules"
METODOS = frozenset({"get", "post", "put", "patch", "delete"})
# Buckets del catálogo cuya ruta todavía no existe (E2: S3-B1 sacó `memberships-write` con la
# venta, S3-B4 `payments-write` con `POST /memberships/{membership_id}/payments` y S3-B5
# `admin-write` con `POST /payments/{payment_id}/void`, S3-B9b `members-detail` con
# `GET /members/{member_id}`; S3-B10 sacó los tres de `members-reveal` con
# `POST /members/{member_id}/reveal`). Desde B10 el catálogo entero tiene ruta.
# S4A-B3 (S4A-D65): `staff-read` nació en el catálogo sin ruta; S4A-B4 la sacó con `GET /audit` y
# `GET /audit/{seq}`. El catálogo entero vuelve a tener ruta.
CLAVES_SIN_RUTA_TODAVIA: frozenset[str] = frozenset()


def test_las_dos_ventanas_de_verificacion_viven_en_post_audit_verify() -> None:
    """S4A-D47 (M-3): minuto y hora se aplican en `POST /audit/verify`; `GET /audit/verify/last`
    no consume ninguna cubeta. S4A-D45 (S4A-B4): `GET /audit` y `GET /audit/{seq}` consumen
    `staff-read`."""
    fuente = (MODULES / "audit" / "router.py").read_text(encoding="utf-8")
    por_ruta: dict[tuple[str, str] | None, set[str]] = {}
    for funcion in ast.walk(ast.parse(fuente)):
        if isinstance(funcion, ast.AsyncFunctionDef | ast.FunctionDef):
            por_ruta.setdefault(_ruta_de(funcion), set()).update(
                nodo.args[1].value
                for nodo in ast.walk(funcion)
                if isinstance(nodo, ast.Call)
                and _nombre_llamado(nodo) == "enforce_user_limit"
                and isinstance(nodo.args[1], ast.Constant)
            )
    assert por_ruta[("post", f"{API_PREFIX}/audit/verify")] == {"audit-verify", "audit-verify-hour"}
    assert por_ruta[("get", f"{API_PREFIX}/audit/verify/last")] == set()
    # S4A-B4 (S4A-D45): la lista y el detalle consumen solo `staff-read`.
    assert por_ruta[("get", f"{API_PREFIX}/audit")] == {"staff-read"}
    assert por_ruta[("get", f"{API_PREFIX}/audit/{{seq}}")] == {"staff-read"}
    assert USER_LIMITS["audit-verify"] == (3, 60)
    # S4A-B5 (S4A-D20, S4A-D45): el historial del socio, en `members/router.py`, también.
    miembros = (MODULES / "members" / "router.py").read_text(encoding="utf-8")
    llamadas = [
        nodo.args[1].value
        for funcion in ast.walk(ast.parse(miembros))
        if isinstance(funcion, ast.AsyncFunctionDef | ast.FunctionDef)
        and _ruta_de(funcion) == ("get", f"{API_PREFIX}/members/{{member_id}}/audit")
        for nodo in ast.walk(funcion)
        if isinstance(nodo, ast.Call)
        and _nombre_llamado(nodo) == "enforce_user_limit"
        and isinstance(nodo.args[1], ast.Constant)
    ]
    assert llamadas == ["staff-read"]
    assert USER_LIMITS["audit-verify-hour"] == (20, 3600)
    assert USER_LIMITS["staff-read"] == (120, 60)


def test_las_tres_ventanas_de_reveal_viven_en_la_misma_ruta() -> None:
    """S3-D44 (M-1): minuto, hora y día se aplican en `POST /members/{member_id}/reveal`."""
    fuente = (MODULES / "members" / "router.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    funciones = [
        f
        for f in ast.walk(arbol)
        if isinstance(f, ast.AsyncFunctionDef)
        and _ruta_de(f) == ("post", f"{API_PREFIX}/members/{{member_id}}/reveal")
    ]
    assert len(funciones) == 1
    buckets = {
        nodo.args[1].value
        for nodo in ast.walk(funciones[0])
        if isinstance(nodo, ast.Call)
        and _nombre_llamado(nodo) == "enforce_user_limit"
        and isinstance(nodo.args[1], ast.Constant)
    }
    assert buckets == {"members-reveal", "members-reveal-hour", "members-reveal-day"}
    assert USER_LIMITS["members-reveal"] == (30, 60)
    assert USER_LIMITS["members-reveal-hour"] == (200, 3600)
    assert USER_LIMITS["members-reveal-day"] == (600, 86400)


@dataclass(frozen=True)
class Hallazgos:
    enforce_de_usuario: list[str]
    buckets_invalidos: list[str]
    rutas: set[tuple[str, str]]
    buckets: set[str]


def _nombre_llamado(nodo: ast.Call) -> str | None:
    if isinstance(nodo.func, ast.Name):
        return nodo.func.id
    if isinstance(nodo.func, ast.Attribute):
        return nodo.func.attr
    return None


def _ruta_de(funcion: ast.AsyncFunctionDef | ast.FunctionDef) -> tuple[str, str] | None:
    """`(método, ruta completa)` del decorador `@router.<método>("<ruta>")` de la función."""
    for decorador in funcion.decorator_list:
        if (
            isinstance(decorador, ast.Call)
            and isinstance(decorador.func, ast.Attribute)
            and decorador.func.attr in METODOS
            and decorador.args
            and isinstance(decorador.args[0], ast.Constant)
            and isinstance(decorador.args[0].value, str)
        ):
            return decorador.func.attr, API_PREFIX + decorador.args[0].value
    return None


def _bucket(argumento: ast.expr) -> str | None:
    if isinstance(argumento, ast.Constant) and isinstance(argumento.value, str):
        return argumento.value if argumento.value in USER_LIMITS else None
    nombre = argumento.id if isinstance(argumento, ast.Name) else None
    if isinstance(argumento, ast.Attribute):
        nombre = argumento.attr
    return PII_SEARCH_BUCKET if nombre == "PII_SEARCH_BUCKET" else None


def analizar(fuente: str, archivo: str) -> Hallazgos:
    arbol = ast.parse(fuente, filename=archivo)
    enforce_de_usuario: list[str] = []
    invalidos: list[str] = []
    rutas: set[tuple[str, str]] = set()
    buckets: set[str] = set()
    for funcion in ast.walk(arbol):
        if not isinstance(funcion, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        ruta = _ruta_de(funcion)
        for nodo in ast.walk(funcion):
            if not isinstance(nodo, ast.Call):
                continue
            llamado = _nombre_llamado(nodo)
            if llamado == "enforce" and any(
                k.arg == "kind" and isinstance(k.value, ast.Constant) and k.value.value == "user"
                for k in nodo.keywords
            ):
                enforce_de_usuario.append(f"{archivo}:{nodo.lineno}")
            if llamado != "enforce_user_limit":
                continue
            bucket = _bucket(nodo.args[1]) if len(nodo.args) >= 2 else None
            if bucket is None:
                invalidos.append(f"{archivo}:{nodo.lineno}")
            else:
                buckets.add(bucket)
            if ruta is not None:
                rutas.add(ruta)
    return Hallazgos(enforce_de_usuario, invalidos, rutas, buckets)


def _routers() -> Hallazgos:
    total = Hallazgos([], [], set(), set())
    for router in sorted(MODULES.glob("*/router.py")):
        parcial = analizar(router.read_text(encoding="utf-8"), router.parent.name + "/router.py")
        total.enforce_de_usuario.extend(parcial.enforce_de_usuario)
        total.buckets_invalidos.extend(parcial.buckets_invalidos)
        total.rutas.update(parcial.rutas)
        total.buckets.update(parcial.buckets)
    return total


def test_ningun_router_llama_a_enforce_con_kind_user() -> None:
    assert _routers().enforce_de_usuario == [], "usar ratelimit.enforce_user_limit"


def test_cada_bucket_de_enforce_user_limit_es_del_catalogo() -> None:
    assert _routers().buckets_invalidos == []


def test_las_rutas_con_enforce_user_limit_son_con_limite_menos_auth() -> None:
    esperadas = {
        (metodo, ruta) for metodo, ruta in CON_LIMITE if not ruta.startswith(f"{API_PREFIX}/auth/")
    }
    assert _routers().rutas == esperadas


def test_toda_clave_del_catalogo_tiene_ruta_salvo_las_pendientes() -> None:
    assert CLAVES_SIN_RUTA_TODAVIA <= set(USER_LIMITS)
    assert _routers().buckets == set(USER_LIMITS) - CLAVES_SIN_RUTA_TODAVIA


# Controles del analizador (fuentes falsas) ---------------------------------------------------

FUENTE_MALA = """
@router.post("/cosas")
async def crear(request, principal):
    await ratelimit.enforce("members-write", str(principal.user_id), limit=1, window_s=60,
                            kind="user")
    await enforce_user_limit(request, f"members-{x}", principal.user_id)
    await enforce_user_limit(request, "inventado", principal.user_id)
"""

FUENTE_BUENA = """
@router.get("/cosas")
async def listar(request, principal, q=None):
    if q:
        await ratelimit.enforce_user_limit(request, PII_SEARCH_BUCKET, principal.user_id)

@router.post("/cosas")
async def crear(request, principal):
    await enforce_user_limit(request, "members-write", principal.user_id)
    await ratelimit.enforce("login-account", "x", limit=1, window_s=60)
"""


def test_el_analizador_detecta_enforce_de_usuario_y_buckets_dinamicos_o_ajenos() -> None:
    hallazgos = analizar(FUENTE_MALA, "falso/router.py")
    assert len(hallazgos.enforce_de_usuario) == 1
    assert len(hallazgos.buckets_invalidos) == 2
    assert hallazgos.rutas == {("post", f"{API_PREFIX}/cosas")}


def test_el_analizador_acepta_literales_del_catalogo_y_pii_search_bucket() -> None:
    hallazgos = analizar(FUENTE_BUENA, "falso/router.py")
    assert hallazgos.enforce_de_usuario == [] and hallazgos.buckets_invalidos == []
    assert hallazgos.rutas == {("get", f"{API_PREFIX}/cosas"), ("post", f"{API_PREFIX}/cosas")}
    assert hallazgos.buckets == {"members-search", "members-write"}

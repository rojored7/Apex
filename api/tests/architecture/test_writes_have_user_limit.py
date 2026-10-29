"""Toda escritura autenticada tiene tope (M-A de la revisión de seguridad V10 del Sprint 3).

Reglas, por AST sobre `app/modules/*/router.py`:
- cada ruta `post`, `put`, `patch` o `delete` está en `CON_LIMITE` (la constante de
  `test_error_codes_per_route.py`, que exige el 429 en el OpenAPI y, con
  `test_user_limits_catalog.py`, la llamada a `enforce_user_limit` fuera de `/auth/`) o en
  `EXENTAS`, con su motivo escrito;
- `EXENTAS` solo admite escrituras públicas de `PUBLIC_ROUTES` y las tres de emergencia
  (`lock`, `unlock`, `revoke-sessions`): son la respuesta a un incidente y un tope las podría
  bloquear justo cuando hacen falta. Ya pasan por la auditoría y solo las llama un admin;
- `EXENTAS` no guarda rutas que ya no existen ni rutas que ya tienen tope.
Una escritura nueva sin tope rompe esta prueba en su Rojo: o se le pone `enforce_user_limit`
(y entra a `CON_LIMITE`) o se escribe aquí el motivo de la excepción.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.core.security import PUBLIC_ROUTES
from app.main import API_PREFIX
from tests.architecture.test_error_codes_per_route import CON_LIMITE
from tests.architecture.test_user_limits_catalog import MODULES, _ruta_de

ESCRITURAS = frozenset({"post", "put", "patch", "delete"})
EMERGENCIA: dict[tuple[str, str], str] = {
    ("post", f"{API_PREFIX}/users/{{user_id}}/lock"): (
        "bloquear una cuenta es la respuesta a un incidente; un tope no puede impedirlo"
    ),
    ("post", f"{API_PREFIX}/users/{{user_id}}/unlock"): (
        "desbloquear tras un incidente o un bloqueo automático; no debe esperar a una ventana"
    ),
    ("post", f"{API_PREFIX}/users/{{user_id}}/revoke-sessions"): (
        "cerrar las sesiones de una cuenta comprometida; no debe esperar a una ventana"
    ),
}
EXENTAS: dict[tuple[str, str], str] = dict(EMERGENCIA)
"""`{(método, ruta): motivo}` de las escrituras sin tope por usuario ni por IP."""


def escrituras(fuente: str, archivo: str) -> set[tuple[str, str]]:
    """`(método, ruta completa)` de cada función con decorador de escritura del router."""
    arbol = ast.parse(fuente, filename=archivo)
    rutas: set[tuple[str, str]] = set()
    for funcion in ast.walk(arbol):
        if isinstance(funcion, ast.AsyncFunctionDef | ast.FunctionDef):
            ruta = _ruta_de(funcion)
            if ruta is not None and ruta[0] in ESCRITURAS:
                rutas.add(ruta)
    return rutas


def _todas_las_escrituras() -> set[tuple[str, str]]:
    total: set[tuple[str, str]] = set()
    for router in sorted(MODULES.glob("*/router.py")):
        total |= escrituras(router.read_text(encoding="utf-8"), router.parent.name + "/router.py")
    return total


def _publicas() -> set[tuple[str, str]]:
    return {(metodo.lower(), ruta) for metodo, ruta in PUBLIC_ROUTES}


def test_toda_escritura_tiene_tope_o_motivo_de_excepcion() -> None:
    sin_tope = sorted(_todas_las_escrituras() - CON_LIMITE - set(EXENTAS))
    assert sin_tope == [], "agregar enforce_user_limit (y CON_LIMITE) o un motivo en EXENTAS"


def test_las_exentas_son_solo_publicas_o_de_emergencia() -> None:
    permitidas = _publicas() | set(EMERGENCIA)
    assert set(EXENTAS) <= permitidas
    assert all(motivo.strip() for motivo in EXENTAS.values())


def test_las_exentas_existen_y_no_tienen_tope() -> None:
    escritas = _todas_las_escrituras()
    assert set(EXENTAS) <= escritas, "EXENTAS guarda una ruta que ya no existe"
    assert set(EXENTAS) & CON_LIMITE == set(), "una ruta con tope no va en EXENTAS"


def test_las_escrituras_de_admin_de_v10_estan_en_con_limite() -> None:
    """M-A: las seis de `auth`, los cinco PATCH de settings y el alta de planes."""
    esperadas = {
        ("post", f"{API_PREFIX}/plans"),
        ("patch", f"{API_PREFIX}/settings/gym"),
        ("patch", f"{API_PREFIX}/settings/privacy"),
        ("patch", f"{API_PREFIX}/settings/memberships"),
        ("patch", f"{API_PREFIX}/settings/payment_methods"),
        ("patch", f"{API_PREFIX}/settings/{{section}}"),
        ("post", f"{API_PREFIX}/users"),
        ("post", f"{API_PREFIX}/users/{{user_id}}/resend-link"),
        ("patch", f"{API_PREFIX}/users/{{user_id}}"),
        ("delete", f"{API_PREFIX}/users/{{user_id}}"),
    }
    assert esperadas <= CON_LIMITE


def test_las_cuatro_escrituras_de_planes_de_b7_estan_en_con_limite_y_existen() -> None:
    """S4A-B7 (S4A-D26, C8): editar, activar, desactivar y dar de baja un plan tienen tope
    (`admin-write`); no van a `EXENTAS`."""
    plan = f"{API_PREFIX}/plans/{{plan_id}}"
    esperadas = {
        ("patch", plan),
        ("post", f"{plan}/activate"),
        ("post", f"{plan}/deactivate"),
        ("delete", plan),
    }
    assert esperadas <= CON_LIMITE
    assert esperadas <= _todas_las_escrituras()
    assert not esperadas & set(EXENTAS)


# Control del analizador (fuente falsa) -------------------------------------------------------

FUENTE = """
@router.get("/cosas")
async def listar(): ...

@router.post("/cosas")
async def crear(): ...

@router.delete("/cosas/{id}")
def borrar(): ...

async def ayuda(): ...
"""


def test_el_analizador_encuentra_solo_las_escrituras() -> None:
    assert escrituras(FUENTE, "falso/router.py") == {
        ("post", f"{API_PREFIX}/cosas"),
        ("delete", f"{API_PREFIX}/cosas/{{id}}"),
    }


def test_el_analizador_recorre_los_routers_reales() -> None:
    assert len(list(Path(MODULES).glob("*/router.py"))) >= 6
    assert ("post", f"{API_PREFIX}/members") in _todas_las_escrituras()

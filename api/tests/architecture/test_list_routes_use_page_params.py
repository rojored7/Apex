"""Toda lista `GET` pagina con `PageParams` y acepta `q` (US-019 T6, criterio 5; regla de datos
6; S2-D3 endurecida en S2-B3).

S2-D3: los routers son planos y FastAPI los incluye de forma perezosa, así que se recorren las
rutas EFECTIVAS de `create_app(...)` (`effective_routes`) y no `router.routes`. Para cada `GET`
publicado se lee su contrato en `app.openapi()`:
- una respuesta `Page_...` exige la dependencia `PageParams`, un parámetro de query `q` y
  `limit` con máximo 200 (`MAX_LIMIT`);
- ninguna respuesta 200 de un `GET` es un arreglo suelto (toda lista pagina en el servidor).
Los controles construyen apps desechables que deben fallar.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.models import Dependant
from pydantic import BaseModel

from app.core.config import Settings
from app.core.pagination import MAX_LIMIT, Page, PageParams, SearchQuery
from app.core.security import effective_routes
from app.main import create_app

SCHEMA_REF = "#/components/schemas/"
RUTAS_SIN_Q_S8: frozenset[str] = frozenset(
    {
        "GET /api/v1/wods/{wod_id}/leaderboard",
        "GET /api/v1/wods/{wod_id}/results",
        "GET /api/v1/members/{member_id}/results",
    }
)
"""S8-B4 (US-171 a US-173): el leaderboard y las dos listas de resultados paginan con `limit` y
`offset` y filtran por parámetros tipados (`level`, `sex`, `include_superseded`, `benchmark`): no
hay texto que buscar, así que no aceptan `q` (exclusión anotada)."""
SIN_Q: frozenset[str] = frozenset({"GET /api/v1/members/{member_id}/attachments"}) | RUTAS_SIN_Q_S8
"""S6-C2 (S6-D57): el listado de adjuntos de un socio pagina sin `q`; S8-B4 suma las tres
lecturas de resultados (exclusión anotada)."""


def _usa_page_params(dependant: Dependant) -> bool:
    return any(d.call is PageParams or _usa_page_params(d) for d in dependant.dependencies)


def _query_params(dependant: Dependant) -> set[str]:
    nombres = {p.alias or p.name for p in dependant.query_params}
    for dep in dependant.dependencies:
        nombres |= _query_params(dep)
    return nombres


def _respuesta_200(operacion: dict[str, Any]) -> dict[str, Any]:
    contenido = operacion.get("responses", {}).get("200", {}).get("content", {})
    schema: dict[str, Any] = contenido.get("application/json", {}).get("schema", {})
    return schema


def _limite_maximo(operacion: dict[str, Any]) -> Any:
    for parametro in operacion.get("parameters", []):
        if parametro.get("in") == "query" and parametro.get("name") == "limit":
            return parametro.get("schema", {}).get("maximum")
    return None


def problemas_de_listas(app: FastAPI) -> tuple[list[str], list[str]]:
    """`(problemas, listas)`: qué lista `GET` incumple y cuáles se revisaron."""
    esquema = app.openapi()
    problemas: list[str] = []
    listas: list[str] = []
    for ruta in effective_routes(app)[0]:
        if "GET" not in ruta.methods:
            continue
        operacion = esquema.get("paths", {}).get(ruta.path, {}).get("get")
        if operacion is None:
            continue
        respuesta = _respuesta_200(operacion)
        if respuesta.get("type") == "array":
            problemas.append(f"GET {ruta.path}: devuelve un arreglo sin paginar")
            continue
        ref = str(respuesta.get("$ref", ""))
        if not ref.removeprefix(SCHEMA_REF).startswith("Page_"):
            continue
        listas.append(f"GET {ruta.path}")
        if not _usa_page_params(ruta.dependant):
            problemas.append(f"GET {ruta.path}: sin PageParams")
        if "q" not in _query_params(ruta.dependant) and f"GET {ruta.path}" not in SIN_Q:
            problemas.append(f"GET {ruta.path}: sin q")
        if _limite_maximo(operacion) != MAX_LIMIT:
            problemas.append(f"GET {ruta.path}: limit sin máximo {MAX_LIMIT}")
    return problemas, listas


def test_las_listas_efectivas_de_la_app_paginan_y_aceptan_q(settings_prueba: Settings) -> None:
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    problemas, listas = problemas_de_listas(app)
    assert problemas == [], "\n".join(problemas)
    # S2-B3 publica la primera lista paginada (`GET /users`); el recorrido no puede quedar vacío.
    # S2-B8 agrega `GET /members` y S2-B9 `GET /plans`: las tres deben recogerse. S3-B7 agrega
    # `GET /memberships` (US-091) y S3-B8 `GET /payments` (US-098). S3-B11 (D28, condición 3)
    # agrega las dos listas anidadas de la ficha, con `PageParams` y `q` real.
    assert {
        "GET /api/v1/users",
        "GET /api/v1/members",
        "GET /api/v1/plans",
        "GET /api/v1/memberships",
        "GET /api/v1/payments",
        "GET /api/v1/members/{member_id}/memberships",
        "GET /api/v1/members/{member_id}/payments",
        # S5-B6 (US-120, US-121): las listas de plantillas y de reglas de aviso.
        "GET /api/v1/notification-templates",
        "GET /api/v1/notification-rules",
    } <= set(listas)


def test_las_listas_anidadas_de_la_ficha_paginan_y_aceptan_q(settings_prueba: Settings) -> None:
    """S3-B11 (D28): las pestañas de la ficha usan `Annotated[PageParams, Depends()]` y
    `q: SearchQuery` (hasta 100 caracteres, sin caracteres de control); la de pagos suma
    `voided`. `limit` declara 1..200 en el OpenAPI."""
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    esquema = app.openapi()
    rutas = {ruta.path: ruta for ruta in effective_routes(app)[0] if "GET" in ruta.methods}
    esperados = {
        "/api/v1/members/{member_id}/memberships": {"limit", "offset", "q"},
        "/api/v1/members/{member_id}/payments": {"limit", "offset", "q", "voided"},
    }
    for path, consulta in esperados.items():
        assert path in rutas, path
        assert _usa_page_params(rutas[path].dependant), path
        assert _query_params(rutas[path].dependant) == consulta, path
        operacion = esquema["paths"][path]["get"]
        parametros = {p["name"]: p for p in operacion["parameters"] if p["in"] == "query"}
        assert parametros["limit"]["schema"]["minimum"] == 1, path
        assert _limite_maximo(operacion) == MAX_LIMIT, path
        q = parametros["q"]["schema"]
        variantes = q.get("anyOf", [q])
        assert any(v.get("maxLength") == 100 for v in variantes), path


class _Out(BaseModel):
    x: int


def _app_de_control() -> FastAPI:
    router = APIRouter()

    @router.get("/sin", response_model=Page[_Out])
    async def sin(q: SearchQuery = None) -> Page[_Out]:
        return Page[_Out](items=[], total=0, limit=25, offset=0)

    @router.get("/sin-q", response_model=Page[_Out])
    async def sin_q(params: Annotated[PageParams, Depends()]) -> Page[_Out]:
        return Page[_Out](items=[], total=0, limit=params.limit, offset=params.offset)

    @router.get("/con", response_model=Page[_Out])
    async def con(params: Annotated[PageParams, Depends()], q: SearchQuery = None) -> Page[_Out]:
        return Page[_Out](items=[], total=0, limit=params.limit, offset=params.offset)

    @router.get("/arreglo", response_model=list[_Out])
    async def arreglo() -> list[_Out]:
        return []

    @router.get("/uno", response_model=_Out)
    async def uno() -> _Out:
        return _Out(x=1)

    app = FastAPI()
    padre = APIRouter(prefix="/api/v1")
    padre.include_router(router)  # incluido como los módulos: perezoso
    app.include_router(padre)
    return app


def test_el_control_detecta_listas_sin_page_params_sin_q_y_arreglos() -> None:
    problemas, listas = problemas_de_listas(_app_de_control())
    assert sorted(problemas) == [
        "GET /api/v1/arreglo: devuelve un arreglo sin paginar",
        "GET /api/v1/sin-q: sin q",
        "GET /api/v1/sin: limit sin máximo 200",
        "GET /api/v1/sin: sin PageParams",
    ]
    assert sorted(listas) == ["GET /api/v1/con", "GET /api/v1/sin", "GET /api/v1/sin-q"]


def test_los_medios_de_pago_son_un_objeto_con_items_que_no_pagina(
    settings_prueba: Settings,
) -> None:
    """S3-B3 (D25, condición 3 del impacto, S3-C7): `GET /payments/methods` responde
    `PaymentMethodsOut {items}`: no es un arreglo (que esta prueba rechaza) ni una `Page_...`
    (son tres medios fijos; no pagina ni acepta `q`). La regla clasifica como lista solo las
    respuestas `Page_...`, así que la ruta no entra en `listas` y no da problemas."""
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    problemas, listas = problemas_de_listas(app)
    assert problemas == []
    assert "GET /api/v1/payments/methods" not in listas
    operacion = app.openapi()["paths"]["/api/v1/payments/methods"]["get"]
    respuesta = _respuesta_200(operacion)
    assert respuesta == {"$ref": f"{SCHEMA_REF}PaymentMethodsOut"}


def test_las_exportaciones_csv_son_la_excepcion_nombrada_a_la_paginacion(
    settings_prueba: Settings,
) -> None:
    """S5-B12 (S5-D36, S5-D92; regla de datos 6): `GET /members/export` y `GET /payments/export`
    devuelven `text/csv` en streaming, no una `Page_...`: no paginan ni aceptan `limit` y `offset`,
    y el recorrido de listas no las toma por listas ni da problemas (Rojo B12)."""
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    problemas, listas = problemas_de_listas(app)
    assert problemas == []
    esquema = app.openapi()
    rutas = {r.path: r for r in effective_routes(app)[0] if "GET" in r.methods}
    for ruta in ("/api/v1/members/export", "/api/v1/payments/export"):
        assert f"GET {ruta}" not in listas
        assert "text/csv" in esquema["paths"][ruta]["get"]["responses"]["200"]["content"]
        assert not _usa_page_params(rutas[ruta].dependant)
        assert not {"limit", "offset"} & _query_params(rutas[ruta].dependant)


def test_s6_b1_el_inventario_de_llaves_pagina_y_filtra_por_data_class(
    settings_prueba: Settings,
) -> None:
    """S6-B1 (S6-D13): `GET /crypto/keys` responde un `Page` de llaves con `summary` (por eso su
    esquema no se llama `Page_...` y el recorrido genérico no lo toma por lista): se comprueba
    aquí, con `PageParams`, `q` (sobre `data_class`), los cuatro filtros, `limit` 1 a 200 y los
    cuatro campos de `Page` más `summary`."""
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    problemas, _ = problemas_de_listas(app)
    assert problemas == []
    esquema = app.openapi()
    ruta = next(
        r
        for r in effective_routes(app)[0]
        if r.path == "/api/v1/crypto/keys" and "GET" in r.methods
    )
    assert _usa_page_params(ruta.dependant)
    assert _query_params(ruta.dependant) == {
        "limit",
        "offset",
        "q",
        "purpose",
        "state",
        "provider",
        "data_class",
    }
    operacion = esquema["paths"]["/api/v1/crypto/keys"]["get"]
    assert _limite_maximo(operacion) == MAX_LIMIT
    parametros = {p["name"]: p for p in operacion["parameters"] if p["in"] == "query"}
    assert parametros["limit"]["schema"]["minimum"] == 1
    q = parametros["q"]["schema"]
    assert any(v.get("maxLength") == 100 for v in q.get("anyOf", [q]))
    nombre = _respuesta_200(operacion)["$ref"].removeprefix(SCHEMA_REF)
    propiedades = esquema["components"]["schemas"][nombre]["properties"]
    assert set(propiedades) == {"items", "total", "limit", "offset", "summary"}


def test_s6_b2_la_bitacora_y_los_trabajos_paginan_y_aceptan_q(settings_prueba: Settings) -> None:
    """S6-B2 (S6-D16): `GET /crypto/ops` y `GET /crypto/jobs` responden `Page_...` con
    `PageParams`, `q` de hasta 100 caracteres, `limit` 1 a 200 y los filtros de la historia."""
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    problemas, listas = problemas_de_listas(app)
    assert problemas == []
    assert {"GET /api/v1/crypto/ops", "GET /api/v1/crypto/jobs"} <= set(listas)
    esquema = app.openapi()
    esperados = {
        "/api/v1/crypto/ops": {
            "limit",
            "offset",
            "q",
            "from",
            "to",
            "verb",
            "data_class",
            "key_id",
            "user_id",
            "result",
            "batch_id",
        },
        "/api/v1/crypto/jobs": {"limit", "offset", "q", "status", "kind", "data_class"},
    }
    for ruta, parametros_esperados in esperados.items():
        efectiva = next(
            r for r in effective_routes(app)[0] if r.path == ruta and "GET" in r.methods
        )
        assert _usa_page_params(efectiva.dependant), ruta
        assert _query_params(efectiva.dependant) == parametros_esperados, ruta
        operacion = esquema["paths"][ruta]["get"]
        assert _limite_maximo(operacion) == MAX_LIMIT, ruta
        parametros = {p["name"]: p for p in operacion["parameters"] if p["in"] == "query"}
        assert parametros["limit"]["schema"]["minimum"] == 1, ruta
        q = parametros["q"]["schema"]
        assert any(v.get("maxLength") == 100 for v in q.get("anyOf", [q])), ruta
        propiedades = esquema["components"]["schemas"][
            _respuesta_200(operacion)["$ref"].removeprefix(SCHEMA_REF)
        ]["properties"]
        assert set(propiedades) == {"items", "total", "limit", "offset"}, ruta


def test_s6_b2_los_enums_de_los_filtros_salen_de_los_modelos(settings_prueba: Settings) -> None:
    """Bug 22 (S6-D16): `kind` solo admite `JOB_KINDS`, `status` `JOB_STATUSES`, `verb`
    `OP_VERBS` y `result` `OP_RESULTS`; el OpenAPI publica exactamente esas listas cerradas."""
    from app.core.crypto.models import JOB_KINDS, JOB_STATUSES, OP_RESULTS, OP_VERBS

    esquema = create_app(settings_prueba, run_migrations_on_startup=False).openapi()

    def enum_de(ruta: str, nombre: str) -> list[str]:
        operacion = esquema["paths"][ruta]["get"]
        parametro = next(p for p in operacion["parameters"] if p["name"] == nombre)
        sch = parametro["schema"]
        variante = next(v for v in sch.get("anyOf", [sch]) if "enum" in v or "$ref" in v)
        if "$ref" in variante:
            variante = esquema["components"]["schemas"][variante["$ref"].removeprefix(SCHEMA_REF)]
        return list(variante["enum"])

    assert JOB_KINDS == ("rotate", "reencrypt", "migrate_provider", "rewrap")
    assert enum_de("/api/v1/crypto/jobs", "kind") == list(JOB_KINDS)
    assert enum_de("/api/v1/crypto/jobs", "status") == list(JOB_STATUSES)
    assert enum_de("/api/v1/crypto/ops", "verb") == list(OP_VERBS)
    assert enum_de("/api/v1/crypto/ops", "result") == list(OP_RESULTS)


def test_s6_c2_el_listado_de_adjuntos_pagina_sin_q(settings_prueba: Settings) -> None:
    """S6-C2: `GET /members/{member_id}/attachments` usa `PageParams` (limit 1..200) y NO acepta
    `q`; la exclusión de `SIN_Q` es solo esa ruta."""
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    problemas, listas = problemas_de_listas(app)
    assert problemas == [], "\n".join(problemas)
    ruta_attachments = "/api/v1/members/{member_id}/attachments"
    assert f"GET {ruta_attachments}" in listas
    rutas = {r.path: r for r in effective_routes(app)[0] if "GET" in r.methods}
    assert _usa_page_params(rutas[ruta_attachments].dependant)
    assert _query_params(rutas[ruta_attachments].dependant) == {"limit", "offset"}
    assert _limite_maximo(app.openapi()["paths"][ruta_attachments]["get"]) == MAX_LIMIT
    assert SIN_Q == {f"GET {ruta_attachments}"} | RUTAS_SIN_Q_S8

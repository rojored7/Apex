"""Las filas de las listas de socios, membresías y pagos no declaran ningún campo sensible
(S2-B8; US-070 T9; N-01; ampliada en S3-B8 a `/api/v1/memberships` y `/api/v1/payments`, L-2).

Se recorren las rutas EFECTIVAS de `create_app(...)` (`effective_routes`, S2-D3) bajo
`/api/v1/members` y, para cada `GET` cuya respuesta 200 es un `Page_...`, se lee en
`app.openapi()` el esquema de la fila (`items`). Falla si la fila declara `document`, `phone`,
`email`, `birth_date`, `emergency_contact` o cualquier `*_idx` o `*_hint`: la lista no lleva
ningún dato cifrado, ni en claro, ni enmascarado, ni su índice ciego. El control construye una
app desechable con una fila falsa que debe fallar.

S3-B8: el mismo recorrido sobre `PREFIJOS_COMERCIALES` (`/api/v1/memberships` y
`/api/v1/payments`): `MembershipRow` y `PaymentRow` llevan solo nombre y apellido del socio (en
claro por regla) y `registered_by_name` (el correo PARCIAL de quien registró, L-2, S3-D57, que
no es un campo sensible: no se llama `email`); ninguna declara `document`, `phone`, `email`,
`birth_date`, `emergency_contact`, `*_idx`, `*_hint` ni un `*_email` con el correo completo.
"""

from __future__ import annotations

from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel

from app.core.config import Settings
from app.core.pagination import Page, PageParams, SearchQuery
from app.core.security import effective_routes
from app.main import create_app

PREFIJO = "/api/v1/members"
SCHEMA_REF = "#/components/schemas/"
SENSIBLES = frozenset({"document", "phone", "email", "birth_date", "emergency_contact"})
SUFIJOS_SENSIBLES = ("_idx", "_hint", "_email")
PREFIJOS_COMERCIALES = ("/api/v1/memberships", "/api/v1/payments")


def _resolver(esquema: dict[str, Any], nodo: dict[str, Any]) -> dict[str, Any]:
    ref = nodo.get("$ref")
    if ref is None:
        return nodo
    resuelto: dict[str, Any] = esquema["components"]["schemas"][str(ref).removeprefix(SCHEMA_REF)]
    return resuelto


def _fila_de_pagina(esquema: dict[str, Any], operacion: dict[str, Any]) -> dict[str, Any] | None:
    contenido = operacion.get("responses", {}).get("200", {}).get("content", {})
    respuesta = contenido.get("application/json", {}).get("schema", {})
    ref = str(respuesta.get("$ref", ""))
    if not ref.removeprefix(SCHEMA_REF).startswith("Page_"):
        return None
    pagina = _resolver(esquema, respuesta)
    items = pagina.get("properties", {}).get("items", {})
    return _resolver(esquema, items.get("items", {}))


def es_sensible(campo: str) -> bool:
    return campo in SENSIBLES or campo.endswith(SUFIJOS_SENSIBLES)


def filas_con_sensibles(app: FastAPI, prefijo: str = PREFIJO) -> tuple[list[str], list[str]]:
    """`(problemas, listas)`: qué fila de lista declara un campo sensible y qué listas se vieron."""
    esquema = app.openapi()
    problemas: list[str] = []
    listas: list[str] = []
    for ruta in effective_routes(app)[0]:
        if "GET" not in ruta.methods or not ruta.path.startswith(prefijo):
            continue
        operacion = esquema.get("paths", {}).get(ruta.path, {}).get("get")
        if operacion is None:
            continue
        fila = _fila_de_pagina(esquema, operacion)
        if fila is None:
            continue
        listas.append(f"GET {ruta.path}")
        for campo in sorted(fila.get("properties", {})):
            if es_sensible(campo):
                problemas.append(f"GET {ruta.path}: la fila declara {campo}")
    return problemas, listas


def test_las_filas_de_las_listas_de_socios_no_declaran_campos_sensibles(
    settings_prueba: Settings,
) -> None:
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    problemas, listas = filas_con_sensibles(app)
    assert problemas == [], "\n".join(problemas)
    # El recorrido no puede quedar vacío: `GET /members` es la lista de US-070.
    assert "GET /api/v1/members" in listas


def test_el_historial_del_socio_se_barre_y_no_lleva_correo(settings_prueba: Settings) -> None:
    """S4A-B5 (S4A-D20, S4A-D54): `GET /members/{member_id}/audit` es una lista bajo `/members`;
    el recorrido la ve y `MemberHistoryItem` no declara `user_email` ni otro sufijo sensible."""
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    problemas, listas = filas_con_sensibles(app)
    assert problemas == [], "\n".join(problemas)
    assert "GET /api/v1/members/{member_id}/audit" in listas
    fila = app.openapi()["components"]["schemas"]["MemberHistoryItem"]["properties"]
    assert "user_email" not in fila
    assert {"user_name", "fields", "purpose"} <= set(fila)


@pytest.mark.parametrize(
    ("prefijo", "lista"),
    [
        ("/api/v1/memberships", "GET /api/v1/memberships"),
        ("/api/v1/payments", "GET /api/v1/payments"),
    ],
)
def test_las_filas_de_membresias_y_pagos_no_declaran_campos_sensibles(
    settings_prueba: Settings, prefijo: str, lista: str
) -> None:
    app = create_app(settings_prueba, run_migrations_on_startup=False)
    problemas, listas = filas_con_sensibles(app, prefijo)
    assert problemas == [], "\n".join(problemas)
    assert lista in listas


def test_la_fila_de_pagos_lleva_el_correo_parcial_y_no_el_completo(
    settings_prueba: Settings,
) -> None:
    """L-2 (S3-D57): `registered_by_name` sí; ningún campo con el correo completo."""
    esquema = create_app(settings_prueba, run_migrations_on_startup=False).openapi()
    fila = esquema["components"]["schemas"]["PaymentRow"]["properties"]
    assert "registered_by_name" in fila
    assert not [campo for campo in fila if "email" in campo]


def test_la_fila_de_socios_lleva_el_fin_de_la_membresia_y_nada_sensible(
    settings_prueba: Settings,
) -> None:
    """S3-B9b (D22, D35): `MemberRowOut` gana `membership_end_date` (dato comercial en claro)."""
    esquema = create_app(settings_prueba, run_migrations_on_startup=False).openapi()
    fila = esquema["components"]["schemas"]["MemberRowOut"]["properties"]
    assert {"membership_status", "plan_name", "membership_end_date"} <= set(fila)
    assert not [campo for campo in fila if es_sensible(campo)]


def test_es_sensible_reconoce_campos_cifrados_indices_y_pistas() -> None:
    for campo in ("document", "phone", "email", "birth_date", "emergency_contact"):
        assert es_sensible(campo), campo
    for campo in (
        "document_idx",
        "phone_idx",
        "email_idx",
        "phone_hint",
        "document_hint",
        "registered_by_email",
    ):
        assert es_sensible(campo), campo
    for campo in (
        "id",
        "first_name",
        "last_name",
        "sex",
        "status",
        "deleted_at",
        "plan_name",
        "membership_end_date",
        "member_first_name",
        "registered_by_name",
        "voided_by_name",
    ):
        assert not es_sensible(campo), campo


class _FilaFalsa(BaseModel):
    id: int
    first_name: str
    document: str
    phone_idx: str
    email_hint: str


class _FilaLimpia(BaseModel):
    id: int
    first_name: str


def _app_de_control() -> FastAPI:
    router = APIRouter()

    @router.get("/members/falsa", response_model=Page[_FilaFalsa])
    async def falsa(
        params: Annotated[PageParams, Depends()], q: SearchQuery = None
    ) -> Page[_FilaFalsa]:
        return Page[_FilaFalsa](items=[], total=0, limit=params.limit, offset=params.offset)

    @router.get("/members/limpia", response_model=Page[_FilaLimpia])
    async def limpia(
        params: Annotated[PageParams, Depends()], q: SearchQuery = None
    ) -> Page[_FilaLimpia]:
        return Page[_FilaLimpia](items=[], total=0, limit=params.limit, offset=params.offset)

    @router.get("/members/uno", response_model=_FilaFalsa)
    async def uno() -> _FilaFalsa:  # detalle, no lista: no se revisa aquí
        return _FilaFalsa(id=1, first_name="a", document="x", phone_idx="y", email_hint="z")

    @router.get("/plans/falsa", response_model=Page[_FilaFalsa])
    async def fuera(params: Annotated[PageParams, Depends()]) -> Page[_FilaFalsa]:
        return Page[_FilaFalsa](items=[], total=0, limit=params.limit, offset=params.offset)

    app = FastAPI()
    padre = APIRouter(prefix="/api/v1")
    padre.include_router(router)  # incluido como los módulos: perezoso
    app.include_router(padre)
    return app


def test_el_control_detecta_una_fila_falsa_con_campos_sensibles() -> None:
    problemas, listas = filas_con_sensibles(_app_de_control())
    assert sorted(problemas) == [
        "GET /api/v1/members/falsa: la fila declara document",
        "GET /api/v1/members/falsa: la fila declara email_hint",
        "GET /api/v1/members/falsa: la fila declara phone_idx",
    ]
    assert sorted(listas) == ["GET /api/v1/members/falsa", "GET /api/v1/members/limpia"]

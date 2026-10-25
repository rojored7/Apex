"""`GET /api/v1/members` con `membership_status` y `plan_id` por HTTP (S3-B9b; US-071 criterios
1 a 8; D22, D27, E2, N-20).

- 422 `validation_error` con `field="membership_status"` para un estado desconocido
  (`"moroso"`, `"ACTIVE"`, `"cancelled"`) y con `field="plan_id"` para un id que no es UUID; el
  mensaje no repite el valor;
- un `plan_id` inexistente da 200 con la página vacía;
- admin y coach filtran; el coach con `status=deleted` recibe 200 con los dados de baja y su
  estado (N-20); `member` 403 y sin token 401 también con los filtros nuevos;
- cada fila con membresía trae `membership_status`, `plan_name` y `membership_end_date` (ISO); la
  fila sin membresía, `none` y los dos nulos; las claves son exactamente `CAMPOS_FILA` (N-01);
- `membership_status` y `plan_id` sin `q` no consumen la cubeta de búsquedas;
- OpenAPI (D27, E2): `POST /members`, `GET /members` y `GET /members/{member_id}` declaran 429
  por ruta y el `APIRouter` de `members` ya no lo declara; las demás operaciones bajo
  `/api/v1/members` (las de otros módulos) no declaran 429 salvo las de `CON_LIMITE`;
  `GET /members` declara los parámetros `membership_status` (con sus seis valores) y `plan_id`
  (`uuid`).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.crypto.keyring import Keyring
from app.main import create_app
from app.modules.members.router import router as members_router
from tests.architecture.test_error_codes_per_route import CON_LIMITE
from tests.conftest import T0, Cabeceras, CrearUsuario
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.members._apoyo import CAMPOS_FILA, MEMBERS

LIMITE_DE_BUSQUEDAS = 60


async def _escenario(session: AsyncSession) -> dict[str, Any]:
    """Un socio al día (Mensual), uno sin membresía y uno dado de baja con una vigente."""
    mensual = await make_plan(session, name="Mensual")

    async def socio(nombre: str, **cambios: Any) -> Any:
        return await make_member(
            session,
            first_name=nombre,
            last_name="Http",
            document=unique_document(),
            phone=None,
            email=None,
            **cambios,
        )

    al_dia = await socio("AlDia")
    await make_membership(
        session, al_dia, mensual, status="active", start=date(2026, 10, 1), end=date(2026, 11, 30)
    )
    sin = await socio("Sin")
    baja = await socio("Baja", deleted_at=T0 - timedelta(days=1))
    await make_membership(
        session, baja, mensual, status="active", start=date(2026, 10, 1), end=date(2026, 11, 30)
    )
    return {
        "plan": str(mensual.id),
        "al_dia": str(al_dia.id),
        "sin": str(sin.id),
        "baja": str(baja.id),
    }


@pytest.mark.parametrize(
    ("query", "campo"),
    [
        ("membership_status=moroso", "membership_status"),
        ("membership_status=ACTIVE", "membership_status"),
        ("membership_status=cancelled", "membership_status"),
        ("membership_status=", "membership_status"),
        ("plan_id=no-es-uuid", "plan_id"),
        ("plan_id=123", "plan_id"),
    ],
    ids=["moroso", "mayusculas", "cancelled", "vacio", "plan-texto", "plan-numero"],
)
async def test_filtros_invalidos_dan_422_con_el_campo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    query: str,
    campo: str,
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(f"{MEMBERS}?{query}", headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", campo)
    assert "moroso" not in error["message"] and "no-es-uuid" not in error["message"]


async def test_un_plan_inexistente_da_200_con_la_pagina_vacia(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    await _escenario(session)
    admin = await usuario_real("admin")
    r = await app_http.get(MEMBERS, params={"plan_id": str(uuid4())}, headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert r.json()["items"] == [] and r.json()["total"] == 0


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_filtran_y_las_filas_traen_plan_y_fin(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    rol: str,
) -> None:
    escenario = await _escenario(session)
    quien = await usuario_real(rol)
    r = await app_http.get(
        MEMBERS,
        params={"membership_status": "active", "plan_id": escenario["plan"]},
        headers=cabeceras(quien),
    )
    assert r.status_code == 200, r.text
    filas = r.json()["items"]
    assert [f["id"] for f in filas] == [escenario["al_dia"]]
    assert set(filas[0]) == CAMPOS_FILA
    assert (
        filas[0]["membership_status"],
        filas[0]["plan_name"],
        filas[0]["membership_end_date"],
    ) == ("active", "Mensual", "2026-11-30")


async def test_sin_filtros_cada_fila_con_membresia_trae_plan_y_la_otra_none(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    escenario = await _escenario(session)
    coach = await usuario_real("coach")
    r = await app_http.get(MEMBERS, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    filas = {f["id"]: f for f in r.json()["items"]}
    assert set(filas) == {escenario["al_dia"], escenario["sin"]}
    assert filas[escenario["al_dia"]]["plan_name"] == "Mensual"
    assert filas[escenario["al_dia"]]["membership_end_date"] == "2026-11-30"
    sin = filas[escenario["sin"]]
    assert (sin["membership_status"], sin["plan_name"], sin["membership_end_date"]) == (
        "none",
        None,
        None,
    )


async def test_el_coach_ve_a_los_dados_de_baja_con_su_estado(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    """N-20: el chip "Dados de baja" es para admin y coach."""
    escenario = await _escenario(session)
    coach = await usuario_real("coach")
    r = await app_http.get(
        MEMBERS,
        params={"status": "deleted", "membership_status": "active"},
        headers=cabeceras(coach),
    )
    assert r.status_code == 200, r.text
    filas = r.json()["items"]
    assert [f["id"] for f in filas] == [escenario["baja"]]
    assert filas[0]["deleted_at"] is not None
    assert (filas[0]["membership_status"], filas[0]["plan_name"]) == ("active", "Mensual")


async def test_member_403_y_sin_token_401_con_los_filtros(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    params = {"membership_status": "active", "plan_id": str(uuid4())}
    r = await app_http.get(MEMBERS, params=params, headers=cabeceras(socio))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    r = await app_http.get(MEMBERS, params=params)
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"


async def test_los_filtros_sin_q_no_consumen_la_cubeta_de_busquedas(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    for numero in range(LIMITE_DE_BUSQUEDAS + 1):
        r = await app_http.get(
            MEMBERS, params={"membership_status": "none"}, headers=cabeceras(coach)
        )
        assert r.status_code == 200, (numero, r.text)
    r = await app_http.get(MEMBERS, params={"q": "ruiz"}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text


# OpenAPI: 429 por ruta (D27, E2) y parámetros nuevos ---------------------------------------


@pytest.fixture
def esquema(settings_prueba: Settings) -> dict[str, Any]:
    return create_app(settings_prueba, run_migrations_on_startup=False).openapi()


def test_el_router_de_members_no_declara_429() -> None:
    assert 429 not in members_router.responses
    assert {401, 403} <= set(members_router.responses)


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [
        ("post", "/api/v1/members"),
        ("get", "/api/v1/members"),
        ("get", "/api/v1/members/{member_id}"),
    ],
)
def test_las_tres_rutas_de_members_con_limite_declaran_429(
    esquema: dict[str, Any], metodo: str, ruta: str
) -> None:
    assert "429" in esquema["paths"][ruta][metodo]["responses"]
    assert (metodo, ruta) in CON_LIMITE


def test_las_demas_operaciones_bajo_members_no_declaran_429(esquema: dict[str, Any]) -> None:
    for ruta, operaciones in esquema["paths"].items():
        if not ruta.startswith("/api/v1/members"):
            continue
        for metodo, operacion in operaciones.items():
            declara = "429" in operacion["responses"]
            assert declara == ((metodo, ruta) in CON_LIMITE), (metodo, ruta)


def test_get_members_declara_membership_status_y_plan_id(esquema: dict[str, Any]) -> None:
    parametros = {p["name"]: p for p in esquema["paths"]["/api/v1/members"]["get"]["parameters"]}
    assert {"membership_status", "plan_id", "q", "status", "sort", "limit", "offset"} <= set(
        parametros
    )
    texto = str(parametros["membership_status"]["schema"])
    for estado in ("active", "expiring", "expired", "frozen", "pending_payment", "none"):
        assert estado in texto, estado
    assert "uuid" in str(parametros["plan_id"]["schema"])


def test_la_fila_de_la_lista_declara_membership_end_date_como_fecha(
    esquema: dict[str, Any],
) -> None:
    fila = esquema["components"]["schemas"]["MemberRowOut"]["properties"]
    assert set(fila) == CAMPOS_FILA
    assert "date" in str(fila["membership_end_date"])

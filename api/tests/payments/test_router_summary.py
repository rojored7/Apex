"""`GET /api/v1/payments/summary` por HTTP (S3-B8, US-100; D23, D27, M-4, S3-D47).

- admin y coach: 200 `PaymentsSummary` (claves exactas, `by_method` con las tres claves fijas),
  todo entero salvo `month`, y `Cache-Control: no-store`;
- sin `month`, el mes de Bogotá del reloj de `api_prueba` (2026-10-21: `2026-10`);
- 422 `validation_error` con `field="month"`: `2026-13`, `9999-12`, `0000-01`, `2026-1` y uno de
  más de 7 caracteres; el mensaje no repite el valor;
- `member` 403 `forbidden`; sin token 401 `unauthorized`;
- OpenAPI: un solo parámetro (`month`, en la consulta), 422 declarado y sin 404 ni 429.

Datos: efectivo 300.000 (2026-10-05T15:00Z) y Nequi 120.000 anulado (2026-10-12T15:00Z):
`total_cop` 300.000, `voided_count` 1, `payments_count` 1.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.main import create_app
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_member
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.payments._apoyo import CAMPOS_POR_MEDIO, CAMPOS_RESUMEN, RESUMEN

RUTA_RESUMEN = "/api/v1/payments/summary"


async def _datos(session: AsyncSession) -> None:
    plan = await make_plan(session)
    socio = await make_member(session)
    membresia = await make_membership(session, socio, plan, status="active")
    await make_payment(
        session, membresia, amount=300_000, paid_at=datetime(2026, 10, 5, 15, tzinfo=UTC)
    )
    await make_payment(
        session,
        membresia,
        amount=120_000,
        method="nequi",
        paid_at=datetime(2026, 10, 12, 15, tzinfo=UTC),
        voided=True,
    )


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_reciben_el_resumen_del_mes(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    rol: str,
) -> None:
    await _datos(session)
    quien = await usuario_real(rol)
    r = await app_http.get(RESUMEN, params={"month": "2026-10"}, headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    assert "no-store" in r.headers.get("cache-control", "")
    datos = r.json()
    assert set(datos) == CAMPOS_RESUMEN
    assert set(datos["by_method"]) == CAMPOS_POR_MEDIO
    assert datos == {
        "month": "2026-10",
        "total_cop": 300_000,
        "by_method": {"cash": 300_000, "nequi": 0, "breb": 0},
        "voided_count": 1,
        "payments_count": 1,
    }
    enteros = [datos["total_cop"], datos["voided_count"], datos["payments_count"]]
    assert all(type(v) is int for v in [*enteros, *datos["by_method"].values()])


async def test_sin_month_usa_el_mes_actual_de_bogota(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    await _datos(session)
    coach = await usuario_real("coach")
    r = await app_http.get(RESUMEN, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert (r.json()["month"], r.json()["total_cop"]) == ("2026-10", 300_000)


@pytest.mark.parametrize("mes", ["2026-13", "9999-12", "0000-01", "2026-1", "2026-10-01"])
async def test_un_mes_invalido_da_422_en_month(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, mes: str
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(RESUMEN, params={"month": mes}, headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", "month")
    assert mes not in error["message"]


async def test_member_recibe_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio = await usuario_real("member")
    r = await app_http.get(RESUMEN, headers=cabeceras(socio))
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    sin_token = await app_http.get(RESUMEN)
    assert sin_token.status_code == 401
    assert sin_token.json()["error"]["code"] == "unauthorized"


def test_el_openapi_del_resumen_declara_month_y_422_sin_404_ni_429(
    settings_prueba: Settings,
) -> None:
    operacion = create_app(settings_prueba, run_migrations_on_startup=False).openapi()["paths"][
        RUTA_RESUMEN
    ]["get"]
    assert [(p["name"], p["in"]) for p in operacion["parameters"]] == [("month", "query")]
    assert {"200", "401", "403", "422"} <= set(operacion["responses"])
    assert not {"404", "429"} & set(operacion["responses"])
    ref = operacion["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/PaymentsSummary")

"""`GET /payments/export` y `payments.service.export_payments` (S5-B12, US-139; S5-D41, S5-D42,
S5-D60, S5-D82). Rojo B12.

Hoy es 2026-10-21 (`reloj`). El mes de octubre en Bogotá (UTC-5) es `[2026-10-01T05:00Z,
2026-11-01T05:00Z)`; el rango pedido es `from=2026-10-01T00:00:00-05:00` y
`to=2026-11-01T00:00:00-05:00`. Escenario a mano, de Lucía Gómez (plan Mensual) salvo P8:
- P1 2026-10-01T04:59:59Z efectivo 20.000: 30 de septiembre en Bogotá, FUERA.
- P2 2026-10-01T05:00:00Z Bre-B 10.000: 2026-10-01 00:00, DENTRO.
- P3 2026-10-05T15:00Z efectivo 300.000, referencia `EF-001`: 2026-10-05 10:00.
- P4 2026-10-10T15:00Z Nequi 240.000, referencia `=HYPERLINK("x")` (se escapa).
- P5 2026-10-12T15:00Z Nequi 120.000 ANULADO, motivo `-error de digitación` (se escapa).
- P6 2026-11-01T03:00Z efectivo 50.000, referencia `+57 ref`: 2026-10-31 22:00 (cruza la medianoche
  UTC y sigue en octubre en Bogotá).
- P7 2026-11-01T05:00:00Z Nequi 70.000: 1 de noviembre, FUERA.
- P8 2026-10-20T15:00Z efectivo 5.000 de `=Hack` Test: socio `'=Hack Test`.
Registró la coach `laura.cajera@test.apex` (`l•••@test.apex`).

Cuadre (S5-D42): no anulados del CSV = P2 + P3 + P4 + P8 + P6 = 10.000 + 300.000 + 240.000 +
5.000 + 50.000 = 605.000 en 5 pagos; `summary("2026-10")` da `total_cop` 605.000, `payments_count` 5
y `voided_count` 1.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring, configure_keyring
from app.core.export import single_flight
from app.core.security import effective_routes
from app.modules.memberships.models import Membership
from app.modules.payments import exports, service
from app.modules.payments.schemas import PaymentExportQuery
from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.core._export_apoyo import (
    filas_export,
    ops_export,
    parsear,
    sesion_propia,
)
from tests.factories.members import KNOWN, make_member
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.payments._apoyo import PAYMENTS

RUTA = f"{PAYMENTS}/export"
TABLA = "payments.payments"
DESDE = "2026-10-01T00:00:00-05:00"
HASTA = "2026-11-01T00:00:00-05:00"
CABECERA = [
    "fecha",
    "socio",
    "plan",
    "monto",
    "medio",
    "referencia",
    "registrado_por",
    "anulado",
    "motivo_anulacion",
]
REGISTRO = "l•••@test.apex"
LUCIA = "Lucía Gómez"


def _fila(
    fecha: str,
    monto: str,
    medio: str,
    referencia: str = "",
    anulado: str = "no",
    motivo: str = "",
    socio: str = LUCIA,
) -> list[str]:
    return [fecha, socio, "Mensual", monto, medio, referencia, REGISTRO, anulado, motivo]


P2 = _fila("2026-10-01 00:00", "10000", "Bre-B")
P3 = _fila("2026-10-05 10:00", "300000", "Efectivo", "EF-001")
P4 = _fila("2026-10-10 10:00", "240000", "Nequi", '\'=HYPERLINK("x")')
P5 = _fila("2026-10-12 10:00", "120000", "Nequi", "", "si", "'-error de digitación")
P8 = _fila("2026-10-20 10:00", "5000", "Efectivo", socio="'=Hack Test")
P6 = _fila("2026-10-31 22:00", "50000", "Efectivo", "'+57 ref")
OCTUBRE = [P2, P3, P4, P5, P8, P6]  # orden ascendente de (paid_at, id)


def _utc(mes: int, dia: int, hora: int, minuto: int = 0, segundo: int = 0) -> datetime:
    return datetime(2026, mes, dia, hora, minuto, segundo, tzinfo=UTC)


@pytest.fixture
async def escenario(
    session: AsyncSession, usuario_real: CrearUsuario, bus_listo: Keyring, reloj: FrozenClock
) -> dict[str, UUID]:
    coach = await usuario_real("coach", email="laura.cajera@test.apex")
    plan = await make_plan(session, name="Mensual")
    lucia = await make_member(session)
    hack = await make_member(
        session, first_name="=Hack", last_name="Test", document="9090", phone=None, email=None
    )
    ml = await make_membership(session, lucia, plan, status="active")
    mh = await make_membership(session, hack, plan, status="active")
    datos: list[tuple[Any, datetime, int, str, str | None, bool, str | None]] = [
        (ml, _utc(10, 1, 4, 59, 59), 20_000, "cash", None, False, None),
        (ml, _utc(10, 1, 5), 10_000, "breb", None, False, None),
        (ml, _utc(10, 5, 15), 300_000, "cash", "EF-001", False, None),
        (ml, _utc(10, 10, 15), 240_000, "nequi", '=HYPERLINK("x")', False, None),
        (ml, _utc(10, 12, 15), 120_000, "nequi", None, True, "-error de digitación"),
        (ml, _utc(11, 1, 3), 50_000, "cash", "+57 ref", False, None),
        (ml, _utc(11, 1, 5), 70_000, "nequi", None, False, None),
        (mh, _utc(10, 20, 15), 5_000, "cash", None, False, None),
    ]
    for membresia, cuando, monto, medio, ref, anulado, motivo in datos:
        await make_payment(
            session,
            membresia,
            amount=monto,
            method=medio,
            paid_at=cuando,
            reference=ref,
            registered_by=coach.id,
            voided=anulado,
            void_reason=motivo,
        )
    return {"coach": coach.id}


async def _pedir(
    cliente: AsyncClient, quien: UsuarioPrueba, cabeceras: Cabeceras, **extra: str
) -> Response:
    params = {"from": DESDE, "to": HASTA, **extra}
    return await cliente.get(RUTA, params=params, headers=cabeceras(quien))


# Contenido y cuadre -----------------------------------------------------------------------------


async def test_admin_descarga_el_csv_del_mes_con_las_nueve_columnas_de_n29(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
    assert r.headers["content-disposition"] == "attachment; filename=pagos-20261021.csv"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    cabecera, filas = parsear(r.content)
    assert cabecera == CABECERA
    assert filas == OCTUBRE


async def test_la_suma_y_el_conteo_de_los_no_anulados_cuadran_con_summary_cruzando_medianoche(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 200, r.text
    vigentes = [fila for fila in parsear(r.content)[1] if fila[7] == "no"]
    assert sum(int(fila[3]) for fila in vigentes) == 605_000  # a mano: ver el docstring
    assert len(vigentes) == 5
    resumen = await service.summary(session, month="2026-10")
    assert (resumen.total_cop, resumen.payments_count, resumen.voided_count) == (605_000, 5, 1)
    assert sum(int(fila[3]) for fila in vigentes) == resumen.total_cop
    assert len(vigentes) == resumen.payments_count
    montos = {fila[3] for fila in vigentes}
    assert "20000" not in montos and "70000" not in montos  # P1 y P7 caen fuera de octubre
    assert P6 in vigentes  # 2026-11-01T03:00Z sigue siendo el 31 de octubre en Bogotá


async def test_los_anulados_salen_con_anulado_si_y_su_motivo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras, voided="true")
        sin = await _pedir(app_http, admin, cabeceras, voided="false")
    assert parsear(r.content)[1] == [P5]
    assert P5 not in parsear(sin.content)[1] and len(parsear(sin.content)[1]) == 5


async def test_el_filtro_por_medio_es_el_de_la_lista(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras, method="nequi")
    assert parsear(r.content)[1] == [P4, P5]


async def test_los_textos_libres_con_disparador_salen_con_apostrofo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    """`referencia` (`=HYPERLINK`, `+57`), `motivo_anulacion` (`-`) y el nombre del socio (`=`)
    pasan por `escape_formula`; el monto es entero y no se escapa."""
    admin = await usuario_real("admin")
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras)
    filas = parsear(r.content)[1]
    assert [f[5] for f in filas] == ["", "EF-001", '\'=HYPERLINK("x")', "", "", "'+57 ref"]
    assert filas[3][8] == "'-error de digitación"
    assert filas[4][1] == "'=Hack Test"
    assert all(not f[3].startswith("'") for f in filas)


async def test_el_csv_no_trae_documento_telefono_ni_correo_del_socio(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras)
    for valor in (KNOWN["document"], "300 765 4321", "Correo.co", "correo.co"):
        assert valor not in r.text


# Validación ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "campo"),
    [
        ({"to": HASTA}, "from"),
        ({"from": DESDE}, "to"),
        ({"from": "2026-13-01", "to": HASTA}, "from"),
        ({"from": "no-es-fecha", "to": HASTA}, "from"),
        ({"from": HASTA, "to": DESDE}, "to"),
        ({"from": "2024-10-01T00:00:00-05:00", "to": "2026-11-01T00:00:00-05:00"}, "to"),
    ],
)
async def test_rangos_invalidos_dan_422_con_field(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    params: dict[str, str],
    campo: str,
) -> None:
    """Falta `from` o `to`, fecha mal formada, invertido y más de 12 meses (dos años)."""
    admin = await usuario_real("admin")
    r = await app_http.get(RUTA, params=params, headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.headers["content-type"].startswith("application/json")
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", campo)
    assert await filas_export(session, TABLA) == []


# Sin bus, lotes y auditoría -------------------------------------------------------------------


async def test_no_usa_el_bus_y_funciona_con_el_custodio_sellado(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    antes = await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops"))
    configure_keyring(None)
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 200, r.text
    assert parsear(r.content)[1] == OCTUBRE
    assert await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops")) == antes
    assert await ops_export(session) == []


async def test_los_lotes_siguen_la_llave_paid_at_id_y_no_pierden_empates(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cinco pagos con el MISMO `paid_at` y lote de 2: salen todos, una vez, ordenados por id."""
    monkeypatch.setattr(exports, "BATCH_SIZE", 2)
    admin = await usuario_real("admin")
    plan = await make_plan(session, name="Mensual")
    membresia = await make_membership(session, await make_member(session), plan, status="active")
    ids: dict[str, UUID] = {}
    for n in range(1, 6):
        pago = await make_payment(
            session, membresia, amount=1_000, paid_at=_utc(10, 15, 12), reference=f"R{n}"
        )
        ids[f"R{n}"] = pago.id
    with sesion_propia(session) as fabrica:
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 200, r.text
    esperado = [ref for ref, _ in sorted(ids.items(), key=lambda par: par[1])]
    assert [fila[5] for fila in parsear(r.content)[1]] == esperado
    assert fabrica.aperturas >= 3  # tres lotes (2, 2 y 1), cada uno con su sesión


async def test_la_exportacion_deja_la_fila_de_apertura_y_la_de_cierre(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 200, r.text
    apertura, cierre = await filas_export(session, TABLA)
    assert apertura["seq"] < cierre["seq"]
    assert apertura["user_id"] == cierre["user_id"] == admin.id
    assert apertura["record_id"] is not None and apertura["record_id"] == cierre["record_id"]
    abre = apertura["after"]
    assert abre["rows"] == 6 and abre["has_q"] is False
    assert abre["fields"] == CABECERA and abre["ip"] == "127.0.0.1"
    assert {"from", "to"} <= set(abre["filters"])
    assert cierre["after"]["completed"] is True and cierre["after"]["rows_sent"] == 6


async def test_si_el_consumidor_corta_el_cierre_queda_incompleto_con_las_filas_enviadas(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    escenario: dict[str, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(exports, "BATCH_SIZE", 1)
    admin = await usuario_real("admin")
    filtros = PaymentExportQuery.model_validate({"from": DESDE, "to": HASTA})
    with sesion_propia(session), actor_scope(admin.id):
        flujo = await service.export_payments(
            session, filtros, by=admin.id, ip="203.0.113.7", max_rows=100
        )
        assert flujo.rows == 6
        cuerpo = flujo.body()
        recibido = b""
        async for trozo in cuerpo:
            recibido += trozo
            if recibido.count(b"\r\n") >= 2:
                break
        await cuerpo.aclose()  # type: ignore[attr-defined]
    apertura, cierre = await filas_export(session, TABLA)
    assert apertura["after"]["rows"] == 6 and apertura["after"]["ip"] == "203.0.113.7"
    assert cierre["after"]["completed"] is False
    assert cierre["after"]["rows_sent"] == 1


# Roles, tope, flujo único y cubetas ----------------------------------------------------------


async def test_coach_y_member_reciben_403_sin_auditar_y_sin_token_401(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    for rol in ("coach", "member"):
        quien = await usuario_real(rol)
        r = await _pedir(app_http, quien, cabeceras)
        assert r.status_code == 403, (rol, r.text)
        assert r.json()["error"]["code"] == "forbidden"
    sin = await app_http.get(RUTA, params={"from": DESDE, "to": HASTA})
    assert sin.status_code == 401
    assert await filas_export(session, TABLA) == []


async def test_mas_filas_que_el_tope_da_422_export_too_large_antes_de_las_cabeceras(
    app_http: AsyncClient,
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    api_prueba.state.settings = api_prueba.state.settings.model_copy(update={"EXPORT_MAX_ROWS": 5})
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 422, r.text
    assert r.headers["content-type"].startswith("application/json")
    assert "content-disposition" not in r.headers
    assert r.json()["error"]["code"] == "export_too_large"
    assert await filas_export(session, TABLA) == []
    api_prueba.state.settings = api_prueba.state.settings.model_copy(update={"EXPORT_MAX_ROWS": 6})
    with sesion_propia(session):
        assert (await _pedir(app_http, admin, cabeceras)).status_code == 200


async def test_un_segundo_flujo_del_mismo_usuario_da_409(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    with single_flight(admin.id), sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "export_in_progress"
    assert await filas_export(session, TABLA) == []


async def test_la_tercera_en_un_minuto_da_429_por_la_cubeta_export(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = await usuario_real("admin")
    with sesion_propia(session):
        for _ in range(2):
            assert (await _pedir(app_http, admin, cabeceras)).status_code == 200
        caplog.set_level(logging.WARNING)
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 429, r.text
    assert "export" in [getattr(rec, "bucket", None) for rec in caplog.records]


@pytest.mark.parametrize(
    ("cubeta", "previas", "ventana"), [("export-hour", 5, 3600), ("export-day", 19, 86400)]
)
async def test_las_cubetas_de_hora_y_dia_cortan_con_429(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
    caplog: pytest.LogCaptureFixture,
    cubeta: str,
    previas: int,
    ventana: int,
) -> None:
    admin = await usuario_real("admin")
    for _ in range(previas):
        await ratelimit.record(cubeta, str(admin.id), window_s=ventana, kind="user")
    with sesion_propia(session):
        assert (await _pedir(app_http, admin, cabeceras)).status_code == 200
        caplog.set_level(logging.WARNING)
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 429, r.text
    assert cubeta in [getattr(rec, "bucket", None) for rec in caplog.records]


def test_la_ruta_export_se_declara_antes_que_el_detalle_del_pago(api_prueba: FastAPI) -> None:
    rutas = [
        r.path
        for r in effective_routes(api_prueba)[0]
        if "GET" in (r.methods or ()) and r.path.startswith(PAYMENTS)
    ]
    assert rutas.index(f"{PAYMENTS}/export") < rutas.index(f"{PAYMENTS}/{{payment_id}}")


async def test_el_cuerpo_corta_en_el_tope_si_aparecen_pagos_tras_el_conteo(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    escenario: dict[str, UUID],
) -> None:
    """S5-D253: tope 6 con seis pagos al contar; entra otro antes del recorrido: el CSV trae 6 filas
    y el cierre dice `completed=false` con `rows_sent=6`."""
    admin = await usuario_real("admin")
    filtros = PaymentExportQuery.model_validate({"from": DESDE, "to": HASTA})
    with sesion_propia(session), actor_scope(admin.id):
        flujo = await service.export_payments(
            session, filtros, by=admin.id, ip="203.0.113.7", max_rows=6
        )
        assert flujo.rows == 6
        membresia = await session.scalar(select(Membership).limit(1))
        assert membresia is not None
        await make_payment(session, membresia, amount=1_000, paid_at=_utc(10, 28, 15))
        cuerpo = b"".join([trozo async for trozo in flujo.body()])
    assert len(parsear(cuerpo)[1]) == 6
    apertura, cierre = await filas_export(session, TABLA)
    assert apertura["after"]["rows"] == 6
    assert cierre["after"]["completed"] is False and cierre["after"]["rows_sent"] == 6

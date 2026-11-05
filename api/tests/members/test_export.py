"""`GET /members/export` y `members.service.export_members` (S5-B12, US-138; S5-D41, S5-D60,
S5-D82; M-10, L-6). Rojo B12.

Hoy es 2026-10-21 (`reloj`). Escenario a mano (`escenario`), todo en Bogotá (UTC-5):
- Ana Pérez: doc 1001, tel 3001112233, correo ana@correo.co; creada 2026-10-10T03:30Z (= 2026-10-09
  22:30); membresía activa Mensual hasta 2026-11-30.
- `=Beto` Ríos: doc `-5000`, tel `+57 300 765 4321`, correo `+beto@x.co` (cada uno con disparador de
  fórmula: salen con apóstrofo); creado 2026-10-11T15:00Z (= 10:00); activa Trimestral hasta
  2026-12-31.
- Caro Díaz: doc 3003, sin teléfono ni correo; creada 2026-10-12T15:00Z; sin membresía.
- Dani Mora (dado de baja): doc 4004, tel 3004004004; creado 2026-10-13T15:00Z; sin membresía.

Filas esperadas (orden `(created_at, id)` ascendente): Ana, Beto, Caro; con `status=deleted`, Dani.
El CSV son las 9 columnas de N-29. Lo que se prueba:
- cabeceras, BOM, columnas, escape de fórmulas (L-6), filtros, dados de baja, 422 con `field`;
- lotes por llave `(created_at, id)` (con empates de `created_at`) y `crypto_ops` agregadas por
  lote y clase con propósito `export` (500 reales con 501 socios);
- auditoría `export`: fila de apertura ANTES del primer byte y fila de cierre con `completed` y
  `rows_sent`, también si el consumidor corta; el texto de `q` nunca se guarda;
- coach 403 sin tocar `crypto_ops`; sellado 503 y tope 422 ANTES de las cabeceras y sin auditar;
  un segundo flujo 409; cubetas `export`, `export-hour` y `export-day`.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring, configure_keyring
from app.core.export import single_flight
from app.core.security import effective_routes
from app.modules.members import exports, service
from app.modules.members.schemas import MemberExportQuery
from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.core._export_apoyo import (
    filas_export,
    ops_export,
    parsear,
    pedir_y_cortar,
    sesion_propia,
)
from tests.factories.members import KNOWN, make_member, make_members
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.members._apoyo import MEMBERS

RUTA = f"{MEMBERS}/export"
TABLA = "members.members"
CABECERA = [
    "nombres",
    "apellidos",
    "documento",
    "telefono",
    "correo",
    "estado_membresia",
    "plan",
    "vence",
    "creado",
]
ANA = ["Ana", "Pérez", "1001", "3001112233", "ana@correo.co", "active", "Mensual", "2026-11-30"]
BETO = [
    "'=Beto",
    "Ríos",
    "'-5000",
    "'+57 300 765 4321",
    "'+beto@x.co",
    "active",
    "Trimestral",
    "2026-12-31",
]
CARO = ["Caro", "Díaz", "3003", "", "", "none", "", ""]
DANI = ["Dani", "Mora", "4004", "3004004004", "", "none", "", ""]
FILA_ANA = [*ANA, "2026-10-09 22:30"]
FILA_BETO = [*BETO, "2026-10-11 10:00"]
FILA_CARO = [*CARO, "2026-10-12 10:00"]
FILA_DANI = [*DANI, "2026-10-13 10:00"]
DOCUMENTO = "member.document"
TELEFONO = "member.phone"
CORREO = "member.email"


def _utc(dia: int, hora: int, minuto: int = 0) -> datetime:
    return datetime(2026, 10, dia, hora, minuto, tzinfo=UTC)


@pytest.fixture
async def escenario(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> dict[str, UUID]:
    mensual = await make_plan(session, name="Mensual")
    trimestral = await make_plan(session, name="Trimestral")
    ana = await make_member(
        session,
        first_name="Ana",
        last_name="Pérez",
        document="1001",
        phone="3001112233",
        email="ana@correo.co",
        created_at=_utc(10, 3, 30),
    )
    beto = await make_member(
        session,
        first_name="=Beto",
        last_name="Ríos",
        document="-5000",
        phone="+57 300 765 4321",
        email="+beto@x.co",
        created_at=_utc(11, 15),
    )
    caro = await make_member(
        session,
        first_name="Caro",
        last_name="Díaz",
        document="3003",
        phone=None,
        email=None,
        created_at=_utc(12, 15),
    )
    dani = await make_member(
        session,
        first_name="Dani",
        last_name="Mora",
        document="4004",
        phone="3004004004",
        email=None,
        status="inactive",
        deleted_at=_utc(15, 15),
        created_at=_utc(13, 15),
    )
    await make_membership(
        session, ana, mensual, status="active", start=date(2026, 10, 1), end=date(2026, 11, 30)
    )
    await make_membership(
        session, beto, trimestral, status="active", start=date(2026, 10, 1), end=date(2026, 12, 31)
    )
    return {
        "mensual": mensual.id,
        "trimestral": trimestral.id,
        "ana": ana.id,
        "beto": beto.id,
        "caro": caro.id,
        "dani": dani.id,
    }


async def _pedir(
    cliente: AsyncClient,
    quien: UsuarioPrueba,
    cabeceras: Cabeceras,
    **params: str,
) -> Response:
    return await cliente.get(RUTA, params=params, headers=cabeceras(quien))


# Contenido ---------------------------------------------------------------------------------


async def test_admin_descarga_el_csv_con_cabeceras_bom_y_las_nueve_columnas_de_n29(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = await usuario_real("admin")
    caplog.set_level(logging.DEBUG)
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "text/csv; charset=utf-8"
    assert r.headers["content-disposition"] == "attachment; filename=socios-20261021.csv"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    cabecera, filas = parsear(r.content)
    assert cabecera == CABECERA
    assert filas == [FILA_ANA, FILA_BETO, FILA_CARO]
    assert "1991-07-23" not in r.text and "Rosa" not in r.text  # nada fuera de las 9 columnas
    assert KNOWN["document"] not in caplog.text  # el CSV no va a los registros


async def test_los_valores_con_disparador_de_formula_salen_con_apostrofo_l6(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras, q="Ríos")
    assert r.status_code == 200, r.text
    _, filas = parsear(r.content)
    assert filas == [FILA_BETO]
    assert filas[0][0] == "'=Beto" and filas[0][3] == "'+57 300 765 4321"  # L-6


async def test_sin_filtro_no_salen_los_dados_de_baja_y_con_status_deleted_solo_ellos(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras, status="deleted")
    assert r.status_code == 200, r.text
    assert parsear(r.content)[1] == [FILA_DANI]


@pytest.mark.parametrize(
    ("filtro", "esperadas"),
    [
        ({"plan_id": "mensual"}, [FILA_ANA]),
        ({"plan_id": "trimestral"}, [FILA_BETO]),
        ({"membership_status": "none"}, [FILA_CARO]),
        ({"membership_status": "active"}, [FILA_ANA, FILA_BETO]),
        ({"q": "1001"}, [FILA_ANA]),
        ({"q": "Díaz"}, [FILA_CARO]),
        ({"membership_status": "active", "q": "Pérez"}, [FILA_ANA]),
    ],
)
async def test_los_filtros_son_los_de_la_lista(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
    filtro: dict[str, str],
    esperadas: list[list[str]],
) -> None:
    admin = await usuario_real("admin")
    params = {k: str(escenario[v]) if k == "plan_id" else v for k, v in filtro.items()}
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras, **params)
    assert r.status_code == 200, r.text
    assert parsear(r.content)[1] == esperadas


@pytest.mark.parametrize(
    ("params", "campo"),
    [
        ({"status": "otro"}, "status"),
        ({"plan_id": "no-es-uuid"}, "plan_id"),
        ({"membership_status": "inventado"}, "membership_status"),
    ],
)
async def test_un_filtro_invalido_da_422_con_field_y_json(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    params: dict[str, str],
    campo: str,
) -> None:
    admin = await usuario_real("admin")
    r = await _pedir(app_http, admin, cabeceras, **params)
    assert r.status_code == 422, r.text
    assert r.headers["content-type"].startswith("application/json")
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", campo)
    assert await filas_export(session, TABLA) == []


# Lotes y bitácora de cifrado -----------------------------------------------------------------


async def test_los_lotes_siguen_la_llave_created_at_id_y_no_pierden_empates(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cinco socios con el MISMO `created_at` y lote de 2: la llave `(created_at, id)` los trae
    sin perder ni repetir ninguno, ordenados por id; los lotes son 2, 2 y 1 (solo documento)."""
    monkeypatch.setattr(exports, "BATCH_SIZE", 2)
    admin = await usuario_real("admin")
    mismo = _utc(10, 15)
    ids: dict[str, UUID] = {}
    for n in range(1, 6):
        socio = await make_member(
            session,
            first_name=f"S{n}",
            document=f"D{n}0000",
            phone=None,
            email=None,
            created_at=mismo,
        )
        ids[f"D{n}0000"] = socio.id
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 200, r.text
    esperado = [doc for doc, _ in sorted(ids.items(), key=lambda par: par[1])]
    assert [fila[2] for fila in parsear(r.content)[1]] == esperado
    assert await ops_export(session) == [(DOCUMENTO, 1), (DOCUMENTO, 2), (DOCUMENTO, 2)]


async def test_el_descifrado_deja_una_fila_por_lote_y_clase_con_proposito_export(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ana, Beto y Caro con lote de 2: lote 1 = Ana y Beto (documento 2, teléfono 2, correo 2);
    lote 2 = Caro (documento 1; sin teléfono ni correo no se descifra nada). Nada de
    `birth_date` ni `emergency_contact`, y las filas llevan al admin como actor."""
    monkeypatch.setattr(exports, "BATCH_SIZE", 2)
    admin = await usuario_real("admin")
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 200, r.text
    assert await ops_export(session) == [
        (DOCUMENTO, 1),
        (DOCUMENTO, 2),
        (CORREO, 2),
        (TELEFONO, 2),
    ]
    actores = await session.scalars(
        text("SELECT DISTINCT user_id FROM crypto.crypto_ops WHERE purpose = 'export'")
    )
    assert list(actores) == [admin.id]


def test_el_lote_real_es_de_500() -> None:
    assert exports.BATCH_SIZE == 500


async def test_501_socios_se_descifran_en_un_lote_de_500_y_otro_de_1(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    admin = await usuario_real("admin")
    await make_members(session, 501)  # sin teléfono ni correo: solo la clase documento
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 200, r.text
    assert len(parsear(r.content)[1]) == 501
    assert await ops_export(session) == [(DOCUMENTO, 1), (DOCUMENTO, 500)]


async def test_el_generador_abre_su_propia_sesion_al_menos_una_por_lote(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(exports, "BATCH_SIZE", 2)
    admin = await usuario_real("admin")
    with sesion_propia(session) as fabrica:
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 200, r.text
    assert fabrica.aperturas >= 2  # dos lotes (la sesión de la petición ya había cerrado)


# Auditoría ----------------------------------------------------------------------------------


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
    assert abre["rows"] == 3 and abre["has_q"] is False
    assert abre["fields"] == CABECERA
    assert abre["ip"] == "127.0.0.1"
    assert isinstance(abre["filters"], dict)
    assert cierre["after"]["completed"] is True and cierre["after"]["rows_sent"] == 3


async def test_el_texto_de_q_nunca_se_guarda_solo_has_q_y_los_filtros_estructurados(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras, q="4004", status="deleted")
    assert r.status_code == 200, r.text
    assert parsear(r.content)[1] == [FILA_DANI]
    filas = await filas_export(session, TABLA)
    assert len(filas) == 2
    abre = filas[0]["after"]
    assert abre["has_q"] is True and abre["rows"] == 1
    assert abre["filters"]["status"] == "deleted"
    assert "q" not in abre["filters"]
    volcado = " ".join(str(f["after"]) for f in filas)
    assert "4004" not in volcado


async def test_si_el_consumidor_corta_el_cierre_queda_incompleto_con_las_filas_enviadas(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    escenario: dict[str, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lote de 1 y tres socios: se leen la cabecera y la primera fila y se cierra el generador
    (el cliente cortó). La apertura ya dijo 3 filas; el cierre dice `completed=False` y
    `rows_sent=1`."""
    monkeypatch.setattr(exports, "BATCH_SIZE", 1)
    admin = await usuario_real("admin")
    with sesion_propia(session), actor_scope(admin.id):
        flujo = await service.export_members(
            session, MemberExportQuery(), by=admin.id, ip="203.0.113.7", max_rows=100
        )
        assert flujo.rows == 3
        cuerpo = flujo.body()
        recibido = b""
        async for trozo in cuerpo:
            recibido += trozo
            if recibido.count(b"\r\n") >= 2:
                break
        await cuerpo.aclose()  # type: ignore[attr-defined]
    apertura, cierre = await filas_export(session, TABLA)
    assert apertura["after"]["rows"] == 3 and apertura["after"]["ip"] == "203.0.113.7"
    assert cierre["after"]["completed"] is False
    assert cierre["after"]["rows_sent"] == 1


# Roles y errores antes de las cabeceras -------------------------------------------------------


async def test_el_coach_recibe_403_y_no_se_descifra_ni_se_audita_nada(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    coach = await usuario_real("coach")
    antes = await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops"))
    r = await _pedir(app_http, coach, cabeceras)
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops")) == antes
    assert await filas_export(session, TABLA) == []


async def test_member_recibe_403_y_sin_token_401(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    bus_listo: Keyring,
) -> None:
    socio = await usuario_real("member")
    assert (await _pedir(app_http, socio, cabeceras)).status_code == 403
    sin_token = await app_http.get(RUTA)
    assert sin_token.status_code == 401
    assert sin_token.json()["error"]["code"] == "unauthorized"


async def test_sellado_responde_503_antes_de_las_cabeceras_y_sin_auditar(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    configure_keyring(None)
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 503, r.text
    assert r.headers["content-type"].startswith("application/json")
    assert "content-disposition" not in r.headers
    assert r.json()["error"]["code"] == "crypto_unavailable"
    assert r.headers["retry-after"] == "30"
    assert await filas_export(session, TABLA) == []


async def test_mas_filas_que_el_tope_da_422_export_too_large_antes_de_las_cabeceras(
    app_http: AsyncClient,
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    """Tope 2 con tres socios vivos: 422 JSON, sin auditar ni descifrar. Con tope 3 pasa."""
    admin = await usuario_real("admin")
    api_prueba.state.settings = api_prueba.state.settings.model_copy(update={"EXPORT_MAX_ROWS": 2})
    with sesion_propia(session):
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 422, r.text
    assert r.headers["content-type"].startswith("application/json")
    assert "content-disposition" not in r.headers
    assert r.json()["error"]["code"] == "export_too_large"
    assert await filas_export(session, TABLA) == []
    assert await ops_export(session) == []
    api_prueba.state.settings = api_prueba.state.settings.model_copy(update={"EXPORT_MAX_ROWS": 3})
    with sesion_propia(session):
        ok = await _pedir(app_http, admin, cabeceras)
    assert ok.status_code == 200, ok.text


async def test_un_segundo_flujo_del_mismo_usuario_da_409_y_al_terminar_se_libera(
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
    assert "content-disposition" not in r.headers
    assert await filas_export(session, TABLA) == []
    with sesion_propia(session):
        primera = await _pedir(app_http, admin, cabeceras)
        segunda = await _pedir(app_http, admin, cabeceras)  # el flujo anterior ya se liberó
    assert (primera.status_code, segunda.status_code) == (200, 200)


# Cubetas (S5-D81) ------------------------------------------------------------------------------


def _buckets(caplog: pytest.LogCaptureFixture) -> list[Any]:
    return [getattr(rec, "bucket", None) for rec in caplog.records]


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
    assert r.json()["error"]["code"] == "rate_limited"
    assert "export" in _buckets(caplog)


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
        assert (await _pedir(app_http, admin, cabeceras)).status_code == 200  # la 6.ª / la 20.ª
        caplog.set_level(logging.WARNING)
        r = await _pedir(app_http, admin, cabeceras)
    assert r.status_code == 429, r.text
    assert cubeta in _buckets(caplog)


def test_la_ruta_export_se_declara_antes_que_el_detalle_del_socio(
    api_prueba: FastAPI,
) -> None:
    rutas = [
        r.path
        for r in effective_routes(api_prueba)[0]
        if "GET" in (r.methods or ()) and r.path.startswith(MEMBERS)
    ]
    assert rutas.index(f"{MEMBERS}/export") < rutas.index(f"{MEMBERS}/{{member_id}}")


# Revisión de seguridad (S5-D252, S5-D253) -------------------------------------------------------


async def test_si_el_cliente_se_desconecta_a_mitad_el_cierre_queda_y_el_flujo_se_libera(
    app_http: AsyncClient,
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S5-D252: el `send` del cliente falla tras la cabecera y la primera fila (lote de 1): la
    respuesta cierra el cuerpo, la fila de cierre dice `completed=false` con las filas enviadas y
    un segundo GET del mismo usuario no da 409."""
    monkeypatch.setattr(exports, "BATCH_SIZE", 1)
    admin = await usuario_real("admin")
    with sesion_propia(session):
        recibidos = await pedir_y_cortar(api_prueba, RUTA, {}, cabeceras(admin), cortar_tras=2)
        assert recibidos == 2
        apertura, cierre = await filas_export(session, TABLA)
        assert apertura["record_id"] == cierre["record_id"]
        assert cierre["after"]["completed"] is False
        assert cierre["after"]["rows_sent"] >= 1
        otra = await _pedir(app_http, admin, cabeceras)
    assert otra.status_code == 200, otra.text


async def test_el_cuerpo_corta_en_el_tope_si_aparecen_filas_tras_el_conteo(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    escenario: dict[str, UUID],
) -> None:
    """S5-D253: tope 3 con tres socios al contar; se inserta una cuarta antes del recorrido. El CSV
    trae 3 filas y el cierre dice `completed=false` con `rows_sent=3` (la apertura dijo 3)."""
    admin = await usuario_real("admin")
    with sesion_propia(session), actor_scope(admin.id):
        flujo = await service.export_members(
            session, MemberExportQuery(), by=admin.id, ip="203.0.113.7", max_rows=3
        )
        assert flujo.rows == 3
        await make_member(session, first_name="Tarde", document="5005", created_at=_utc(20, 15))
        cuerpo = b"".join([trozo async for trozo in flujo.body()])
    _, filas = parsear(cuerpo)
    assert len(filas) == 3 and all(f[0] != "Tarde" for f in filas)
    apertura, cierre = await filas_export(session, TABLA)
    assert apertura["after"]["rows"] == 3
    assert cierre["after"]["completed"] is False and cierre["after"]["rows_sent"] == 3

"""Filtro `last_attendance` y columnas `last_attendance_at` y `membership_classes_remaining` de
`GET /api/v1/members` (S7-R2, US-163; S7-D15, G-03, G-04). Rojo R2.

Hoy es el miércoles 21 de octubre de 2026 en Bogotá (reloj de las pruebas, 10:00). El corte de
`Nd` es el día civil de Bogotá `hoy - N`: asistir ese día todavía cuenta como reciente.

Escenario (`escenario`): ocho socios ficticios con la última asistencia viva de cada uno.
- Pedro: hace 40 días. Juan: ayer (y una asistencia anterior). Mara: hace 10 días.
- Lola: nunca. Sara: hace 45 días y una de ayer QUITADA (no cuenta).
- Borde30: el día `hoy - 30` a las 00:00 de Bogotá (05:00Z): aún reciente para `30d`.
- Borde31: un minuto antes (04:59Z, el día `hoy - 31`): ya entra a `30d`.
- Tomás: dado de baja, nunca asistió: no sale nunca (la lista solo trae vivos por defecto).

Membresías: Pedro, Mara y Borde31 con mensual activa; Juan con tiquetera de 12 clases y 2
restantes; Sara y Lola sin membresía. Sara está `inactive`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from app.core.pagination import PageParams
from app.core.ratelimit import usage
from app.modules.members import service
from app.modules.members.schemas import MemberListQuery
from tests.conftest import Cabeceras, ContadorDeConsultas, CrearUsuario
from tests.factories.classes import make_attendance, make_session
from tests.factories.members import make_member, make_members
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.members._apoyo import MEMBERS
from tests.notifications._apoyo_avisos import ANTES, socio

TABLA = "classes.attendance"
# Medianoche de Bogotá = 05:00Z; el reloj de las pruebas marca 2026-10-21 15:00Z (10:00 Bogotá).
HOY_BOGOTA = datetime(2026, 10, 21, 5, 0, tzinfo=UTC)

PEDRO_AT = HOY_BOGOTA - timedelta(days=40, hours=-4)
JUAN_AT = HOY_BOGOTA - timedelta(days=1, hours=-6)
SARA_AT = HOY_BOGOTA - timedelta(days=45, hours=-2)


async def _asistio(session: AsyncSession, miembro: Any, cuando: datetime, **cambios: Any) -> None:
    clase = await make_session(session, starts_at=cuando)
    await make_attendance(session, clase, miembro.id, checked_in_at=cuando, **cambios)


@pytest.fixture
async def escenario(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> dict[str, UUID]:
    mensual = await make_plan(session, name="Mensual")
    tiquetera = await make_plan(
        session, name="Tiquetera 12", kind="classes", class_count=12, duration_days=90
    )
    pedro = await socio(session, nombre="Pedro", apellido="Díaz")
    juan = await socio(session, nombre="Juan", apellido="Rojas")
    mara = await socio(session, nombre="Mara", apellido="Ruiz")
    lola = await socio(session, nombre="Lola", apellido="Paz")
    sara = await socio(session, nombre="Sara", apellido="Gil", status="inactive")
    borde30 = await socio(session, nombre="Borde", apellido="Treinta")
    borde31 = await socio(session, nombre="Borde", apellido="Treintaiuno")
    tomas = await socio(
        session, nombre="Tomás", apellido="Baja", deleted_at=ANTES, status="inactive"
    )

    await _asistio(session, pedro, PEDRO_AT)
    await _asistio(session, juan, HOY_BOGOTA - timedelta(days=9))
    await _asistio(session, juan, JUAN_AT)
    await _asistio(session, mara, HOY_BOGOTA - timedelta(days=10, hours=-3))
    await _asistio(session, sara, SARA_AT)
    await _asistio(
        session,
        sara,
        HOY_BOGOTA - timedelta(days=1, hours=-4),
        removed_at=HOY_BOGOTA,
        removed_reason="error",
    )
    await _asistio(session, borde30, HOY_BOGOTA - timedelta(days=30))
    await _asistio(session, borde31, HOY_BOGOTA - timedelta(days=30, minutes=1))

    await make_membership(session, pedro, mensual, status="active")
    await make_membership(session, borde31, mensual, status="active")
    await make_membership(session, mara, mensual, status="active")
    await make_membership(session, juan, tiquetera, status="active", classes_remaining=2)
    return {
        nombre: m.id
        for nombre, m in {
            "pedro": pedro,
            "juan": juan,
            "mara": mara,
            "lola": lola,
            "sara": sara,
            "borde30": borde30,
            "borde31": borde31,
            "tomas": tomas,
        }.items()
    }


async def _lista(
    cliente: AsyncClient, cabeceras: Cabeceras, quien: Any, **params: Any
) -> dict[str, Any]:
    r = await cliente.get(MEMBERS, params={"limit": 200, **params}, headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    cuerpo: dict[str, Any] = r.json()
    return cuerpo


def _ids(cuerpo: dict[str, Any]) -> set[str]:
    return {fila["id"] for fila in cuerpo["items"]}


def _esperados(ids: dict[str, UUID], *nombres: str) -> set[str]:
    return {str(ids[nombre]) for nombre in nombres}


@pytest.mark.parametrize(
    ("valor", "nombres"),
    [
        ("7d", {"pedro", "mara", "lola", "sara", "borde30", "borde31"}),
        ("14d", {"pedro", "lola", "sara", "borde30", "borde31"}),
        ("30d", {"pedro", "lola", "sara", "borde31"}),
        ("60d", {"lola"}),
        ("never", {"lola"}),
    ],
)
async def test_cada_valor_devuelve_los_que_no_vienen_desde_el_corte_o_nunca(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
    valor: str,
    nombres: set[str],
) -> None:
    admin = await usuario_real("admin")
    cuerpo = await _lista(app_http, cabeceras, admin, last_attendance=valor)
    assert _ids(cuerpo) == _esperados(escenario, *nombres)
    assert cuerpo["total"] == len(nombres)


async def test_never_devuelve_solo_los_que_nunca_asistieron_y_una_quitada_no_cuenta(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
) -> None:
    coach = await usuario_real("coach")
    cuerpo = await _lista(app_http, cabeceras, coach, last_attendance="never")
    assert _ids(cuerpo) == _esperados(escenario, "lola")
    # Sara solo tiene una asistencia viva (hace 45 días): la de ayer fue quitada.
    en_30 = await _lista(app_http, cabeceras, coach, last_attendance="30d")
    assert str(escenario["sara"]) in _ids(en_30)


async def test_la_baja_del_socio_no_sale_aunque_nunca_haya_asistido(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    cuerpo = await _lista(app_http, cabeceras, admin, last_attendance="never")
    assert str(escenario["tomas"]) not in _ids(cuerpo)
    bajas = await _lista(app_http, cabeceras, admin, last_attendance="never", status="deleted")
    assert _ids(bajas) == _esperados(escenario, "tomas")


async def test_combinado_con_q_status_y_membership_status(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")

    async def con(**filtros: Any) -> set[str]:
        return _ids(await _lista(app_http, cabeceras, admin, last_attendance="30d", **filtros))

    assert await con(q="Díaz") == _esperados(escenario, "pedro")
    assert await con(q="treinta") == _esperados(escenario, "borde31")
    assert await con(status="inactive") == _esperados(escenario, "sara")
    assert await con(membership_status="active") == _esperados(escenario, "pedro", "borde31")
    assert await con(membership_status="none") == _esperados(escenario, "lola", "sara")
    assert await con(membership_status="none", status="active") == _esperados(escenario, "lola")
    assert await con(q="Díaz", membership_status="none") == set()


async def test_total_correcto_y_paginacion_estable(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    esperados = _esperados(escenario, "pedro", "lola", "sara", "borde31")
    vistos: list[str] = []
    for desplazamiento in (0, 2):
        pagina = await _lista(
            app_http, cabeceras, admin, last_attendance="30d", limit=2, offset=desplazamiento
        )
        assert pagina["total"] == 4
        assert (pagina["limit"], pagina["offset"]) == (2, desplazamiento)
        assert len(pagina["items"]) == 2
        vistos += [fila["id"] for fila in pagina["items"]]
    assert set(vistos) == esperados and len(vistos) == 4
    ultima = await _lista(app_http, cabeceras, admin, last_attendance="30d", limit=2, offset=4)
    assert ultima["items"] == [] and ultima["total"] == 4


async def test_sin_filtro_la_lista_no_cambia(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    cuerpo = await _lista(app_http, cabeceras, admin)
    assert _ids(cuerpo) == _esperados(
        escenario, "pedro", "juan", "mara", "lola", "sara", "borde30", "borde31"
    )


@pytest.mark.parametrize("valor", ["mucho", "", "7", "90d", "7D", "Never"])
async def test_valor_invalido_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, valor: str
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(f"{MEMBERS}?last_attendance={valor}", headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", "last_attendance")
    assert "mucho" not in error["message"]


async def test_el_rol_member_recibe_403_y_sin_token_401(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    socio_rol = await usuario_real("member")
    r = await app_http.get(f"{MEMBERS}?last_attendance=30d", headers=cabeceras(socio_rol))
    assert r.status_code == 403, r.text
    assert (await app_http.get(f"{MEMBERS}?last_attendance=30d")).status_code == 401


async def test_consume_staff_read_solo_con_el_filtro(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
) -> None:
    coach = await usuario_real("coach")
    antes = await usage("staff-read", str(coach.id), window_s=60)
    await _lista(app_http, cabeceras, coach)
    assert await usage("staff-read", str(coach.id), window_s=60) == antes
    for n in (1, 2):
        await _lista(app_http, cabeceras, coach, last_attendance="30d")
        assert await usage("staff-read", str(coach.id), window_s=60) == antes + n


async def test_last_attendance_at_es_la_ultima_viva_en_utc_o_null(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    cuerpo = await _lista(app_http, cabeceras, admin)
    filas = {fila["id"]: fila for fila in cuerpo["items"]}
    esperadas = {
        "pedro": PEDRO_AT,
        "juan": JUAN_AT,
        "sara": SARA_AT,  # la de ayer está quitada
        "borde30": HOY_BOGOTA - timedelta(days=30),
        "lola": None,
    }
    for nombre, cuando in esperadas.items():
        valor = filas[str(escenario[nombre])]["last_attendance_at"]
        if cuando is None:
            assert valor is None
        else:
            assert datetime.fromisoformat(valor) == cuando
            assert datetime.fromisoformat(valor).utcoffset() == timedelta(0)


async def test_membership_classes_remaining_solo_en_tiquetera(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    filas = {f["id"]: f for f in (await _lista(app_http, cabeceras, admin))["items"]}
    assert filas[str(escenario["juan"])]["membership_classes_remaining"] == 2
    for nombre in ("pedro", "mara", "lola", "sara"):  # mensual o sin membresía
        assert filas[str(escenario[nombre])]["membership_classes_remaining"] is None


async def test_last_attendance_at_en_una_consulta_por_pagina(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    socios = await make_members(session, 50)
    clase = await make_session(session, starts_at=HOY_BOGOTA - timedelta(days=3))
    for miembro in socios[::2]:
        await make_attendance(session, clase, miembro.id)
    admin = await usuario_real("admin")

    with contador_de_consultas.midiendo():
        r = await app_http.get(f"{MEMBERS}?limit=50", headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert len(r.json()["items"]) == 50
    assert contador_de_consultas.de(TABLA) == 1, contador_de_consultas.sentencias
    con = [f for f in r.json()["items"] if f["last_attendance_at"] is not None]
    assert len(con) == 25

    with contador_de_consultas.midiendo():  # con el filtro: una del conjunto y una de la página
        r = await app_http.get(f"{MEMBERS}?limit=50&last_attendance=7d", headers=cabeceras(admin))
    assert r.status_code == 200, r.text
    assert contador_de_consultas.de(TABLA) == 2, contador_de_consultas.sentencias
    assert len(r.json()["items"]) == 25  # los 25 que nunca vinieron


async def test_una_pagina_vacia_no_consulta_asistencias(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    await make_member(session)
    admin = await usuario_real("admin")
    with contador_de_consultas.midiendo():
        r = await app_http.get(f"{MEMBERS}?q=zzzz-sin-resultados", headers=cabeceras(admin))
    assert r.status_code == 200 and r.json()["items"] == [], r.text
    assert contador_de_consultas.de(TABLA) == 0


async def test_el_service_acepta_el_filtro_y_lo_combina(
    session: AsyncSession, escenario: dict[str, UUID]
) -> None:
    pagina = await service.list(
        session,
        MemberListQuery(last_attendance="30d", membership_status="active"),
        PageParams(limit=50, offset=0),
    )
    assert {fila.id for fila in pagina.items} == {escenario["pedro"], escenario["borde31"]}
    assert pagina.total == 2

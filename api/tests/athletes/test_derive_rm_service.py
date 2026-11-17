"""RM derivado por `PUT /results` real (S9-B3, US-181; S9-D7, S9-D10, S9-D30, S9-D56, L-4).

El handler suscrito a `WodResultValidated` corre en la transacción del emisor: sin `lock_member`
propio, sin cifrar ni descifrar nada y con cargas en gramos enteros (S8-D41).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.context import actor_scope
from app.core.crypto.keyring import configure_keyring
from app.core.pagination import PageParams
from app.modules.athletes import derive, service
from app.modules.results.events import WodResultValidated
from tests.athletes._apoyo import auditoria_de_records
from tests.athletes._apoyo_derivar import (
    AlertasCapturadas,
    contar_sentencias,
    escena_carga,
    poner,
    records_de,
    vigente_g,
    wod_extra,
)
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.athletes import INVALIDAR, make_record
from tests.results._apoyo import escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

PAGINA = PageParams(limit=25, offset=0)


def _id_de(respuesta: Response) -> UUID:
    assert respuesta.status_code == 201, respuesta.text
    return UUID(respuesta.json()["id"])


async def test_100_kg_sobre_95_kg_crea_el_derivado_con_todos_sus_campos(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena_carga(session)
    ayer = await wod_extra(session, e, "2026-10-20", "Ayer carga")
    coach = await usuario_real("coach")
    h = cabeceras(coach)
    primero = _id_de(await poner(app_http, h, e, wod_id=ayer, load_g=95_000))

    segundo = _id_de(await poner(app_http, h, e, load_g=100_000))

    filas = await records_de(session, e.socio_id)
    assert sorted(f["value_g"] for f in filas) == [95_000, 100_000]
    assert vigente_g(filas) == 100_000
    nuevo = next(f for f in filas if f["value_g"] == 100_000)
    assert nuevo["result_id"] == segundo
    assert nuevo["source"] == "derived" and nuevo["kind"] == "rm"
    assert nuevo["movement_id"] == e.movimientos[0]
    assert nuevo["wod_id"] == e.wod_id
    assert nuevo["achieved_on"].isoformat() == "2026-10-21"
    assert nuevo["created_by"] == coach.id
    assert nuevo["capped"] is False and nuevo["invalidated_at"] is None
    assert (nuevo["level"], nuevo["seconds"], nuevo["rounds"], nuevo["reps"]) == (None,) * 4
    assert nuevo["load_g"] is None and nuevo["benchmark_id"] is None
    anterior = next(f for f in filas if f["value_g"] == 95_000)
    assert anterior["result_id"] == primero


async def test_90_kg_sobre_95_kg_no_crea_nada(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena_carga(session)
    ayer = await wod_extra(session, e, "2026-10-20", "Ayer carga")
    h = cabeceras(await usuario_real("coach"))
    _id_de(await poner(app_http, h, e, wod_id=ayer, load_g=95_000))

    resultado = await poner(app_http, h, e, load_g=90_000)

    assert resultado.status_code == 201, resultado.text
    filas = await records_de(session, e.socio_id)
    assert [f["value_g"] for f in filas] == [95_000]


@pytest.mark.parametrize(
    ("cambios", "motivo"),
    [
        ({"load_g": 0}, "cero gramos"),
        ({"level": "scaled", "load_g": 150_000}, "scaled"),
    ],
)
async def test_marcas_que_no_derivan_no_dejan_record(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    cambios: dict[str, Any],
    motivo: str,
) -> None:
    e = await escena_carga(session)
    h = cabeceras(await usuario_real("coach"))

    resultado = await poner(app_http, h, e, **cambios)

    assert resultado.status_code == 201, resultado.text
    assert await records_de(session, e.socio_id) == [], motivo


async def test_rx_plus_deriva_igual_que_rx(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena_carga(session)
    h = cabeceras(await usuario_real("coach"))

    resultado = await poner(app_http, h, e, level="rx_plus", load_g=110_000)

    assert resultado.status_code == 201, resultado.text
    assert vigente_g(await records_de(session, e.socio_id)) == 110_000


async def test_un_wod_que_no_es_de_carga_no_deriva(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena(session, score_type="time", con_clase=False)
    h = cabeceras(await usuario_real("coach"))

    resultado = await poner(app_http, h, e, load_g=None, seconds=300)

    assert resultado.status_code == 201, resultado.text
    assert await records_de(session, e.socio_id) == []


async def test_la_auditoria_registra_el_insert_con_quien_valido(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena_carga(session)
    coach = await usuario_real("coach")
    _id_de(await poner(app_http, cabeceras(coach), e, load_g=100_000))

    (fila,) = await records_de(session, e.socio_id)

    auditoria = await auditoria_de_records(session, fila["id"])
    assert [a["action"] for a in auditoria] == ["insert"]
    assert auditoria[0]["user_id"] == coach.id
    assert fila["created_by"] == coach.id


async def test_el_evento_emitido_dos_veces_no_duplica_ni_alerta(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    alertas: AlertasCapturadas,
    caplog: pytest.LogCaptureFixture,
) -> None:
    e = await escena_carga(session)
    coach = await usuario_real("coach")
    resultado_id = _id_de(await poner(app_http, cabeceras(coach), e, load_g=100_000))
    evento = WodResultValidated(result_id=resultado_id, member_id=e.socio_id, wod_id=e.wod_id)

    with actor_scope(coach.id), caplog.at_level(logging.DEBUG):
        await events.emit(evento, session)
        await events.emit(evento, session)

    assert len(await records_de(session, e.socio_id)) == 1
    assert alertas.recibidas == []
    assert "derivación omitida" not in caplog.text


async def test_un_23505_del_unico_result_kind_es_un_no_op_sin_alerta(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    alertas: AlertasCapturadas,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """US-181 CA6: la fila invalidada sigue ocupando `(result_id, kind)`; si el evento llega de
    nuevo, el `INSERT` choca con ese único: se ignora, sin alerta y con la sesión usable."""
    e = await escena_carga(session)
    coach = await usuario_real("coach")
    resultado_id = _id_de(await poner(app_http, cabeceras(coach), e, load_g=100_000))
    (fila,) = await records_de(session, e.socio_id)
    await session.execute(INVALIDAR, {"a": coach.id, "r": "voided", "n": None, "i": fila["id"]})
    evento = WodResultValidated(result_id=resultado_id, member_id=e.socio_id, wod_id=e.wod_id)

    with actor_scope(coach.id), caplog.at_level(logging.DEBUG):
        await events.emit(evento, session)

    filas = await records_de(session, e.socio_id)
    assert len(filas) == 1 and filas[0]["invalidated_at"] is not None
    assert alertas.recibidas == []
    assert "derivación omitida" not in caplog.text
    assert await session.scalar(text("SELECT 1")) == 1, "la sesión sigue usable"


async def test_deriva_con_el_keyring_sin_cargar(session: AsyncSession) -> None:
    """Derivar no cifra ni descifra: con el custodio caído el resultado y su RM se guardan."""
    e = await escena_carga(session)
    antes = await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops"))
    configure_keyring(None)

    salida = await registrar(session, e, load_g=100_000, seconds=None)

    filas = await records_de(session, e.socio_id)
    assert [f["value_g"] for f in filas] == [100_000]
    assert filas[0]["result_id"] == salida.id
    despues = await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops"))
    assert despues == antes, "el handler no usó el bus de cifrado"


async def test_convive_con_un_record_manual(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena_carga(session)
    ayer = await wod_extra(session, e, "2026-10-20", "Ayer carga")
    h = cabeceras(await usuario_real("coach"))
    manual = await make_record(
        session, e.socio_id, movement_id=e.movimientos[0], value_g=90_000, source="manual"
    )

    _id_de(await poner(app_http, h, e, wod_id=ayer, load_g=100_000))
    _id_de(await poner(app_http, h, e, load_g=100_000))  # igual al vigente: no crea

    filas = await records_de(session, e.socio_id)
    assert sorted((f["source"], f["value_g"]) for f in filas) == [
        ("derived", 100_000),
        ("manual", 90_000),
    ]
    assert vigente_g(filas) == 100_000
    pagina = await service.list_records(session, e.socio_id, PAGINA)
    vigentes = [r for r in pagina.items if r.is_current]
    assert [(r.source, r.value_g) for r in vigentes] == [("derived", 100_000)]
    assert manual.invalidated_at is None


async def test_result_source_en_record_out_desk_kiosk_y_manual(session: AsyncSession) -> None:
    """L-4: el récord derivado dice si su resultado vino del escritorio o de la tablet; el manual
    no tiene resultado (`None`)."""
    e = await escena(
        session, score_type="load", time_cap_s=None, fecha="2026-10-20", con_clase=False
    )
    kiosco = await escena(session, score_type="load", time_cap_s=None)
    await registrar(session, e, source="desk", load_g=100_000, seconds=None)
    await registrar(session, kiosco, source="kiosk", load_g=80_000, seconds=None)
    await make_record(session, e.socio_id, movement_id=e.movimientos[1], value_g=50_000)

    desk = await service.list_records(session, e.socio_id, PAGINA)
    tablet = await service.list_records(session, kiosco.socio_id, PAGINA)

    por_fuente = {(r.source, r.value_g): r.result_source for r in desk.items}
    assert por_fuente == {("derived", 100_000): "desk", ("manual", 50_000): None}
    assert [(r.source, r.result_source) for r in tablet.items] == [("derived", "kiosk")]


async def test_presupuesto_de_sentencias_por_put_results(session: AsyncSession) -> None:
    """S9-D30: sin récord posible el handler suma 2 sentencias (`get_mark` y `record_meta_for`);
    con derivación, a lo sumo 6 sobre las tablas de `athletes`, `results` y `wods`. Se mide contra
    el mismo registro sin el handler suscrito."""
    tablas = ("athletes.", "results.", "wods.")

    async def medir(score_type: str, dia: str, *, con_handler: bool, **marca: Any) -> int:
        e = await escena(
            session,
            score_type=score_type,
            time_cap_s=None if score_type == "load" else 600,
            fecha=dia,
            con_clase=False,
        )
        quitados: list[Any] = []
        if not con_handler:
            suscritos = events._subscribers.get(WodResultValidated, [])
            quitados = [h for h in suscritos if h is derive.on_wod_result_validated]
            for h in quitados:
                suscritos.remove(h)
        try:
            with contar_sentencias(session, tablas) as vistas:
                await registrar(session, e, **marca)
        finally:
            for h in quitados:  # la prueba mide con y sin handler: se vuelve a suscribir
                events.subscribe(WodResultValidated, h)
        return len(vistas)

    sin_posible = await medir("time", "2026-10-10", con_handler=True, seconds=300)
    base_sin = await medir("time", "2026-10-11", con_handler=False, seconds=300)
    assert sin_posible - base_sin == 2

    con_derivacion = await medir(
        "load", "2026-10-12", con_handler=True, load_g=100_000, seconds=None
    )
    base_con = await medir("load", "2026-10-13", con_handler=False, load_g=100_000, seconds=None)
    assert con_derivacion - base_con == 4


async def test_el_patch_de_unit_con_un_derivado_vivo_da_422_y_nunca_pasa(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    """S9-D56 (LOW-3, condición de B2): un récord derivado se inserta sin `FOR SHARE` del catálogo
    porque exige un WOD que use el movimiento; con un derivado vivo, cambiar `unit` da 422 (por el
    uso o por el puerto de récords) y la unidad queda intacta."""
    e = await escena_carga(session)
    h = cabeceras(await usuario_real("coach"))
    _id_de(await poner(app_http, h, e, load_g=100_000))
    assert [f["source"] for f in await records_de(session, e.socio_id)] == ["derived"]
    admin = await usuario_real("admin")

    r = await app_http.patch(
        f"/api/v1/movements/{e.movimientos[0]}", json={"unit": "reps"}, headers=cabeceras(admin)
    )

    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "unit"
    unidad = await session.scalar(
        text("SELECT unit FROM wods.movements WHERE id = :i"), {"i": e.movimientos[0]}
    )
    assert unidad == "kg"

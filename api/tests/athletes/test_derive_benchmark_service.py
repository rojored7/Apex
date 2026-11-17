"""Récord de benchmark derivado por `PUT /results` real (S9-B4, US-182; S9-D10, S9-D30, S9-D57/58).

El handler corre en la transacción del emisor, sin candados propios. Valores a mano: segundos para
`time`, gramos enteros para `load` (S8-D41). Dos WODs con el mismo `benchmark_id` son el mismo
benchmark (los récords se identifican por el benchmark, no por el WOD).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.db import DatabaseBusy
from app.modules.athletes import derive
from app.modules.athletes.events import PersonalRecordSet
from app.modules.results.events import WodResultValidated
from tests.athletes._apoyo_derivar import (
    AlertasCapturadas,
    contar_sentencias,
    escena_carga,
    poner,
    records_de,
    wod_extra,
)
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.wods import make_benchmark, make_wod
from tests.results._apoyo import Escena, escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def _escena_time(session: AsyncSession, fecha: str = "2026-10-01") -> Escena:
    return await escena(session, score_type="time", time_cap_s=600, fecha=fecha, con_clase=False)


async def _benchmark(session: AsyncSession, e: Escena, score_type: str = "time") -> UUID:
    return (await make_benchmark(session, e.coach, f"Bench {uuid4().hex[:8]}", score_type)).id


async def _wod_de(
    session: AsyncSession,
    e: Escena,
    benchmark_id: UUID,
    fecha: str,
    score_type: str = "time",
) -> UUID:
    """Otro WOD del mismo benchmark con los mismos movimientos (el primero es el principal)."""
    wod = await make_wod(
        session,
        e.coach,
        list(e.movimientos),
        date=fecha,
        title=f"Bench {fecha} {uuid4().hex[:6]}",
        score_type=score_type,
        time_cap_s=600 if score_type == "time" else None,
        benchmark_id=str(benchmark_id),
    )
    return wod.id


def _id_de(respuesta: Response) -> UUID:
    assert respuesta.status_code == 201, respuesta.text
    return UUID(respuesta.json()["id"])


def _del_benchmark(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [f for f in filas if f["kind"] == "benchmark"]


async def _resultados(session: AsyncSession, member_id: UUID) -> int:
    return int(
        await session.scalar(
            text("SELECT count(*) FROM results.wod_results WHERE member_id = :m"), {"m": member_id}
        )
        or 0
    )


async def _tiempo(
    http: AsyncClient, h: dict[str, str], e: Escena, wod_id: UUID, segundos: int, **extra: Any
) -> UUID:
    return _id_de(await poner(http, h, e, wod_id=wod_id, load_g=None, seconds=segundos, **extra))


async def test_245_s_sobre_260_s_crea_el_record_con_todos_sus_campos(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await _escena_time(session)
    bench = await _benchmark(session, e)
    ayer = await _wod_de(session, e, bench, "2026-10-20")
    hoy = await _wod_de(session, e, bench, "2026-10-21")
    coach = await usuario_real("coach")
    h = cabeceras(coach)
    primero = await _tiempo(app_http, h, e, ayer, 260)

    segundo = await _tiempo(app_http, h, e, hoy, 245)

    filas = _del_benchmark(await records_de(session, e.socio_id))
    assert sorted(f["seconds"] for f in filas) == [245, 260]
    nuevo = next(f for f in filas if f["seconds"] == 245)
    assert nuevo["result_id"] == segundo and nuevo["wod_id"] == hoy
    assert nuevo["source"] == "derived" and nuevo["benchmark_id"] == bench
    assert nuevo["level"] == "rx" and nuevo["capped"] is False
    assert nuevo["achieved_on"].isoformat() == "2026-10-21"
    assert nuevo["created_by"] == coach.id and nuevo["invalidated_at"] is None
    assert nuevo["movement_id"] is None and nuevo["value_g"] is None
    assert (nuevo["rounds"], nuevo["reps"], nuevo["load_g"]) == (None, None, None)
    assert next(f for f in filas if f["seconds"] == 260)["result_id"] == primero


async def test_270_s_sobre_260_s_no_crea(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await _escena_time(session)
    bench = await _benchmark(session, e)
    ayer = await _wod_de(session, e, bench, "2026-10-20")
    hoy = await _wod_de(session, e, bench, "2026-10-21")
    h = cabeceras(await usuario_real("coach"))
    await _tiempo(app_http, h, e, ayer, 260)

    await _tiempo(app_http, h, e, hoy, 270)

    assert [f["seconds"] for f in _del_benchmark(await records_de(session, e.socio_id))] == [260]


async def test_el_empate_no_crea_otro_record(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await _escena_time(session)
    bench = await _benchmark(session, e)
    ayer = await _wod_de(session, e, bench, "2026-10-20")
    hoy = await _wod_de(session, e, bench, "2026-10-21")
    h = cabeceras(await usuario_real("coach"))
    await _tiempo(app_http, h, e, ayer, 260)

    await _tiempo(app_http, h, e, hoy, 260)

    assert len(_del_benchmark(await records_de(session, e.socio_id))) == 1


async def test_dos_wods_con_el_mismo_benchmark_son_el_mismo_benchmark(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    """Un WOD de otro benchmark es otro objetivo: su primera marca crea, sin importar la otra."""
    e = await _escena_time(session)
    uno = await _benchmark(session, e)
    otro = await _benchmark(session, e)
    wod_uno_a = await _wod_de(session, e, uno, "2026-10-19")
    wod_uno_b = await _wod_de(session, e, uno, "2026-10-20")
    wod_otro = await _wod_de(session, e, otro, "2026-10-21")
    h = cabeceras(await usuario_real("coach"))
    await _tiempo(app_http, h, e, wod_uno_a, 200)
    await _tiempo(app_http, h, e, wod_uno_b, 210)  # peor en el mismo benchmark: no crea
    await _tiempo(app_http, h, e, wod_otro, 400)  # otro benchmark: primera marca, crea

    filas = _del_benchmark(await records_de(session, e.socio_id))

    assert sorted((f["benchmark_id"], f["seconds"]) for f in filas) == sorted(
        [(uno, 200), (otro, 400)]
    )


async def test_un_wod_sin_benchmark_no_deja_record_de_benchmark(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await _escena_time(session)
    h = cabeceras(await usuario_real("coach"))

    await _tiempo(app_http, h, e, e.wod_id, 245)

    assert await records_de(session, e.socio_id) == []


async def test_un_capped_es_el_primer_record_y_quien_termino_lo_supera(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await _escena_time(session)
    bench = await _benchmark(session, e)
    d1 = await _wod_de(session, e, bench, "2026-10-19")
    d2 = await _wod_de(session, e, bench, "2026-10-20")
    d3 = await _wod_de(session, e, bench, "2026-10-21")
    h = cabeceras(await usuario_real("coach"))

    _id_de(await poner(app_http, h, e, wod_id=d1, load_g=None, capped=True, reps=30))
    primero = _del_benchmark(await records_de(session, e.socio_id))
    assert [(f["capped"], f["seconds"], f["reps"]) for f in primero] == [(True, 600, 30)]

    await _tiempo(app_http, h, e, d2, 599)  # terminó: supera al capped
    _id_de(await poner(app_http, h, e, wod_id=d3, load_g=None, capped=True, reps=45))

    filas = _del_benchmark(await records_de(session, e.socio_id))
    assert sorted((f["capped"], f["seconds"], f["reps"]) for f in filas) == [
        (False, 599, None),
        (True, 600, 30),
    ]


async def test_un_benchmark_de_carga_con_principal_crea_los_dos_records(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena_carga(session)
    bench = await _benchmark(session, e, "load")
    wod = await _wod_de(session, e, bench, "2026-10-18", "load")
    coach = await usuario_real("coach")
    h = cabeceras(coach)

    resultado = _id_de(await poner(app_http, h, e, wod_id=wod, load_g=100_000))

    filas = await records_de(session, e.socio_id)
    rm = next(f for f in filas if f["kind"] == "rm")
    marca = next(f for f in filas if f["kind"] == "benchmark")
    assert len(filas) == 2
    assert (rm["value_g"], rm["movement_id"], rm["result_id"]) == (
        100_000,
        e.movimientos[0],
        resultado,
    )
    assert (marca["load_g"], marca["benchmark_id"], marca["result_id"]) == (
        100_000,
        bench,
        resultado,
    )
    assert marca["level"] == "rx" and marca["value_g"] is None and marca["movement_id"] is None
    assert rm["created_by"] == coach.id == marca["created_by"]


async def test_cada_record_de_un_benchmark_de_carga_compara_con_su_propio_vigente(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    """RM ya en 120 kg (WOD suelto); el benchmark en 100 kg crea solo el de benchmark."""
    e = await escena_carga(session)
    suelto = await wod_extra(session, e, "2026-10-17", "Suelto carga")
    bench = await _benchmark(session, e, "load")
    wod = await _wod_de(session, e, bench, "2026-10-18", "load")
    h = cabeceras(await usuario_real("coach"))
    _id_de(await poner(app_http, h, e, wod_id=suelto, load_g=120_000))

    _id_de(await poner(app_http, h, e, wod_id=wod, load_g=100_000))

    filas = await records_de(session, e.socio_id)
    assert sorted((f["kind"], f["value_g"] or f["load_g"]) for f in filas) == [
        ("benchmark", 100_000),
        ("rm", 120_000),
    ]


# Fallo blando y savepoint por récord (S9-D58) ----------------------------------------------------


async def _falla_en_benchmark(evento: PersonalRecordSet, sesion: AsyncSession) -> None:
    if evento.kind == "benchmark":
        raise RuntimeError("fallo forzado en el récord de benchmark")


async def test_el_fallo_en_benchmark_es_blando_y_no_deja_record(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    alertas: AlertasCapturadas,
) -> None:
    e = await _escena_time(session)
    bench = await _benchmark(session, e)
    wod = await _wod_de(session, e, bench, "2026-10-21")
    h = cabeceras(await usuario_real("coach"))
    events.subscribe(PersonalRecordSet, _falla_en_benchmark)

    resultado = await poner(app_http, h, e, wod_id=wod, load_g=None, seconds=245)

    assert resultado.status_code == 201, resultado.text
    assert await _resultados(session, e.socio_id) == 1
    assert await records_de(session, e.socio_id) == []
    assert alertas.de("athletes_derive_skipped") == [{"error_type": "RuntimeError"}]


async def test_un_fallo_en_el_segundo_record_no_deshace_el_primero_ni_el_resultado(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    alertas: AlertasCapturadas,
) -> None:
    e = await escena_carga(session)
    bench = await _benchmark(session, e, "load")
    wod = await _wod_de(session, e, bench, "2026-10-18", "load")
    h = cabeceras(await usuario_real("coach"))
    events.subscribe(PersonalRecordSet, _falla_en_benchmark)

    resultado = await poner(app_http, h, e, wod_id=wod, load_g=100_000)

    assert resultado.status_code == 201, resultado.text
    assert await _resultados(session, e.socio_id) == 1
    filas = await records_de(session, e.socio_id)
    assert [(f["kind"], f["value_g"]) for f in filas] == [("rm", 100_000)]
    assert alertas.de("athletes_derive_skipped") == [{"error_type": "RuntimeError"}]


async def test_un_fallo_en_el_primer_record_no_impide_el_de_benchmark(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    alertas: AlertasCapturadas,
) -> None:
    e = await escena_carga(session)
    bench = await _benchmark(session, e, "load")
    wod = await _wod_de(session, e, bench, "2026-10-18", "load")
    h = cabeceras(await usuario_real("coach"))

    async def falla_en_rm(evento: PersonalRecordSet, sesion: AsyncSession) -> None:
        if evento.kind == "rm":
            raise RuntimeError("fallo forzado en el RM")

    events.subscribe(PersonalRecordSet, falla_en_rm)

    resultado = await poner(app_http, h, e, wod_id=wod, load_g=100_000)

    assert resultado.status_code == 201, resultado.text
    filas = await records_de(session, e.socio_id)
    assert [(f["kind"], f["load_g"]) for f in filas] == [("benchmark", 100_000)]
    assert alertas.de("athletes_derive_skipped") == [{"error_type": "RuntimeError"}]


async def test_base_ocupada_en_el_benchmark_da_503_y_no_guarda_ni_el_rm(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    alertas: AlertasCapturadas,
) -> None:
    e = await escena_carga(session)
    bench = await _benchmark(session, e, "load")
    wod = await _wod_de(session, e, bench, "2026-10-18", "load")
    h = cabeceras(await usuario_real("coach"))

    async def ocupado(evento: PersonalRecordSet, sesion: AsyncSession) -> None:
        if evento.kind == "benchmark":
            raise DatabaseBusy()

    events.subscribe(PersonalRecordSet, ocupado)

    r = await poner(app_http, h, e, wod_id=wod, load_g=100_000)

    assert r.status_code == 503 and r.json()["error"]["code"] == "busy", r.text
    assert await _resultados(session, e.socio_id) == 0
    assert await records_de(session, e.socio_id) == []
    assert alertas.de("athletes_derive_skipped") == []


async def test_la_doble_emision_del_benchmark_es_un_no_op_sin_alerta(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    alertas: AlertasCapturadas,
) -> None:
    e = await _escena_time(session)
    bench = await _benchmark(session, e)
    wod = await _wod_de(session, e, bench, "2026-10-21")
    h = cabeceras(await usuario_real("coach"))
    resultado = await _tiempo(app_http, h, e, wod, 245)
    assert len(_del_benchmark(await records_de(session, e.socio_id))) == 1

    await events.emit(
        WodResultValidated(result_id=resultado, member_id=e.socio_id, wod_id=wod), session
    )

    assert len(_del_benchmark(await records_de(session, e.socio_id))) == 1
    assert alertas.de("athletes_derive_skipped") == []


# Presupuesto de sentencias (S9-D30) --------------------------------------------------------------


async def test_presupuesto_de_sentencias_del_benchmark(session: AsyncSession) -> None:
    """Un benchmark de tiempo suma 4 (como el RM: lectura del vigente e INSERT) y uno de carga con
    principal suma 6 (a lo sumo, S9-D30), contra el mismo registro sin el handler suscrito."""
    tablas = ("athletes.", "results.", "wods.")

    async def medir(score_type: str, dia: str, *, con: bool, **marca: Any) -> int:
        esc = await escena(
            session,
            score_type=score_type,
            time_cap_s=None if score_type == "load" else 600,
            fecha=dia,
            con_clase=False,
        )
        bench = await _benchmark(session, esc, score_type)
        wod = await _wod_de(session, esc, bench, "2026-09-" + dia[-2:], score_type)
        quitados: list[Any] = []
        if not con:
            suscritos = events._subscribers.get(WodResultValidated, [])
            quitados = [x for x in suscritos if x is derive.on_wod_result_validated]
            for x in quitados:
                suscritos.remove(x)
        try:
            with contar_sentencias(session, tablas) as vistas:
                await registrar(session, esc, wod_id=wod, **marca)
        finally:
            for x in quitados:
                events.subscribe(WodResultValidated, x)
        return len(vistas)

    con_t = await medir("time", "2026-10-10", con=True, seconds=245)
    sin_t = await medir("time", "2026-10-11", con=False, seconds=245)
    assert con_t - sin_t == 4
    con_l = await medir("load", "2026-10-12", con=True, load_g=100_000, seconds=None)
    sin_l = await medir("load", "2026-10-13", con=False, load_g=100_000, seconds=None)
    assert con_l - sin_l == 6

"""Revisiones de S9-B3 (seguridad y base de datos; S9-D57): el savepoint envuelve TODO el handler.

Un bug de Python o un `DBAPIError` no ocupado en cualquier lectura o regla es fallo BLANDO (201 +
alerta sin ids); `DatabaseBusy`, `EventDepthExceeded` y «base ocupada» se re-lanzan; un 23514 no se
confunde con la doble emisión (23505 de `uq_personal_records_result_kind`). Además: planes de las
dos lecturas nuevas, ausencia de candados en ejecución y presupuesto exacto de sentencias.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.db import DatabaseBusy
from app.core.events import EventDepthExceeded
from app.modules.athletes import derive, queries
from app.modules.athletes.events import PersonalRecordSet
from app.modules.results.events import WodResultValidated
from app.modules.wods import service as wods_service
from tests.athletes._apoyo_derivar import (
    AlertasCapturadas,
    contar_sentencias,
    escena_carga,
    poner,
    records_de,
)
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.explain import capturar_sql
from tests.results._apoyo import escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def _resultados(session: AsyncSession, member_id: Any) -> int:
    return int(
        await session.scalar(
            text("SELECT count(*) FROM results.wod_results WHERE member_id = :m"), {"m": member_id}
        )
        or 0
    )


@pytest.mark.parametrize("blanco", ["derive_rm", "current_rm"])
async def test_una_regla_o_lectura_que_lanza_es_fallo_blando(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    alertas: AlertasCapturadas,
    monkeypatch: pytest.MonkeyPatch,
    blanco: str,
) -> None:
    e = await escena_carga(session)
    h = cabeceras(await usuario_real("coach"))

    def roto(*_a: Any, **_k: Any) -> Any:
        raise ValueError("bug de python")

    async def roto_async(*_a: Any, **_k: Any) -> Any:
        raise ValueError("bug de python")

    monkeypatch.setattr(derive, blanco, roto if blanco == "derive_rm" else roto_async)

    r = await poner(app_http, h, e, load_g=100_000)

    assert r.status_code == 201, r.text
    assert await _resultados(session, e.socio_id) == 1
    assert await records_de(session, e.socio_id) == []
    assert alertas.de("athletes_derive_skipped") == [{"error_type": "ValueError"}]


async def test_un_dbapierror_real_no_ocupado_en_una_lectura_es_blando_y_la_sesion_sigue(
    session: AsyncSession, alertas: AlertasCapturadas, monkeypatch: pytest.MonkeyPatch
) -> None:
    """42P01 real (tabla inexistente) dentro de `get_mark`: aborta la transacción salvo que un
    savepoint la envuelva. La misma transacción escribe y confirma después."""
    e = await escena_carga(session)

    async def lectura_rota(sesion: AsyncSession, _id: Any) -> Any:
        await sesion.execute(text("SELECT 1 FROM athletes.no_existe"))

    monkeypatch.setattr(derive.results_service, "get_mark", lectura_rota)

    await registrar(session, e, load_g=100_000, seconds=None)
    await session.commit()

    assert alertas.de("athletes_derive_skipped") == [{"error_type": "ProgrammingError"}]
    assert await records_de(session, e.socio_id) == []
    assert await _resultados(session, e.socio_id) == 1
    assert await session.scalar(text("SELECT 1")) == 1


async def test_un_programmingerror_simulado_en_get_mark_es_blando(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    alertas: AlertasCapturadas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    e = await escena_carga(session)
    h = cabeceras(await usuario_real("coach"))

    async def get_mark_roto(*_a: Any) -> Any:
        raise ProgrammingError("SELECT 1", {}, Exception("42501 permiso denegado"))

    monkeypatch.setattr(derive.results_service, "get_mark", get_mark_roto)

    r = await poner(app_http, h, e, load_g=100_000)

    assert r.status_code == 201, r.text
    assert alertas.de("athletes_derive_skipped") == [{"error_type": "ProgrammingError"}]


async def test_database_busy_de_un_suscriptor_sale_como_503_y_no_se_omite(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    alertas: AlertasCapturadas,
) -> None:
    e = await escena_carga(session)
    h = cabeceras(await usuario_real("coach"))

    async def ocupado(evento: PersonalRecordSet, sesion: AsyncSession) -> None:
        raise DatabaseBusy()

    events.subscribe(PersonalRecordSet, ocupado)

    r = await poner(app_http, h, e, load_g=100_000)

    assert r.status_code == 503 and r.json()["error"]["code"] == "busy", r.text
    assert alertas.de("athletes_derive_skipped") == []


async def test_event_depth_exceeded_se_relanza(
    session: AsyncSession, alertas: AlertasCapturadas
) -> None:
    e = await escena_carga(session)

    async def profundo(evento: PersonalRecordSet, sesion: AsyncSession) -> None:
        raise EventDepthExceeded("demasiado profundo")

    events.subscribe(PersonalRecordSet, profundo)

    with pytest.raises(EventDepthExceeded):
        await registrar(session, e, load_g=100_000, seconds=None)

    assert alertas.de("athletes_derive_skipped") == []


async def test_un_23514_alerta_y_no_se_confunde_con_la_doble_emision(
    session: AsyncSession, alertas: AlertasCapturadas, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`rm_shape` violada (un RM con `level`): IntegrityError 23514, fallo blando CON alerta."""
    e = await escena_carga(session)
    original = derive._record_of

    def deforme(*a: Any, **k: Any) -> Any:
        registro = original(*a, **k)
        registro.level = "rx"
        return registro

    monkeypatch.setattr(derive, "_record_of", deforme)

    await registrar(session, e, load_g=100_000, seconds=None)

    assert alertas.de("athletes_derive_skipped") == [{"error_type": "IntegrityError"}]
    assert await records_de(session, e.socio_id) == []
    assert await session.scalar(text("SELECT 1")) == 1


async def test_validated_by_nulo_sale_con_aviso_y_ids(
    session: AsyncSession, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = await escena_carga(session)
    salida = await registrar(session, e, load_g=100_000, seconds=None)
    real = derive.results_service.get_mark

    async def sin_validador(sesion: AsyncSession, rid: Any) -> Any:
        marca = await real(sesion, rid)
        return replace(marca, validated_by=None)

    monkeypatch.setattr(derive.results_service, "get_mark", sin_validador)
    evento = WodResultValidated(result_id=salida.id, member_id=e.socio_id, wod_id=e.wod_id)

    with caplog.at_level(logging.WARNING):
        await events.emit(evento, session)

    textos = [
        r.getMessage() + " " + " ".join(str(v) for v in r.__dict__.values()) for r in caplog.records
    ]
    assert any("sin validador" in t and str(salida.id) in t for t in textos)


async def test_el_handler_no_emite_candados_en_ejecucion(session: AsyncSession) -> None:
    """Sentencias desde que entra el handler de derivación: sin FOR UPDATE, FOR SHARE ni
    `pg_advisory` (las de `record.py` anteriores no cuentan)."""
    e = await escena_carga(session)
    abierto: list[bool] = []

    async def marca(evento: WodResultValidated, sesion: AsyncSession) -> None:
        abierto.append(True)

    suscritos = events._subscribers[WodResultValidated]
    suscritos.insert(0, marca)  # corre justo antes del handler de `athletes`
    vistas: list[str] = []
    destino = session.sync_session.get_bind()

    def anotar(_c: Any, _cur: Any, sql: str, *_a: Any) -> None:
        if abierto:
            vistas.append(sql.upper())

    sa_event.listen(destino, "before_cursor_execute", anotar)
    try:
        await registrar(session, e, load_g=100_000, seconds=None)
    finally:
        sa_event.remove(destino, "before_cursor_execute", anotar)
        suscritos.remove(marca)

    assert any("PERSONAL_RECORDS" in s for s in vistas), "el handler sí escribió"
    # El único candado asesor es el de la cadena de auditoría (`core/audit`, al hacer `flush`
    # del récord): va al final del orden de candados (S9-D7) y no lo pide el handler.
    asesores = [s for s in vistas if "PG_ADVISORY" in s]
    assert len(asesores) <= 1, asesores
    for s in vistas:
        assert "FOR UPDATE" not in s and "FOR SHARE" not in s, s


async def test_presupuesto_exacto_de_sentencias(session: AsyncSession) -> None:
    """S9-D30/D57: 2 sin récord posible y 4 con derivación (el contador excluye SAVEPOINT y
    RELEASE: los viajes reales suman esos dos también sin récord)."""
    tablas = ("athletes.", "results.", "wods.")

    async def medir(score_type: str, dia: str, *, con: bool, **marca: Any) -> int:
        esc = await escena(
            session,
            score_type=score_type,
            time_cap_s=None if score_type == "load" else 600,
            fecha=dia,
            con_clase=False,
        )
        quitados: list[Any] = []
        if not con:
            suscritos = events._subscribers.get(WodResultValidated, [])
            quitados = [x for x in suscritos if x is derive.on_wod_result_validated]
            for x in quitados:
                suscritos.remove(x)
        try:
            with contar_sentencias(session, tablas) as vistas:
                await registrar(session, esc, **marca)
        finally:
            for x in quitados:
                events.subscribe(WodResultValidated, x)
        return len(vistas)

    sin = await medir("time", "2026-10-10", con=True, seconds=300)
    base_sin = await medir("time", "2026-10-11", con=False, seconds=300)
    assert sin - base_sin == 2
    con = await medir("load", "2026-10-12", con=True, load_g=100_000, seconds=None)
    base_con = await medir("load", "2026-10-13", con=False, load_g=100_000, seconds=None)
    assert con - base_con == 4


async def _plan_generico(session: AsyncSession, sql: str, parametros: int) -> str:
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    await session.execute(text("SET LOCAL plan_cache_mode = force_generic_plan"))
    conexion = await session.connection()
    nombre = f"p_{uuid4().hex[:8]}"
    await conexion.exec_driver_sql(f"PREPARE {nombre} AS {sql}")
    argumentos = ", ".join(f"'{uuid4()}'" for _ in range(parametros))
    filas = await conexion.exec_driver_sql(f"EXPLAIN EXECUTE {nombre}({argumentos})")
    return "\n".join(str(f[0]) for f in filas.all())


async def test_plan_de_current_rm_usa_ix_personal_records_rm(session: AsyncSession) -> None:
    with capturar_sql(session, "athletes.personal_records") as vistas:
        await queries.current_rm(session, uuid4(), uuid4())
    sql, parametros = vistas[0]

    plan = await _plan_generico(session, sql, len(parametros))

    assert "ix_personal_records_rm" in plan, plan
    assert "Seq Scan" not in plan, plan


async def test_plan_de_record_meta_for_usa_uq_wod_movements_primary(
    session: AsyncSession,
) -> None:
    with capturar_sql(session, "wods.wods") as vistas:
        await wods_service.record_meta_for(session, [uuid4()])
    sql, parametros = vistas[0]

    plan = await _plan_generico(session, sql, len(parametros))

    assert "uq_wod_movements_primary" in plan, plan
    assert "Seq Scan" not in plan, plan

"""Revisión de seguridad de S9-B4 (S9-D58, S9-D59): cobertura de los tres tramos del handler.

Un WOD `load` con principal y benchmark crea DOS récords (RM primero, benchmark después). Se prueba
que un fallo del tramo benchmark no deshace el RM ni el resultado, que lo «ocupado» y lo de
conexión se re-lanzan, que la auditoría y la cadena quedan sanas, que una regla que lanza no omite
al otro récord y que la marca debe ser del benchmark del WOD.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event as sa_event
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.audit_verify import run_verification
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.events import EventDepthExceeded
from app.modules.athletes import derive
from app.modules.athletes.events import PersonalRecordSet
from app.modules.results.events import WodResultValidated
from tests.athletes._apoyo_derivar import AlertasCapturadas, escena_carga, records_de
from tests.athletes.test_derive_benchmark_service import (
    _benchmark,
    _del_benchmark,
    _falla_en_benchmark,
    _resultados,
    _wod_de,
)
from tests.results._apoyo import Escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def _escena(session: AsyncSession) -> tuple[Escena, UUID, UUID]:
    """WOD `load` con principal y benchmark `load`: el resultado deriva RM y benchmark."""
    e = await escena_carga(session)
    bench = await _benchmark(session, e, "load")
    wod = await _wod_de(session, e, bench, "2026-10-18", "load")
    return e, bench, wod


def _tipos(filas: list[dict[str, Any]]) -> list[tuple[str, int | None]]:
    return sorted((f["kind"], f["value_g"] or f["load_g"]) for f in filas)


# MEDIUM-1 (a): fallos no ocupados en el tramo benchmark ----------------------------------------


async def test_un_dbapierror_real_en_el_tramo_benchmark_deja_el_rm_y_la_sesion_usable(
    session: AsyncSession, alertas: AlertasCapturadas, monkeypatch: pytest.MonkeyPatch
) -> None:
    e, _bench, wod = await _escena(session)

    async def lectura_rota(*_a: Any, **_k: Any) -> Any:
        await session.execute(text("SELECT 1 FROM athletes.no_existe"))  # 42P01 real

    monkeypatch.setattr(derive, "current_benchmark", lectura_rota)

    await registrar(session, e, wod_id=wod, load_g=100_000, seconds=None)
    await session.commit()  # la misma transacción confirma tras el fallo blando

    assert _tipos(await records_de(session, e.socio_id)) == [("rm", 100_000)]
    assert await _resultados(session, e.socio_id) == 1
    assert alertas.de("athletes_derive_skipped") == [{"error_type": "ProgrammingError"}]
    assert await session.scalar(text("SELECT 1")) == 1


async def test_un_23514_en_el_tramo_benchmark_deja_el_rm(
    session: AsyncSession, alertas: AlertasCapturadas, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`benchmark_shape` violada (un benchmark con `value_g`): 23514 solo del segundo récord."""
    e, _bench, wod = await _escena(session)
    original = derive._record_of

    def deforme(draft: Any, *a: Any, **k: Any) -> Any:
        registro = original(draft, *a, **k)
        if draft.kind == "benchmark":
            registro.value_g = 5
        return registro

    monkeypatch.setattr(derive, "_record_of", deforme)

    await registrar(session, e, wod_id=wod, load_g=100_000, seconds=None)
    await session.commit()

    assert _tipos(await records_de(session, e.socio_id)) == [("rm", 100_000)]
    assert alertas.de("athletes_derive_skipped") == [{"error_type": "IntegrityError"}]
    assert await session.scalar(text("SELECT 1")) == 1


# MEDIUM-1 (b): lo que se re-lanza desde el tramo benchmark ---------------------------------------


async def test_event_depth_exceeded_en_el_tramo_benchmark_se_relanza(
    session: AsyncSession, alertas: AlertasCapturadas
) -> None:
    e, _bench, wod = await _escena(session)

    async def profundo(evento: PersonalRecordSet, sesion: AsyncSession) -> None:
        if evento.kind == "benchmark":
            raise EventDepthExceeded("demasiado profundo")

    events.subscribe(PersonalRecordSet, profundo)

    with pytest.raises(EventDepthExceeded):
        await registrar(session, e, wod_id=wod, load_g=100_000, seconds=None)

    assert alertas.de("athletes_derive_skipped") == []


# MEDIUM-1 (c): auditoría y cadena ----------------------------------------------------------------


async def test_tras_un_fallo_blando_del_benchmark_queda_una_sola_auditoria_y_la_cadena_verifica(
    session: AsyncSession, alertas: AlertasCapturadas
) -> None:
    e, _bench, wod = await _escena(session)
    events.subscribe(PersonalRecordSet, _falla_en_benchmark)
    cuenta = text(
        "SELECT count(*) FROM audit.audit_log "
        "WHERE table_name = 'athletes.personal_records' AND action = 'insert'"
    )
    antes = await session.scalar(cuenta)

    await registrar(session, e, wod_id=wod, load_g=100_000, seconds=None)
    await session.commit()

    filas = await records_de(session, e.socio_id)
    assert [f["kind"] for f in filas] == ["rm"]
    assert await session.scalar(cuenta) == (antes or 0) + 1, "solo la fila `insert` del RM"
    de_rm = await session.scalar(
        text(
            "SELECT count(*) FROM audit.audit_log WHERE table_name = 'athletes.personal_records' "
            "AND action = 'insert' AND record_id = :i"
        ),
        {"i": filas[0]["id"]},
    )
    assert de_rm == 1
    with actor_scope(SYSTEM_USER_ID):
        vista = await run_verification(session, source="cli", by=SYSTEM_USER_ID)
    assert vista.ok is True


# MEDIUM-1 (d): sin candados con dos récords ------------------------------------------------------


async def test_el_handler_con_dos_records_no_pide_candados_propios(session: AsyncSession) -> None:
    e, _bench, wod = await _escena(session)
    abierto: list[bool] = []

    async def marca(evento: WodResultValidated, sesion: AsyncSession) -> None:
        abierto.append(True)

    suscritos = events._subscribers[WodResultValidated]
    suscritos.insert(0, marca)
    vistas: list[str] = []
    destino = session.sync_session.get_bind()

    def anotar(_c: Any, _cur: Any, sql: str, *_a: Any) -> None:
        if abierto:
            vistas.append(sql.upper())

    sa_event.listen(destino, "before_cursor_execute", anotar)
    try:
        await registrar(session, e, wod_id=wod, load_g=100_000, seconds=None)
    finally:
        sa_event.remove(destino, "before_cursor_execute", anotar)
        suscritos.remove(marca)

    assert _tipos(await records_de(session, e.socio_id)) == [
        ("benchmark", 100_000),
        ("rm", 100_000),
    ]
    # El único candado asesor es el de la cadena de auditoría (`core/audit`, al hacer `flush`),
    # el mismo para los dos récords; el handler no pide ningún otro.
    assert len({s for s in vistas if "PG_ADVISORY" in s}) <= 1
    for s in vistas:
        assert "FOR UPDATE" not in s and "FOR SHARE" not in s, s


# LOW-2: una regla que lanza no omite al otro récord ---------------------------------------------


async def test_una_regla_de_benchmark_que_lanza_no_omite_el_rm(
    session: AsyncSession, alertas: AlertasCapturadas, monkeypatch: pytest.MonkeyPatch
) -> None:
    e, _bench, wod = await _escena(session)

    def roto(*_a: Any, **_k: Any) -> Any:
        raise ValueError("bug de python")

    monkeypatch.setattr(derive, "derive_benchmark", roto)

    await registrar(session, e, wod_id=wod, load_g=100_000, seconds=None)

    assert _tipos(await records_de(session, e.socio_id)) == [("rm", 100_000)]
    assert alertas.de("athletes_derive_skipped") == [{"error_type": "ValueError"}]


# LOW-4: la marca debe ser del benchmark del WOD --------------------------------------------------


async def test_una_marca_de_otro_benchmark_no_deriva_benchmark_y_avisa_con_ids(
    session: AsyncSession,
    alertas: AlertasCapturadas,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    e, _bench, wod = await _escena(session)
    original = derive.results_service.get_mark

    async def de_otro(sesion: AsyncSession, result_id: UUID) -> Any:
        marca = await original(sesion, result_id)
        return None if marca is None else replace(marca, benchmark_id=uuid4())

    monkeypatch.setattr(derive.results_service, "get_mark", de_otro)

    with caplog.at_level(logging.WARNING):
        salida = await registrar(session, e, wod_id=wod, load_g=100_000, seconds=None)

    assert _tipos(await records_de(session, e.socio_id)) == [("rm", 100_000)]
    assert _del_benchmark(await records_de(session, e.socio_id)) == []
    assert alertas.de("athletes_derive_skipped") == []
    texto = "\n".join(
        [
            r.getMessage() + " " + " ".join(str(v) for v in r.__dict__.values())
            for r in caplog.records
        ]
    )
    assert "no es del benchmark del WOD" in texto
    assert str(salida.id) in texto and str(e.socio_id) in texto and str(wod) in texto


# LOW-5: 0 g no es récord de benchmark ------------------------------------------------------------


async def test_una_carga_de_cero_gramos_no_deja_ningun_record(session: AsyncSession) -> None:
    e, _bench, wod = await _escena(session)

    await registrar(session, e, wod_id=wod, load_g=0, seconds=None)

    assert await records_de(session, e.socio_id) == []


# LOW-6: un fallo de conexión se re-lanza y no sigue con los tramos restantes ---------------------


def _conexion_caida() -> BaseException:
    return DBAPIError("SELECT 1", {}, Exception("conexión caída"), connection_invalidated=True)


@pytest.mark.parametrize("fabrica", [ConnectionRefusedError, _conexion_caida])
async def test_un_fallo_de_conexion_en_el_rm_se_relanza_sin_alertas_ni_mas_tramos(
    session: AsyncSession,
    alertas: AlertasCapturadas,
    monkeypatch: pytest.MonkeyPatch,
    fabrica: Any,
) -> None:
    e, _bench, wod = await _escena(session)
    llamadas: list[str] = []

    async def cae(*_a: Any, **_k: Any) -> Any:
        raise fabrica()

    async def espia(*_a: Any, **_k: Any) -> Any:
        llamadas.append("benchmark")

    monkeypatch.setattr(derive, "current_rm", cae)
    monkeypatch.setattr(derive, "current_benchmark", espia)

    with pytest.raises((ConnectionRefusedError, DBAPIError)):
        await registrar(session, e, wod_id=wod, load_g=100_000, seconds=None)

    assert alertas.de("athletes_derive_skipped") == []
    assert llamadas == [], "no se sigue con el tramo de benchmark"

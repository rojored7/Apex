"""El handler de derivación no puede tumbar la tablet (S9-B3, H-2; S9-D30, S9-D42; enmienda 4).

Derivar falla en BLANDO: un fallo dentro del savepoint se revierte, se registra `derivación omitida`
(ids solo en el log), se alerta SIN ids y el resultado se confirma. Una alerta que falla nunca
revierte el resultado. Solo «base ocupada» (SQLSTATE de `BUSY_SQLSTATES`) sale como 503 `busy`.

El fallo se fuerza con un suscriptor de `PersonalRecordSet`: el contrato (S9-D42) pone la emisión
DENTRO del savepoint, así que su excepción cae en el `except` del handler.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import db, events
from app.core.alerts import register_sink, unregister_sink
from app.core.audit_verify import run_verification
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.provider import configure_provider
from app.core.security import create_access_token, register_principal_loader
from app.modules.athletes import derive
from app.modules.athletes.events import PersonalRecordSet
from app.modules.results.events import WodResultRecorded
from tests.athletes._apoyo_derivar import (
    AlertasCapturadas,
    escena_carga,
    poner,
    records_de,
)
from tests.auth._sesion import ORIGEN
from tests.conftest import CLAVE_PRUEBA, Cabeceras, CrearUsuario
from tests.factories.users import make_user
from tests.results._apoyo import escena, registrar

BLANDO = pytest.mark.usefixtures("reloj", "bus_listo")


async def _fallo_forzado(evento: PersonalRecordSet, sesion: AsyncSession) -> None:
    raise RuntimeError("fallo forzado dentro del savepoint")


def _forzar_fallo() -> None:
    events.subscribe(PersonalRecordSet, _fallo_forzado)


def _ids_en_el_log(caplog: pytest.LogCaptureFixture) -> str:
    """Mensaje y `extra` de cada registro como un solo texto (los ids viajan en `extra`)."""
    piezas: list[str] = []
    for r in caplog.records:
        piezas.append(r.getMessage())
        piezas.extend(str(v) for k, v in r.__dict__.items() if k not in {"args", "msg"})
    return "\n".join(piezas)


async def _resultados(session: AsyncSession, member_id: UUID) -> int:
    return int(
        await session.scalar(
            text("SELECT count(*) FROM results.wod_results WHERE member_id = :m"), {"m": member_id}
        )
        or 0
    )


@BLANDO
async def test_un_fallo_al_derivar_no_revierte_el_resultado_y_alerta_sin_ids(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    alertas: AlertasCapturadas,
    caplog: pytest.LogCaptureFixture,
) -> None:
    e = await escena_carga(session)
    h = cabeceras(await usuario_real("coach"))
    _forzar_fallo()

    with caplog.at_level(logging.INFO):
        r = await poner(app_http, h, e, load_g=100_000)

    assert r.status_code == 201, r.text
    resultado_id = r.json()["id"]
    assert await _resultados(session, e.socio_id) == 1, "el resultado se confirma"
    assert await records_de(session, e.socio_id) == [], "el savepoint se revirtió"
    assert alertas.de("athletes_derive_skipped") == [{"error_type": "RuntimeError"}]
    texto = _ids_en_el_log(caplog)
    assert "derivación omitida" in texto
    assert resultado_id in texto and str(e.socio_id) in texto, "los ids van en el log"
    for _codigo, contexto in alertas.recibidas:
        assert resultado_id not in str(contexto) and str(e.socio_id) not in str(contexto)


@BLANDO
async def test_una_alerta_que_falla_no_revierte_el_resultado(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hallazgo 1: `alert` parcheado para lanzar `ValueError`; va en su propio `try`."""
    e = await escena_carga(session)
    h = cabeceras(await usuario_real("coach"))
    _forzar_fallo()
    llamadas: list[str] = []

    def alerta_rota(codigo: str, **contexto: object) -> None:
        llamadas.append(codigo)
        raise ValueError("la alerta falló")

    monkeypatch.setattr(derive, "alert", alerta_rota)

    r = await poner(app_http, h, e, load_g=100_000)

    assert llamadas == ["athletes_derive_skipped"], "la derivación sí intentó alertar"
    assert r.status_code == 201, r.text
    assert await _resultados(session, e.socio_id) == 1


class _SinkRoto:
    def __init__(self) -> None:
        self.llamadas = 0

    def send(self, code: str, context: Any) -> None:
        self.llamadas += 1
        raise OSError("canal caído")


@BLANDO
async def test_un_sink_que_lanza_no_revierte_el_resultado(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    e = await escena_carga(session)
    h = cabeceras(await usuario_real("coach"))
    _forzar_fallo()
    sink = _SinkRoto()
    register_sink(sink)
    try:
        r = await poner(app_http, h, e, load_g=100_000)
    finally:
        unregister_sink(sink)

    assert sink.llamadas == 1, "la derivación sí alertó"
    assert r.status_code == 201, r.text
    assert await _resultados(session, e.socio_id) == 1


@BLANDO
async def test_la_sesion_sigue_usable_y_la_cadena_de_auditoria_verifica(
    session: AsyncSession, alertas: AlertasCapturadas
) -> None:
    """Hallazgo 3: tras el savepoint revertido la misma transacción escribe y confirma; la fila de
    auditoría del resultado persiste, no queda la del récord omitido y la cadena verifica."""
    e = await escena_carga(session)
    _forzar_fallo()
    antes = await session.scalar(
        text("SELECT count(*) FROM audit.audit_log WHERE table_name = 'athletes.personal_records'")
    )

    salida = await registrar(session, e, load_g=100_000, seconds=None)
    await session.commit()  # la misma transacción confirma tras el fallo blando

    assert alertas.de("athletes_derive_skipped") == [{"error_type": "RuntimeError"}]
    de_resultado = await session.scalar(
        text(
            "SELECT count(*) FROM audit.audit_log "
            "WHERE table_name = 'results.wod_results' AND record_id = :i AND action = 'insert'"
        ),
        {"i": salida.id},
    )
    assert de_resultado == 1
    despues = await session.scalar(
        text("SELECT count(*) FROM audit.audit_log WHERE table_name = 'athletes.personal_records'")
    )
    assert despues == antes, "no queda auditoría del récord omitido"
    assert await session.scalar(text("SELECT 1")) == 1
    with actor_scope(SYSTEM_USER_ID):
        vista = await run_verification(session, source="cli", by=SYSTEM_USER_ID)
    assert vista.ok is True


@BLANDO
async def test_un_fallo_en_el_segundo_resultado_no_deshace_el_primer_record(
    session: AsyncSession, alertas: AlertasCapturadas
) -> None:
    """El fallo blando solo revierte SU savepoint: el RM del resultado anterior queda."""
    e = await escena_carga(session)
    await registrar(session, e, load_g=90_000, seconds=None)
    otro = await escena(
        session, score_type="load", time_cap_s=None, fecha="2026-10-20", con_clase=False
    )
    _forzar_fallo()

    await registrar(session, otro, load_g=95_000, seconds=None)

    assert [f["value_g"] for f in await records_de(session, e.socio_id)] == [90_000]
    assert alertas.de("athletes_derive_skipped") == [{"error_type": "RuntimeError"}]


# «Base ocupada» de verdad (hallazgo 2, enmienda 4) -----------------------------------------------


@pytest.fixture
async def app_real(
    seguridad: Settings,
    engine: AsyncEngine,
    bus_confirmado: Any,
    proveedor_local: LocalFileProvider,
    cargador_real: Any,
    reloj: FrozenClock,
) -> AsyncIterator[Any]:
    """La app real con el `get_session` real (commit real, sin override)."""
    from app.main import create_app

    aplicacion = create_app(seguridad, run_migrations_on_startup=False)
    register_principal_loader(cargador_real)
    configure_provider(proveedor_local)
    db.configure_sessionmaker(async_sessionmaker(engine, expire_on_commit=False))
    try:
        yield aplicacion
    finally:
        db.configure_sessionmaker(None)
        configure_provider(None)
        await db.dispose_engine()


async def test_base_ocupada_da_503_busy_sin_resultado_y_sin_alerta(
    app_real: Any,
    engine: AsyncEngine,
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    reloj: FrozenClock,
    alertas: AlertasCapturadas,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Un suscriptor de `WodResultRecorded` (se emite ANTES que `Validated`) inserta, desde OTRA
    conexión y sin confirmar, un récord con el mismo `(result_id, kind)`. El `INSERT` del handler
    espera ese único, choca con `lock_timeout` (55P03 real) y `PUT /results` responde 503 `busy`
    con `Retry-After: 1`: nada se guarda, ni resultado ni récord, y no hay alerta de derivación."""
    una, _otra = dos_sesiones
    e = await escena(una, score_type="load", time_cap_s=None, con_clase=False)
    coach = await make_user(una, role="coach", password=CLAVE_PRUEBA)
    token = create_access_token(coach.id, "coach", coach.member_id, reloj)
    headers = {"Authorization": f"Bearer {token}", "Origin": ORIGEN}
    socio_id, wod_id, movimiento = e.socio_id, e.wod_id, e.movimientos[0]
    una.expunge_all()
    insertado: list[UUID] = []

    async with engine.connect() as ajena:

        async def ocupar(evento: WodResultRecorded, sesion: AsyncSession) -> None:
            await sesion.execute(text("SET LOCAL lock_timeout = '300ms'"))
            await ajena.execute(
                text(
                    "INSERT INTO athletes.personal_records (id, created_by, member_id, kind, "
                    "movement_id, value_g, achieved_on, source, result_id, wod_id) VALUES "
                    "(:i, :c, :m, 'rm', :mov, 50000, DATE '2026-10-21', 'derived', :r, :w)"
                ),
                {
                    "i": uuid4(),
                    "c": SYSTEM_USER_ID,
                    "m": evento.member_id,
                    "mov": movimiento,
                    "r": evento.result_id,
                    "w": evento.wod_id,
                },
            )
            insertado.append(evento.result_id)

        events.subscribe(WodResultRecorded, ocupar)
        transporte = ASGITransport(app=app_real, raise_app_exceptions=False)
        try:
            async with AsyncClient(transport=transporte, base_url="http://t") as http:
                with caplog.at_level(logging.INFO):
                    r = await asyncio.wait_for(
                        http.put(
                            "/api/v1/results",
                            json={
                                "wod_id": str(wod_id),
                                "member_id": str(socio_id),
                                "level": "rx",
                                "load_g": 100_000,
                            },
                            headers=headers,
                        ),
                        timeout=30,
                    )
        finally:
            await ajena.rollback()
            handlers = events._subscribers.get(WodResultRecorded, [])
            if ocupar in handlers:
                handlers.remove(ocupar)

    assert insertado, (r.status_code, r.text)
    assert r.status_code == 503, r.text
    assert r.json()["error"]["code"] == "busy"
    assert r.headers["retry-after"] == "1"
    assert await _resultados(una, socio_id) == 0, "el resultado no se confirmó"
    assert await records_de(una, socio_id) == []
    assert alertas.de("athletes_derive_skipped") == []
    assert "derivación omitida" not in _ids_en_el_log(caplog)
    await una.rollback()

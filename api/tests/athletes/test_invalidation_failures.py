"""Dos políticas de fallo ante una invalidación (S9-B5, hallazgos 2 y 3; S9-D30, S9-D42, H-2).

- **Invalidar falla CERRADO** (S9-D30): un RM falso vigente no lo repara ningún comando. Si
  `_invalidate` falla, se revierte la corrección o la anulación entera: no queda resultado nuevo ni
  anulado y el récord anterior sigue vivo.
- **Reponer falla en BLANDO**: un fallo al reponer NO revierte la corrección; deja una alerta
  `athletes_derive_skipped` SIN ids, la sesión sigue usable, la invalidación ya hecha persiste con
  su fila de auditoría y la cadena de auditoría verifica.
- **«Base ocupada» (S9-D42)**: un `lock_timeout` REAL (55P03) dentro del savepoint de la reposición
  sale como 503 `busy` y no se confirma NADA (ni la corrección ni la invalidación).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core import events
from app.core.audit_verify import run_verification
from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.security import create_access_token
from app.modules.athletes import alerts, derive
from app.modules.results import service as results_service
from app.modules.results.events import WodResultRecorded
from tests.athletes._apoyo import auditoria_de_records
from tests.athletes._apoyo_derivar import AlertasCapturadas, poner, records_de, vigente_g
from tests.athletes._apoyo_invalidar import (
    anular_resultado,
    cargar,
    escena_serie,
    por_resultado,
    vivos,
    wod_en,
)
from tests.athletes.test_derive_soft_fail import app_real  # noqa: F401  (la app con commit real)
from tests.auth._sesion import ORIGEN
from tests.conftest import CLAVE_PRUEBA, CrearUsuario
from tests.factories.users import make_user
from tests.results._apoyo import Escena, escena

BLANDO = pytest.mark.usefixtures("reloj", "bus_listo")
REAL = pytest.mark.usefixtures("reloj")  # el commit real trae su propio bus (`bus_confirmado`)


async def _resultados(session: AsyncSession, member_id: UUID) -> int:
    return int(
        await session.scalar(
            text("SELECT count(*) FROM results.wod_results WHERE member_id = :m"), {"m": member_id}
        )
        or 0
    )


async def _vigentes(session: AsyncSession, member_id: UUID) -> int:
    return int(
        await session.scalar(
            text(
                "SELECT count(*) FROM results.wod_results WHERE member_id = :m AND is_current "
                "AND status = 'validated'"
            ),
            {"m": member_id},
        )
        or 0
    )


async def _roto(*_a: Any, **_k: Any) -> Any:
    raise RuntimeError("fallo forzado")


def _ids_en_el_log(caplog: pytest.LogCaptureFixture) -> str:
    piezas: list[str] = []
    for r in caplog.records:
        piezas.append(r.getMessage())
        piezas.extend(str(v) for k, v in r.__dict__.items() if k not in {"args", "msg"})
    return "\n".join(piezas)


@pytest.fixture
async def e(session: AsyncSession) -> Escena:
    return await escena_serie(session, "2026-10-12")


# Invalidar falla cerrado ----------------------------------------------------------------------


@BLANDO
async def test_un_fallo_al_invalidar_en_una_correccion_revierte_la_correccion(
    session: AsyncSession,
    e: Escena,
    alertas: AlertasCapturadas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    malo = await cargar(session, e, e.wod_id, 1_000_000)
    monkeypatch.setattr(derive, "_invalidate", _roto)

    with pytest.raises(RuntimeError, match="fallo forzado"):
        async with session.begin_nested():  # la transacción de la petición
            await cargar(session, e, e.wod_id, 100_000, anterior_id=malo.id)

    assert await _resultados(session, e.socio_id) == 1, "no queda el resultado nuevo"
    assert await _vigentes(session, e.socio_id) == 1, "el original sigue vigente"
    filas = await records_de(session, e.socio_id)
    assert vigente_g(filas) == 1_000_000 and len(filas) == 1
    assert alertas.de("athletes_derive_skipped") == [], "fallar cerrado no es un fallo blando"


@BLANDO
async def test_un_fallo_al_invalidar_en_una_anulacion_revierte_la_anulacion(
    session: AsyncSession,
    e: Escena,
    usuario_real: CrearUsuario,
    alertas: AlertasCapturadas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = await usuario_real("admin")
    r = await cargar(session, e, e.wod_id, 100_000)
    monkeypatch.setattr(derive, "_invalidate", _roto)

    with pytest.raises(RuntimeError, match="fallo forzado"):
        async with session.begin_nested():
            await anular_resultado(session, admin.id, r.id)

    estado = await session.scalar(
        text("SELECT status FROM results.wod_results WHERE id = :i"), {"i": r.id}
    )
    assert estado == "validated", "el resultado no quedó anulado"
    assert vigente_g(await records_de(session, e.socio_id)) == 100_000
    assert alertas.de("athletes_derive_skipped") == []


# Reponer falla en blando ----------------------------------------------------------------------


async def _hueco_de_tres(session: AsyncSession, e: Escena) -> tuple[UUID, UUID]:
    """1.000 kg erróneo (récord) y 95 kg (sin récord): devuelve el WOD y el resultado del error."""
    w_b = await wod_en(session, e, "2026-10-14", "B")
    malo = await cargar(session, e, w_b, 1_000_000)
    await cargar(session, e, await wod_en(session, e, "2026-10-15", "C"), 95_000)
    return w_b, malo.id


@BLANDO
async def test_un_fallo_al_reponer_no_revierte_la_correccion_y_alerta_sin_ids(
    session: AsyncSession,
    e: Escena,
    alertas: AlertasCapturadas,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w_b, malo_id = await _hueco_de_tres(session, e)
    monkeypatch.setattr(results_service, "member_marks", _roto)

    with caplog.at_level(logging.INFO):
        corregido = await cargar(session, e, w_b, 92_000, anterior_id=malo_id)

    assert await _vigentes(session, e.socio_id) == 2, "la corrección se confirma"
    filas = await records_de(session, e.socio_id)
    assert por_resultado(filas, malo_id)["invalidated_reason"] == "superseded"
    assert por_resultado(filas, corregido.id)["value_g"] == 92_000
    assert vigente_g(filas) == 92_000, "el 95 no se repuso"
    assert alertas.de("athletes_derive_skipped") == [{"error_type": "RuntimeError"}]
    assert alertas.de("athletes_restore_capped") == []
    texto = _ids_en_el_log(caplog)
    assert "derivación omitida" in texto and str(e.socio_id) in texto, "los ids van al log"
    for _codigo, contexto in alertas.recibidas:
        assert str(e.socio_id) not in str(contexto) and str(corregido.id) not in str(contexto)


@BLANDO
async def test_un_fallo_al_reponer_tras_anular_no_revierte_la_anulacion(
    session: AsyncSession,
    e: Escena,
    usuario_real: CrearUsuario,
    alertas: AlertasCapturadas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = await usuario_real("admin")
    cien = await cargar(session, e, e.wod_id, 100_000)
    await cargar(session, e, await wod_en(session, e, "2026-10-13", "A"), 60_000)
    monkeypatch.setattr(results_service, "member_marks", _roto)

    salida = await anular_resultado(session, admin.id, cien.id)

    assert salida.status == "voided"
    filas = await records_de(session, e.socio_id)
    assert por_resultado(filas, cien.id)["invalidated_reason"] == "voided"
    assert vivos(filas) == [], "no se repuso el 60"
    assert alertas.de("athletes_derive_skipped") == [{"error_type": "RuntimeError"}]


@BLANDO
async def test_tras_el_fallo_blando_la_sesion_sigue_usable_y_la_cadena_verifica(
    session: AsyncSession,
    e: Escena,
    alertas: AlertasCapturadas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w_b, malo_id = await _hueco_de_tres(session, e)
    record_malo = por_resultado(await records_de(session, e.socio_id), malo_id)["id"]
    monkeypatch.setattr(results_service, "member_marks", _roto)

    corregido = await cargar(session, e, w_b, 92_000, anterior_id=malo_id)
    await session.commit()  # la misma transacción confirma tras el fallo blando

    assert await session.scalar(text("SELECT 1")) == 1
    actualizaciones = [
        f for f in await auditoria_de_records(session, record_malo) if f["action"] == "update"
    ]
    assert len(actualizaciones) == 1, "la invalidación ya hecha persiste con su auditoría"
    assert actualizaciones[0]["after"]["invalidated_reason"] == "superseded"
    insertado = await session.scalar(
        text(
            "SELECT count(*) FROM audit.audit_log WHERE table_name = 'results.wod_results' "
            "AND record_id = :i AND action = 'insert'"
        ),
        {"i": corregido.id},
    )
    assert insertado == 1
    with actor_scope(SYSTEM_USER_ID):
        vista = await run_verification(session, source="cli", by=SYSTEM_USER_ID)
    assert vista.ok is True
    assert alertas.de("athletes_derive_skipped") == [{"error_type": "RuntimeError"}]


@BLANDO
async def test_una_alerta_que_falla_al_reponer_no_revierte_la_correccion(
    session: AsyncSession, e: Escena, monkeypatch: pytest.MonkeyPatch
) -> None:
    w_b, malo_id = await _hueco_de_tres(session, e)
    monkeypatch.setattr(results_service, "member_marks", _roto)

    llamadas: list[str] = []

    def alerta_registrada(codigo: str, **contexto: object) -> None:
        llamadas.append(codigo)
        raise ValueError("la alerta falló")

    monkeypatch.setattr(alerts, "alert", alerta_registrada)

    await cargar(session, e, w_b, 92_000, anterior_id=malo_id)

    assert llamadas == ["athletes_derive_skipped"], "la reposición sí intentó alertar"
    assert await _vigentes(session, e.socio_id) == 2


# «Base ocupada» de verdad dentro del savepoint de la reposición -------------------------------


@REAL
async def test_base_ocupada_al_reponer_da_503_busy_y_no_confirma_nada(
    app_real: Any,  # noqa: F811
    engine: AsyncEngine,
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    reloj: FrozenClock,
    alertas: AlertasCapturadas,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """100 kg en W1 (récord) y 40 kg en W2 (sin récord). Se corrige W1 a 30 kg: la reposición
    querría insertar el récord de los 40 kg. Un suscriptor de `WodResultRecorded` (se emite ANTES
    que `Validated`) inserta, desde OTRA conexión y sin confirmar, un récord con el mismo
    `(result_id, kind)` del de 40 kg y fija `lock_timeout` en 300 ms: el `INSERT` de la reposición
    espera ese único, choca con 55P03 REAL y `PUT /results` responde 503 `busy` con
    `Retry-After: 1`. No se confirma NADA: ni el resultado nuevo, ni la invalidación del de 100."""
    una, _otra = dos_sesiones
    e = await escena(una, score_type="load", time_cap_s=None, con_clase=False)
    w2 = await wod_en(una, e, "2026-10-20", "W2")
    r1 = await cargar(una, e, e.wod_id, 100_000)
    r2 = await cargar(una, e, w2, 40_000)
    await una.commit()
    coach = await make_user(una, role="coach", password=CLAVE_PRUEBA)
    token = create_access_token(coach.id, "coach", coach.member_id, reloj)
    headers = {"Authorization": f"Bearer {token}", "Origin": ORIGEN}
    socio_id, wod_id, movimiento = e.socio_id, e.wod_id, e.movimientos[0]
    antes = await records_de(una, socio_id)
    assert vigente_g(antes) == 100_000, "el récord del de 100 kg existe antes de corregir"
    una.expunge_all()
    insertado: list[UUID] = []

    async with engine.connect() as ajena:

        async def ocupar(evento: WodResultRecorded, sesion: AsyncSession) -> None:
            await sesion.execute(text("SET LOCAL lock_timeout = '300ms'"))
            await ajena.execute(
                text(
                    "INSERT INTO athletes.personal_records (id, created_by, member_id, kind, "
                    "movement_id, value_g, achieved_on, source, result_id, wod_id) VALUES "
                    "(:i, :c, :m, 'rm', :mov, 40000, DATE '2026-10-20', 'derived', :r, :w)"
                ),
                {
                    "i": uuid4(),
                    "c": SYSTEM_USER_ID,
                    "m": evento.member_id,
                    "mov": movimiento,
                    "r": r2.id,
                    "w": w2,
                },
            )
            insertado.append(r2.id)

        events.subscribe(WodResultRecorded, ocupar)
        transporte = ASGITransport(app=app_real, raise_app_exceptions=False)
        try:
            async with AsyncClient(transport=transporte, base_url="http://t") as http:
                with caplog.at_level(logging.INFO):
                    r = await asyncio.wait_for(
                        poner(
                            http,
                            headers,
                            e,
                            load_g=30_000,
                            supersedes_id=r1.id,
                        ),
                        timeout=30,
                    )
        finally:
            await ajena.rollback()
            handlers = events._subscribers.get(WodResultRecorded, [])
            if ocupar in handlers:
                handlers.remove(ocupar)

    assert wod_id == e.wod_id
    assert insertado, (r.status_code, r.text)
    assert r.status_code == 503, r.text
    assert r.json()["error"]["code"] == "busy"
    assert r.headers["retry-after"] == "1"
    assert await _resultados(una, socio_id) == 2, "el resultado nuevo no se confirmó"
    assert await _vigentes(una, socio_id) == 2
    filas = await records_de(una, socio_id)
    assert por_resultado(filas, r1.id)["invalidated_at"] is None, "la invalidación no se confirmó"
    assert vigente_g(filas) == 100_000
    assert alertas.de("athletes_derive_skipped") == [], "base ocupada no se omite en blando"
    assert alertas.de("athletes_restore_capped") == []
    await una.rollback()

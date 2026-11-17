"""La invalidación deja rastro en la auditoría (S9-B5, hallazgo 4; S9-D42, S9-D1 c).

Un `UPDATE` de Core no pasa por `after_flush` y quedaría sin fila de `audit_log`: `_invalidate`
escribe por ORM. Al corregir, `audit_log` tiene UNA fila `update` de `athletes.personal_records`
con el `record_id` del récord, el actor que corrigió y `subject_member_id` = el socio; al anular, lo
mismo con el admin como actor. El `after` trae `invalidated_reason` y ninguna medida del cuerpo
(`weight_g`, `height_cm`, `body_fat_pct`, `notes`). La reposición deja su `insert`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_verify import run_verification
from app.core.context import SYSTEM_USER_ID, actor_scope
from tests.athletes._apoyo import auditoria_de_records
from tests.athletes._apoyo_derivar import records_de
from tests.athletes._apoyo_invalidar import (
    anular_resultado,
    cargar,
    escena_serie,
    por_resultado,
    wod_en,
)
from tests.conftest import CrearUsuario
from tests.results._apoyo import Escena

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

MEDIDAS = ("weight_g", "height_cm", "body_fat_pct", "notes")


@pytest.fixture
async def e(session: AsyncSession) -> Escena:
    return await escena_serie(session, "2026-10-12")


def _claves(fila: dict[str, Any]) -> set[str]:
    return set((fila["after"] or {}).keys()) | set((fila["before"] or {}).keys())


async def test_corregir_deja_una_fila_update_con_el_actor_el_socio_y_el_motivo(
    session: AsyncSession, e: Escena
) -> None:
    malo = await cargar(session, e, e.wod_id, 1_000_000)
    record_id = por_resultado(await records_de(session, e.socio_id), malo.id)["id"]
    await cargar(session, e, e.wod_id, 100_000, anterior_id=malo.id)

    filas = await auditoria_de_records(session, record_id)

    actualizaciones = [f for f in filas if f["action"] == "update"]
    assert len(actualizaciones) == 1, [f["action"] for f in filas]
    fila = actualizaciones[0]
    assert fila["record_id"] == record_id
    assert fila["user_id"] == e.coach, "el actor que corrigió"
    assert fila["subject_member_id"] == e.socio_id
    assert fila["after"]["invalidated_reason"] == "superseded"
    assert not set(MEDIDAS) & _claves(fila)
    assert "***" not in str(fila["after"]) and "***" not in str(fila["before"])


async def test_anular_deja_una_fila_update_con_el_admin_como_actor(
    session: AsyncSession, e: Escena, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    r = await cargar(session, e, e.wod_id, 100_000)
    record_id = por_resultado(await records_de(session, e.socio_id), r.id)["id"]

    await anular_resultado(session, admin.id, r.id)

    actualizaciones = [
        f for f in await auditoria_de_records(session, record_id) if f["action"] == "update"
    ]
    assert len(actualizaciones) == 1
    fila = actualizaciones[0]
    assert fila["user_id"] == admin.id
    assert fila["subject_member_id"] == e.socio_id
    assert fila["after"]["invalidated_reason"] == "voided"
    assert not set(MEDIDAS) & _claves(fila)


async def test_la_reposicion_deja_su_insert_con_el_actor_que_corrigio(
    session: AsyncSession, e: Escena
) -> None:
    w_b = await wod_en(session, e, "2026-10-14", "B")
    malo = await cargar(session, e, w_b, 1_000_000)
    c = await cargar(session, e, await wod_en(session, e, "2026-10-15", "C"), 95_000)
    await cargar(session, e, w_b, 92_000, anterior_id=malo.id)
    repuesto = por_resultado(await records_de(session, e.socio_id), c.id)

    filas = await auditoria_de_records(session, repuesto["id"])

    assert [f["action"] for f in filas] == ["insert"]
    assert filas[0]["user_id"] == e.coach
    assert filas[0]["subject_member_id"] == e.socio_id
    assert filas[0]["after"]["source"] == "derived"
    assert filas[0]["after"]["value_g"] == 95_000


async def test_cada_record_invalidado_deja_su_propia_fila_update(
    session: AsyncSession, e: Escena, usuario_real: CrearUsuario
) -> None:
    """Un resultado de un WOD benchmark `load` con principal tiene DOS récords; anularlo deja dos
    filas `update`, una por récord."""
    from tests.athletes._apoyo_invalidar import vivos
    from tests.factories.wods import make_benchmark

    admin = await usuario_real("admin")
    bm = await make_benchmark(session, e.coach, name="Grace carga", score_type="load")
    w = await wod_en(session, e, "2026-10-13", "Carga", benchmark_id=bm.id)
    r = await cargar(session, e, w, 100_000)
    previos = await records_de(session, e.socio_id)
    ids = [f["id"] for f in vivos(previos, "rm") + vivos(previos, "benchmark")]
    assert len(ids) == 2

    await anular_resultado(session, admin.id, r.id)

    por_id: dict[UUID, int] = {}
    for record_id in ids:
        por_id[record_id] = sum(
            1 for f in await auditoria_de_records(session, record_id) if f["action"] == "update"
        )
    assert list(por_id.values()) == [1, 1]


async def test_la_cadena_de_auditoria_verifica_tras_corregir_y_reponer(
    session: AsyncSession, e: Escena
) -> None:
    w_b = await wod_en(session, e, "2026-10-14", "B")
    malo = await cargar(session, e, w_b, 1_000_000)
    await cargar(session, e, await wod_en(session, e, "2026-10-15", "C"), 95_000)
    await cargar(session, e, w_b, 92_000, anterior_id=malo.id)
    await session.commit()

    with actor_scope(SYSTEM_USER_ID):
        vista = await run_verification(session, source="cli", by=SYSTEM_USER_ID)

    assert vista.ok is True
    n = await session.scalar(
        text(
            "SELECT count(*) FROM audit.audit_log WHERE table_name = 'athletes.personal_records' "
            "AND action = 'update'"
        )
    )
    assert n == 1

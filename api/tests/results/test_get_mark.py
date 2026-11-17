"""`results.service.get_mark` (S9-B3, S9-D6, L-4): la marca de UN resultado como dato plano.

Una consulta por la clave primaria, sin candados ni ORM; `None` si no existe. Trae `status`,
`is_current`, `supersedes_id`, `validated_by` y `source` (para decir «Automático (tablet)»).
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.results import service
from app.modules.results.models import WodResult
from app.modules.results.schemas import ResultMark, VoidIn
from tests.factories.explain import capturar_sql
from tests.results._apoyo import escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

CAMPOS = {
    "result_id",
    "member_id",
    "wod_id",
    "wod_date",
    "benchmark_id",
    "level",
    "seconds",
    "rounds",
    "reps",
    "load_g",
    "capped",
    "status",
    "is_current",
    "supersedes_id",
    "validated_by",
    "source",
}


async def test_devuelve_la_marca_completa_como_dato_plano(session: AsyncSession) -> None:
    e = await escena(session, score_type="load", time_cap_s=None, con_clase=False)
    salida = await registrar(session, e, level="rx_plus", load_g=102_500, seconds=None)
    session.expunge_all()

    marca = await service.get_mark(session, salida.id)

    assert isinstance(marca, ResultMark) and is_dataclass(marca)
    assert not isinstance(marca, WodResult)
    assert {f.name for f in fields(marca)} == CAMPOS
    assert marca.result_id == salida.id
    assert (marca.member_id, marca.wod_id) == (e.socio_id, e.wod_id)
    assert marca.wod_date == date(2026, 10, 21)
    assert marca.benchmark_id is None
    assert (marca.level, marca.load_g, marca.capped) == ("rx_plus", 102_500, False)
    assert (marca.seconds, marca.rounds, marca.reps) == (None, None, None)
    assert (marca.status, marca.is_current, marca.supersedes_id) == ("validated", True, None)
    assert marca.validated_by == e.coach
    assert marca.source == "desk"


async def test_source_kiosk_se_conserva(session: AsyncSession) -> None:
    e = await escena(session, score_type="load", time_cap_s=None)
    assert e.clase_id is not None
    salida = await registrar(session, e, source="kiosk", load_g=80_000, seconds=None)
    session.expunge_all()

    marca = await service.get_mark(session, salida.id)

    assert marca is not None and marca.source == "kiosk"


async def test_none_si_el_resultado_no_existe(session: AsyncSession) -> None:
    assert await service.get_mark(session, uuid4()) is None


async def test_una_correccion_apunta_al_anterior_y_el_anterior_deja_de_ser_vigente(
    session: AsyncSession,
) -> None:
    e = await escena(session, score_type="load", time_cap_s=None, con_clase=False)
    primero = await registrar(session, e, load_g=90_000, seconds=None)
    segundo = await registrar(session, e, load_g=95_000, seconds=None, supersedes_id=primero.id)
    session.expunge_all()

    anterior = await service.get_mark(session, primero.id)
    nuevo = await service.get_mark(session, segundo.id)

    assert anterior is not None and nuevo is not None
    assert (anterior.is_current, anterior.status) == (False, "validated")
    assert anterior.supersedes_id is None
    assert (nuevo.is_current, nuevo.supersedes_id, nuevo.load_g) == (True, primero.id, 95_000)


async def test_un_resultado_anulado_se_ve_voided_y_no_vigente(session: AsyncSession) -> None:
    e = await escena(session, score_type="load", time_cap_s=None, con_clase=False)
    salida = await registrar(session, e, load_g=90_000, seconds=None)
    with actor_scope(e.coach):
        await service.void_result(
            session, salida.id, VoidIn.model_validate({"reason": "Socio equivocado"}), by=e.coach
        )
    session.expunge_all()

    marca = await service.get_mark(session, salida.id)

    assert marca is not None
    assert (marca.status, marca.is_current) == ("voided", False)


async def test_una_consulta_por_clave_sin_candados_ni_join(session: AsyncSession) -> None:
    e = await escena(session, score_type="load", time_cap_s=None, con_clase=False)
    salida = await registrar(session, e, load_g=90_000, seconds=None)
    session.expunge_all()

    with capturar_sql(session, "results.wod_results") as sentencias:
        await service.get_mark(session, salida.id)

    assert len(sentencias) == 1, "una sola consulta"
    sql = sentencias[0][0].upper()
    assert " FOR " not in sql, "lectura pura: el handler no pide candados (S9-D7)"
    assert " JOIN " not in sql
    assert "WHERE" in sql and ".ID" in sql, "por la clave primaria"


async def test_get_mark_se_exporta_en_el_service_y_no_cambia_las_lecturas_de_v050() -> None:
    assert "get_mark" in service.__all__ and "ResultMark" in service.__all__
    assert {"list_member_results", "list_wod_results", "leaderboard"} <= set(service.__all__)

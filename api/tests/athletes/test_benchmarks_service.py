"""Benchmarks del socio y su serie: `list_benchmarks` y `benchmark_series` (S9-C1, US-183).

Base real. Solo cuentan los resultados VIGENTES y VALIDADOS: fuera `pending`, los corregidos
(reemplazados) y los anulados. Escena (socio S, `reloj` = 2026-10-21):
- Fran (`time`): 280 s (09-01), 260 s corregido a 240 s (09-08), 300 s anulado (09-15),
  225 s `pending` (09-22), 250 s `scaled` (10-01).
- Grace (`time`): 150 s (09-10).
- Un WOD que no es benchmark con resultado, y otro socio con 100 s en Fran: no cuentan.
Serie de Fran: 280 rx, 240 rx, 250 scaled (mejor: 240; `level_changed` solo en el tercero).
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.errors import DomainError
from app.core.pagination import PageParams
from app.modules.athletes import reads, service
from app.modules.athletes.schemas import BenchmarkRowOut, BenchmarkSeriesOut
from app.modules.results.models import WodResult
from app.modules.results.schemas import VoidIn
from app.modules.results.service import void_result
from app.modules.wods import service as wods_service
from tests.athletes._apoyo_derivar import AlertasCapturadas
from tests.factories.members import make_members
from tests.factories.wods import make_benchmark, make_wod
from tests.results._apoyo import Escena, escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


@dataclass
class Mundo:
    e: Escena
    fran: UUID
    grace: UUID
    otro: UUID
    ids: dict[str, UUID]


async def _wod(session: AsyncSession, e: Escena, dia: str, **cambios: Any) -> UUID:
    cuerpo: dict[str, Any] = {
        "date": dia,
        "title": f"W {dia} {uuid4().hex[:6]}",
        "score_type": "time",
        "time_cap_s": 900,
    }
    cuerpo.update(cambios)
    return (await make_wod(session, e.coach, list(e.movimientos), **cuerpo)).id


async def _poner(session: AsyncSession, e: Escena, wod_id: UUID, **marca: Any) -> UUID:
    return (await registrar(session, dataclasses.replace(e, wod_id=wod_id), **marca)).id


@pytest.fixture
async def mundo(session: AsyncSession) -> Mundo:
    e = await escena(session, score_type="time", fecha="2026-08-20", con_clase=False)
    fran = (await make_benchmark(session, e.coach, "Fran", "time")).id
    grace = (await make_benchmark(session, e.coach, "Grace", "time")).id
    ids: dict[str, UUID] = {}
    w1 = await _wod(session, e, "2026-09-01", benchmark_id=fran)
    w2 = await _wod(session, e, "2026-09-08", benchmark_id=fran)
    w3 = await _wod(session, e, "2026-09-15", benchmark_id=fran)
    w4 = await _wod(session, e, "2026-09-22", benchmark_id=fran)
    w5 = await _wod(session, e, "2026-10-01", benchmark_id=fran)
    wg = await _wod(session, e, "2026-09-10", benchmark_id=grace)
    libre = await _wod(session, e, "2026-09-12")
    ids["a1"] = await _poner(session, e, w1, seconds=280)
    malo = await _poner(session, e, w2, seconds=260)
    ids["a2_malo"] = malo
    ids["a2"] = await _poner(session, e, w2, seconds=240, supersedes_id=malo)
    anulado = await _poner(session, e, w3, seconds=300)
    ids["anulado"] = anulado
    with actor_scope(e.coach):
        await void_result(session, anulado, VoidIn(reason="Socio equivocado"), by=e.coach)
    with actor_scope(e.coach):
        session.add(
            WodResult(
                wod_id=w4,
                member_id=e.socio_id,
                wod_date=date(2026, 9, 22),
                benchmark_id=fran,
                level="rx",
                seconds=225,
                status="pending",
                recorded_by=e.coach,
                source="desk",
            )
        )
        await session.flush()
    ids["a3"] = await _poner(session, e, w5, seconds=250, level="scaled")
    ids["grace"] = await _poner(session, e, wg, seconds=150)
    await _poner(session, e, libre, seconds=100)
    otro = (await make_members(session, 1))[0]
    ajeno = dataclasses.replace(e, socio_id=otro.id, socio=otro)
    await _poner(session, ajeno, w1, seconds=100)
    return Mundo(e, fran, grace, otro.id, ids)


# --- la lista de benchmarks -------------------------------------------------------------------


async def test_lista_solo_benchmarks_con_intentos_vigentes_y_validados(
    session: AsyncSession, mundo: Mundo
) -> None:
    pagina = await service.list_benchmarks(session, mundo.e.socio_id, PageParams())

    assert pagina.total == 2
    assert all(isinstance(f, BenchmarkRowOut) for f in pagina.items)
    fran, grace = pagina.items  # por nombre
    assert (fran.name, fran.benchmark_id, fran.score_type) == ("Fran", mundo.fran, "time")
    # Cuentan 280, 240 (la corrección) y 250 scaled; no el 260, el anulado ni el pending.
    assert fran.attempts == 3
    assert (fran.best.level, fran.best.seconds, fran.best.capped) == ("rx", 240, False)
    assert fran.last_on == date(2026, 10, 1)
    assert (grace.name, grace.attempts, grace.best.seconds) == ("Grace", 1, 150)
    assert grace.last_on == date(2026, 9, 10)


async def test_el_wod_sin_benchmark_y_el_otro_socio_no_aparecen(
    session: AsyncSession, mundo: Mundo
) -> None:
    mio = await service.list_benchmarks(session, mundo.e.socio_id, PageParams())
    suyo = await service.list_benchmarks(session, mundo.otro, PageParams())

    assert {f.name for f in mio.items} == {"Fran", "Grace"}
    assert [(f.name, f.attempts, f.best.seconds) for f in suyo.items] == [("Fran", 1, 100)]


async def test_la_lista_pagina_despues_de_agrupar(session: AsyncSession, mundo: Mundo) -> None:
    primera = await service.list_benchmarks(session, mundo.e.socio_id, PageParams(limit=1))
    segunda = await service.list_benchmarks(
        session, mundo.e.socio_id, PageParams(limit=1, offset=1)
    )
    fuera = await service.list_benchmarks(session, mundo.e.socio_id, PageParams(limit=1, offset=5))

    assert (primera.total, primera.limit, primera.offset) == (2, 1, 0)
    assert [f.name for f in primera.items] == ["Fran"]
    assert [f.name for f in segunda.items] == ["Grace"]
    assert (fuera.total, fuera.items) == (2, [])


async def test_un_socio_sin_intentos_da_lista_vacia(session: AsyncSession) -> None:
    (socio,) = await make_members(session, 1)

    pagina = await service.list_benchmarks(session, socio.id, PageParams())

    assert (pagina.total, pagina.items) == (0, [])


async def test_la_lista_de_un_socio_inexistente_da_404(session: AsyncSession) -> None:
    with pytest.raises(DomainError) as caso:
        await service.list_benchmarks(session, uuid4(), PageParams())
    assert caso.value.status == 404 and caso.value.code == "member_not_found"


# --- la serie ---------------------------------------------------------------------------------


async def test_la_serie_trae_solo_vigentes_y_validados_en_orden_cronologico(
    session: AsyncSession, mundo: Mundo
) -> None:
    serie = await service.benchmark_series(session, mundo.e.socio_id, mundo.fran)

    assert isinstance(serie, BenchmarkSeriesOut)
    assert (serie.benchmark_id, serie.name, serie.score_type) == (mundo.fran, "Fran", "time")
    assert [a.result_id for a in serie.attempts] == [
        mundo.ids["a1"],
        mundo.ids["a2"],
        mundo.ids["a3"],
    ]
    assert [a.seconds for a in serie.attempts] == [280, 240, 250]
    assert [a.wod_date for a in serie.attempts] == [
        date(2026, 9, 1),
        date(2026, 9, 8),
        date(2026, 10, 1),
    ]
    assert [a.level for a in serie.attempts] == ["rx", "rx", "scaled"]
    assert [a.source for a in serie.attempts] == ["desk", "desk", "desk"]


async def test_exactamente_un_mejor_y_level_changed_solo_en_el_cambio(
    session: AsyncSession, mundo: Mundo
) -> None:
    serie = await service.benchmark_series(session, mundo.e.socio_id, mundo.fran)

    assert [a.is_best for a in serie.attempts] == [False, True, False]
    assert [a.level_changed for a in serie.attempts] == [False, False, True]


async def test_los_pending_los_reemplazados_y_los_anulados_no_estan(
    session: AsyncSession, mundo: Mundo
) -> None:
    serie = await service.benchmark_series(session, mundo.e.socio_id, mundo.fran)

    vistos = {a.result_id for a in serie.attempts}
    assert mundo.ids["a2_malo"] not in vistos
    assert mundo.ids["anulado"] not in vistos
    assert 225 not in {a.seconds for a in serie.attempts}


async def test_la_serie_es_solo_del_socio(session: AsyncSession, mundo: Mundo) -> None:
    serie = await service.benchmark_series(session, mundo.otro, mundo.fran)

    assert [a.seconds for a in serie.attempts] == [100]
    assert [a.is_best for a in serie.attempts] == [True]


async def test_benchmark_sin_intentos_da_serie_vacia(session: AsyncSession, mundo: Mundo) -> None:
    otro = await make_benchmark(session, mundo.e.coach, "Helen", "time")

    serie = await service.benchmark_series(session, mundo.e.socio_id, otro.id)

    assert (serie.name, serie.score_type, serie.attempts) == ("Helen", "time", [])


async def test_benchmark_inexistente_da_404_benchmark_not_found(
    session: AsyncSession, mundo: Mundo
) -> None:
    with pytest.raises(DomainError) as caso:
        await service.benchmark_series(session, mundo.e.socio_id, uuid4())
    assert caso.value.status == 404 and caso.value.code == "benchmark_not_found"


async def test_socio_inexistente_da_404_member_not_found(
    session: AsyncSession, mundo: Mundo
) -> None:
    with pytest.raises(DomainError) as caso:
        await service.benchmark_series(session, uuid4(), mundo.fran)
    assert caso.value.status == 404 and caso.value.code == "member_not_found"


async def test_un_socio_dado_de_baja_tambien_se_lee(session: AsyncSession, mundo: Mundo) -> None:
    from sqlalchemy import text

    await session.execute(
        text("UPDATE members.members SET deleted_at = now() WHERE id = :i"),
        {"i": mundo.e.socio_id},
    )

    serie = await service.benchmark_series(session, mundo.e.socio_id, mundo.fran)

    assert len(serie.attempts) == 3


# --- tope y campos ----------------------------------------------------------------------------


def test_el_tope_de_la_serie_es_200() -> None:
    assert reads.SERIES_MAX == 200


async def test_el_tope_deja_los_intentos_mas_recientes_en_orden_ascendente(
    session: AsyncSession, mundo: Mundo, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reads, "SERIES_MAX", 2)

    serie = await service.benchmark_series(session, mundo.e.socio_id, mundo.fran)

    assert [a.result_id for a in serie.attempts] == [mundo.ids["a2"], mundo.ids["a3"]]
    assert sum(a.is_best for a in serie.attempts) == 1


async def test_la_respuesta_no_trae_campos_cifrados_ni_datos_del_socio(
    session: AsyncSession, mundo: Mundo
) -> None:
    serie = await service.benchmark_series(session, mundo.e.socio_id, mundo.fran)
    pagina = await service.list_benchmarks(session, mundo.e.socio_id, PageParams())
    prohibidos = {
        "weight_g",
        "height_cm",
        "body_fat_pct",
        "notes",
        "document",
        "phone",
        "email",
        "birth_date",
        "member_id",
        "first_name",
        "last_name",
    }

    assert not prohibidos & set(serie.model_dump())
    assert not prohibidos & set(serie.attempts[0].model_dump())
    assert not prohibidos & set(pagina.items[0].model_dump())


# --- revisiones de S9-C1 (S9-D63) -------------------------------------------------------------


async def test_la_serie_dice_si_se_trunco_y_el_mejor_es_el_de_los_intentos_mostrados(
    session: AsyncSession, mundo: Mundo, monkeypatch: pytest.MonkeyPatch
) -> None:
    completa = await service.benchmark_series(session, mundo.e.socio_id, mundo.fran)
    monkeypatch.setattr(reads, "SERIES_MAX", 2)
    recortada = await service.benchmark_series(session, mundo.e.socio_id, mundo.fran)
    monkeypatch.setattr(reads, "SERIES_MAX", 3)
    justa = await service.benchmark_series(session, mundo.e.socio_id, mundo.fran)

    assert completa.truncated is False and justa.truncated is False
    assert len(justa.attempts) == 3
    assert recortada.truncated is True
    assert [a.result_id for a in recortada.attempts] == [mundo.ids["a2"], mundo.ids["a3"]]
    assert sum(a.is_best for a in recortada.attempts) == 1


async def test_una_serie_vacia_no_esta_truncada(session: AsyncSession, mundo: Mundo) -> None:
    otro = await make_benchmark(session, mundo.e.coach, "Helen", "time")

    serie = await service.benchmark_series(session, mundo.e.socio_id, otro.id)

    assert serie.truncated is False


async def test_la_lista_alerta_y_registra_cuando_alcanza_el_tope_de_marcas(
    session: AsyncSession,
    mundo: Mundo,
    alertas: AlertasCapturadas,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reads, "MEMBER_MARKS_MAX", 4)  # el socio tiene 4 marcas de benchmark
    with caplog.at_level(logging.WARNING, logger="app.athletes"):
        pagina = await service.list_benchmarks(session, mundo.e.socio_id, PageParams())

    assert pagina.total == 2  # la respuesta sigue
    assert alertas.de("athletes_restore_capped") == [{"marcas": 4}]
    avisos = [r for r in caplog.records if r.name == "app.athletes"]
    assert avisos and getattr(avisos[0], "member_id", None) == str(mundo.e.socio_id)
    assert str(mundo.e.socio_id) not in str(alertas.recibidas)


async def test_la_lista_no_alerta_bajo_el_tope(
    session: AsyncSession, mundo: Mundo, alertas: AlertasCapturadas
) -> None:
    await service.list_benchmarks(session, mundo.e.socio_id, PageParams())

    assert alertas.recibidas == []


async def test_q_filtra_por_nombre_sin_tildes_ni_mayusculas_y_el_total_lo_refleja(
    session: AsyncSession, mundo: Mundo
) -> None:
    angel = await make_benchmark(session, mundo.e.coach, "Ángel Ñandú", "time")
    w = await _wod(session, mundo.e, "2026-10-05", benchmark_id=angel.id)
    await _poner(session, mundo.e, w, seconds=200)
    socio = mundo.e.socio_id

    por_tilde = await service.list_benchmarks(session, socio, PageParams(), q="ANGEL")
    por_ene = await service.list_benchmarks(session, socio, PageParams(), q="ñandu")
    por_parte = await service.list_benchmarks(session, socio, PageParams(), q="  RA ")
    sin_q = await service.list_benchmarks(session, socio, PageParams())
    ninguno = await service.list_benchmarks(session, socio, PageParams(), q="zzz")
    comodin = await service.list_benchmarks(session, socio, PageParams(), q="%")

    assert [f.name for f in por_tilde.items] == ["Ángel Ñandú"] and por_tilde.total == 1
    assert [f.name for f in por_ene.items] == ["Ángel Ñandú"]
    assert [f.name for f in por_parte.items] == ["Fran", "Grace"] and por_parte.total == 2
    assert sin_q.total == 3
    assert (ninguno.total, ninguno.items) == (0, [])
    assert (comodin.total, comodin.items) == (0, [])  # `%` es literal, no comodín


async def test_marcas_de_un_benchmark_fuera_del_catalogo_se_registran_sin_datos_personales(
    session: AsyncSession,
    mundo: Mundo,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = wods_service.benchmark_refs

    async def sin_fran(sesion: AsyncSession, ids: Any) -> Any:
        refs = await real(sesion, ids)
        refs.pop(mundo.fran, None)
        return refs

    monkeypatch.setattr(reads.wods_service, "benchmark_refs", sin_fran)
    with caplog.at_level(logging.WARNING, logger="app.athletes"):
        pagina = await service.list_benchmarks(session, mundo.e.socio_id, PageParams())

    assert [f.name for f in pagina.items] == ["Grace"]
    avisos = [r for r in caplog.records if r.name == "app.athletes"]
    assert avisos and getattr(avisos[0], "marcas", None) == 3
    assert str(mundo.fran) not in caplog.text and str(mundo.e.socio_id) not in caplog.text

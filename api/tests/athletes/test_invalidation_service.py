"""Invalidación de récords derivados al corregir o anular un resultado (S9-B5, US-181 CA3 a CA6).

Handlers `on_wod_result_superseded` (corrección) y `on_wod_result_voided` (anulación) más la
reposición del mejor de `on_wod_result_validated` cuando la marca corrige a otra (S9-D7, S9-D10,
S9-D11, S9-D30, S9-D42). Valores a mano, en gramos enteros (S8-D41); cada WOD en un día distinto
(`uq_wods_date`).

- Corregir 1.000 kg (1.000.000 g) a 100 kg deja el récord de 1.000 kg `superseded` con
  `invalidated_by_result_id` = el resultado nuevo, SIN borrarlo, y el vigente en 100.000 g.
- Anular deja el récord `voided` (sin resultado sucesor); el actor es quien anuló.
- El hueco: 90, 1.000 (error), 95 y la corrección a 92 deja vigente 95 (se repone el 95).
- Lo mismo con benchmark (el mejor tiempo que había quedado tapado).
- Una fila invalidada es terminal: la base rechaza revivirla.
- Se invalida también con el socio dado de baja.
- Una corrección sin récord no llama a `member_marks`; con récord, una vez por objetivo.
- Tope de sentencias con corrección y reposición (S9-D30) y tope de marcas candidatas (alerta
  `athletes_restore_capped` con `{"marcas": N}`, sin ids, y no repone).
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.modules.athletes import derive
from app.modules.athletes.events import PersonalRecordSet
from tests.athletes._apoyo_derivar import (
    AlertasCapturadas,
    contar_sentencias,
    records_de,
    vigente_g,
)
from tests.athletes._apoyo_invalidar import (
    ContadorMarcas,
    anular_resultado,
    cargar,
    escena_serie,
    invalidados,
    poner_en,
    por_resultado,
    vivos,
    wod_en,
)
from tests.conftest import CapturarEventos, CrearUsuario
from tests.factories.wods import make_benchmark
from tests.results._apoyo import Escena

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


@pytest.fixture
async def e(session: AsyncSession) -> Escena:
    """Socio y coach; el primer WOD (`load`) cae el 2026-10-12."""
    return await escena_serie(session, "2026-10-12")


# Corregir -------------------------------------------------------------------------------------


async def test_corregir_1000_kg_a_100_kg_deja_el_de_1000_superseded_y_el_vigente_correcto(
    session: AsyncSession, e: Escena
) -> None:
    malo = await cargar(session, e, e.wod_id, 1_000_000)
    bueno = await cargar(session, e, e.wod_id, 100_000, anterior_id=malo.id)

    filas = await records_de(session, e.socio_id)

    assert len(filas) == 2, "el de 1.000 kg no se borra"
    viejo = por_resultado(filas, malo.id)
    assert viejo["value_g"] == 1_000_000
    assert viejo["invalidated_at"] is not None
    assert viejo["invalidated_reason"] == "superseded"
    assert viejo["invalidated_by_result_id"] == bueno.id
    assert viejo["invalidated_by"] == e.coach
    nuevo = por_resultado(filas, bueno.id)
    assert nuevo["value_g"] == 100_000 and nuevo["invalidated_at"] is None
    assert nuevo["source"] == "derived"
    assert vigente_g(filas) == 100_000


async def test_corregir_hacia_arriba_tambien_invalida_el_anterior_y_deriva_el_nuevo(
    session: AsyncSession, e: Escena
) -> None:
    malo = await cargar(session, e, e.wod_id, 90_000)
    bueno = await cargar(session, e, e.wod_id, 95_000, anterior_id=malo.id)

    filas = await records_de(session, e.socio_id)

    assert por_resultado(filas, malo.id)["invalidated_reason"] == "superseded"
    assert por_resultado(filas, bueno.id)["value_g"] == 95_000
    assert vigente_g(filas) == 95_000


async def test_corregir_una_marca_scaled_no_deja_vigente_alguno(
    session: AsyncSession, e: Escena
) -> None:
    """La corrección pasa a `scaled`: no deriva y el anterior queda invalidado; sin vigente."""
    malo = await cargar(session, e, e.wod_id, 100_000)
    await cargar(session, e, e.wod_id, 100_000, anterior_id=malo.id, level="scaled")

    filas = await records_de(session, e.socio_id)

    assert len(filas) == 1
    assert filas[0]["invalidated_reason"] == "superseded"
    assert vigente_g(filas) is None


async def test_el_hueco_90_1000_95_y_la_correccion_a_92_deja_vigente_95(
    session: AsyncSession, e: Escena
) -> None:
    """90 kg (derivó), 1.000 kg erróneo (derivó, vigente), 95 kg (no derivó: menor que 1.000).
    Se corrige el 1.000 a 92: el 92 deriva (mayor que 90) y la reposición agrega el 95."""
    a = await cargar(session, e, await wod_en(session, e, "2026-10-13", "A"), 90_000)
    w_b = await wod_en(session, e, "2026-10-14", "B")
    malo = await cargar(session, e, w_b, 1_000_000)
    c = await cargar(session, e, await wod_en(session, e, "2026-10-15", "C"), 95_000)
    assert vigente_g(await records_de(session, e.socio_id)) == 1_000_000

    corregido = await cargar(session, e, w_b, 92_000, anterior_id=malo.id)

    filas = await records_de(session, e.socio_id)
    assert len(filas) == 4
    assert por_resultado(filas, a.id)["invalidated_at"] is None
    assert por_resultado(filas, malo.id)["invalidated_reason"] == "superseded"
    assert por_resultado(filas, corregido.id)["value_g"] == 92_000
    repuesto = por_resultado(filas, c.id)
    assert repuesto["value_g"] == 95_000 and repuesto["invalidated_at"] is None
    assert vigente_g(filas) == 95_000
    assert sorted(f["value_g"] for f in vivos(filas)) == [90_000, 92_000, 95_000]


async def test_el_record_repuesto_nace_derivado_con_la_fecha_del_wod_y_el_actor_del_contexto(
    session: AsyncSession, e: Escena
) -> None:
    w_b = await wod_en(session, e, "2026-10-14", "B")
    malo = await cargar(session, e, w_b, 1_000_000)
    c_wod = await wod_en(session, e, "2026-10-15", "C")
    c = await cargar(session, e, c_wod, 95_000)

    await cargar(session, e, w_b, 92_000, anterior_id=malo.id)

    repuesto = por_resultado(await records_de(session, e.socio_id), c.id)
    assert repuesto["source"] == "derived"
    assert repuesto["wod_id"] == c_wod
    assert repuesto["achieved_on"].isoformat() == "2026-10-15"
    assert repuesto["created_by"] == e.coach, "el actor del contexto: quien corrigió"
    assert repuesto["invalidated_at"] is None


async def test_reponer_emite_personal_record_set_y_invalidar_no_emite(
    session: AsyncSession, e: Escena, capturar_eventos: CapturarEventos
) -> None:
    w_b = await wod_en(session, e, "2026-10-14", "B")
    malo = await cargar(session, e, w_b, 1_000_000)
    c = await cargar(session, e, await wod_en(session, e, "2026-10-15", "C"), 95_000)
    recibidos = capturar_eventos(PersonalRecordSet)

    corregido = await cargar(session, e, w_b, 92_000, anterior_id=malo.id)

    filas = await records_de(session, e.socio_id)
    assert [ev.record_id for ev in recibidos] == [
        por_resultado(filas, corregido.id)["id"],
        por_resultado(filas, c.id)["id"],
    ], "primero el del resultado nuevo, luego el repuesto; la invalidación no emite nada"
    assert all(ev.source == "derived" and ev.kind == "rm" for ev in recibidos)


async def test_corregir_a_un_valor_menor_no_repone_si_el_mejor_ya_tiene_record_vivo(
    session: AsyncSession, e: Escena
) -> None:
    """50 kg (R), 100 kg (R vigente), 80 kg (sin récord). Se corrige el 50 a 45: el de 50 se
    invalida, el 45 no deriva (menor que 100) y el 80 NO se repone: no supera al vigente (100)."""
    w_a = await wod_en(session, e, "2026-10-13", "A")
    a = await cargar(session, e, w_a, 50_000)
    b = await cargar(session, e, await wod_en(session, e, "2026-10-14", "B"), 100_000)
    await cargar(session, e, await wod_en(session, e, "2026-10-15", "C"), 80_000)

    await cargar(session, e, w_a, 45_000, anterior_id=a.id)

    filas = await records_de(session, e.socio_id)
    assert [f["value_g"] for f in vivos(filas)] == [100_000]
    assert por_resultado(filas, b.id)["invalidated_at"] is None
    assert len(filas) == 2, "ni el 45 ni el 80 crearon récord"


# Anular ---------------------------------------------------------------------------------------


async def test_anular_deja_el_record_voided_sin_resultado_sucesor(
    session: AsyncSession, e: Escena, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    r = await cargar(session, e, e.wod_id, 1_000_000)

    await anular_resultado(session, admin.id, r.id)

    filas = await records_de(session, e.socio_id)
    assert len(filas) == 1
    assert filas[0]["invalidated_reason"] == "voided"
    assert filas[0]["invalidated_by_result_id"] is None
    assert filas[0]["invalidated_by"] == admin.id, "el admin que anuló, no quien registró"
    assert vigente_g(filas) is None


async def test_anular_repone_el_mejor_que_habia_quedado_tapado(
    session: AsyncSession, e: Escena, usuario_real: CrearUsuario
) -> None:
    """100 kg (R vigente) y tres marcas menores sin récord: 40, 50 y 60 kg. Anular el de 100 repone
    SOLO el 60 (la mejor), no las tres."""
    admin = await usuario_real("admin")
    cien = await cargar(session, e, e.wod_id, 100_000)
    await cargar(session, e, await wod_en(session, e, "2026-10-13", "A"), 40_000)
    await cargar(session, e, await wod_en(session, e, "2026-10-14", "B"), 50_000)
    sesenta = await cargar(session, e, await wod_en(session, e, "2026-10-15", "C"), 60_000)

    await anular_resultado(session, admin.id, cien.id)

    filas = await records_de(session, e.socio_id)
    assert por_resultado(filas, cien.id)["invalidated_reason"] == "voided"
    assert [f["value_g"] for f in vivos(filas)] == [60_000]
    assert vivos(filas)[0]["result_id"] == sesenta.id
    assert len(filas) == 2
    assert vivos(filas)[0]["created_by"] == admin.id


async def test_anular_un_resultado_sin_record_no_toca_nada(
    session: AsyncSession, e: Escena, usuario_real: CrearUsuario, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await usuario_real("admin")
    await cargar(session, e, e.wod_id, 100_000)
    menor = await cargar(session, e, await wod_en(session, e, "2026-10-13", "A"), 60_000)
    contador = ContadorMarcas(monkeypatch)

    await anular_resultado(session, admin.id, menor.id)

    filas = await records_de(session, e.socio_id)
    assert len(filas) == 1 and invalidados(filas) == []
    assert contador.llamadas == [], "sin récord invalidado no hay reposición"


async def test_un_resultado_nuevo_tras_anular_deriva_con_normalidad(
    session: AsyncSession, e: Escena, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    r = await cargar(session, e, e.wod_id, 1_000_000)
    await anular_resultado(session, admin.id, r.id)

    nuevo = await cargar(session, e, e.wod_id, 100_000)

    filas = await records_de(session, e.socio_id)
    assert por_resultado(filas, nuevo.id)["value_g"] == 100_000
    assert vigente_g(filas) == 100_000


async def test_anular_un_wod_con_rm_y_benchmark_invalida_los_dos_y_repone_por_objetivo(
    session: AsyncSession, e: Escena, usuario_real: CrearUsuario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un benchmark de tipo `load` con principal deriva DOS récords (S9-D10); anular el resultado
    invalida los dos, y la reposición corre una vez por objetivo tocado (RM y benchmark)."""
    admin = await usuario_real("admin")
    bm = await make_benchmark(session, e.coach, name="Grace carga", score_type="load")
    w = await wod_en(session, e, "2026-10-13", "Carga benchmark", benchmark_id=bm.id)
    r = await cargar(session, e, w, 100_000)
    antes = await records_de(session, e.socio_id)
    assert sorted(f["kind"] for f in vivos(antes, "rm") + vivos(antes, "benchmark")) == [
        "benchmark",
        "rm",
    ]
    contador = ContadorMarcas(monkeypatch)

    await anular_resultado(session, admin.id, r.id)

    filas = await records_de(session, e.socio_id)
    assert len(invalidados(filas)) == 2
    assert {f["invalidated_reason"] for f in filas} == {"voided"}
    assert len(contador.llamadas) == 2, "una reposición por objetivo tocado"


# Benchmark ------------------------------------------------------------------------------------


async def _serie_benchmark(session: AsyncSession, e: Escena) -> tuple[Any, Any, Any, Any]:
    """Fran (`time`): W1 280 s (récord), W2 300 s y W3 290 s (peores que el vigente: sin récord)."""
    bm = await make_benchmark(session, e.coach, name="Fran", score_type="time")
    datos: dict[str, Any] = {"score_type": "time", "time_cap_s": 600, "benchmark_id": bm.id}
    w1 = await wod_en(session, e, "2026-10-14", "F1", **datos)
    w2 = await wod_en(session, e, "2026-10-15", "F2", **datos)
    w3 = await wod_en(session, e, "2026-10-16", "F3", **datos)
    r1 = await poner_en(session, e, w1, seconds=280)
    r2 = await poner_en(session, e, w2, seconds=300)
    r3 = await poner_en(session, e, w3, seconds=290)
    return w1, r1, r2, r3


async def test_benchmark_corregir_invalida_el_anterior_y_repone_el_mejor_que_quedo(
    session: AsyncSession, e: Escena
) -> None:
    """Se corrige 280 s a 295 s: el 280 se invalida, el 295 deriva y la reposición agrega el 290
    (mejor que 295; el 300 no es mejor que nada)."""
    w1, r1, r2, r3 = await _serie_benchmark(session, e)
    assert [f["seconds"] for f in vivos(await records_de(session, e.socio_id), "benchmark")] == [
        280
    ]

    corregido = await poner_en(session, e, w1, anterior_id=r1.id, seconds=295)

    filas = await records_de(session, e.socio_id)
    assert por_resultado(filas, r1.id, "benchmark")["invalidated_reason"] == "superseded"
    assert por_resultado(filas, r1.id, "benchmark")["invalidated_by_result_id"] == corregido.id
    assert sorted(f["seconds"] for f in vivos(filas, "benchmark")) == [290, 295]
    assert por_resultado(filas, r3.id, "benchmark")["invalidated_at"] is None
    assert all(f["result_id"] != r2.id for f in filas), "el 300 no es récord"


async def test_benchmark_anular_repone_el_mejor_tiempo_que_habia_quedado_tapado(
    session: AsyncSession, e: Escena, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    _w1, r1, _r2, r3 = await _serie_benchmark(session, e)

    await anular_resultado(session, admin.id, r1.id)

    filas = await records_de(session, e.socio_id)
    assert por_resultado(filas, r1.id, "benchmark")["invalidated_reason"] == "voided"
    assert [f["seconds"] for f in vivos(filas, "benchmark")] == [290]
    assert vivos(filas, "benchmark")[0]["result_id"] == r3.id


# La base no deja revivir ----------------------------------------------------------------------


async def test_la_base_rechaza_revivir_un_record_invalidado(
    session: AsyncSession, e: Escena
) -> None:
    malo = await cargar(session, e, e.wod_id, 1_000_000)
    await cargar(session, e, e.wod_id, 100_000, anterior_id=malo.id)
    fila = por_resultado(await records_de(session, e.socio_id), malo.id)
    assert fila["invalidated_at"] is not None, "la prueba exige el récord ya invalidado"

    with pytest.raises(DBAPIError):
        async with session.begin_nested():
            await session.execute(
                text(
                    "UPDATE athletes.personal_records SET invalidated_at = NULL, "
                    "invalidated_reason = NULL, invalidated_by = NULL, "
                    "invalidated_by_result_id = NULL WHERE id = :i"
                ),
                {"i": fila["id"]},
            )

    despues = por_resultado(await records_de(session, e.socio_id), malo.id)
    assert despues["invalidated_reason"] == "superseded"


# Socio dado de baja ---------------------------------------------------------------------------


async def test_anular_invalida_tambien_con_el_socio_dado_de_baja(
    session: AsyncSession, e: Escena, usuario_real: CrearUsuario
) -> None:
    """S9-D14: `void_result` no exige socio vivo y los handlers invalidan igual."""
    admin = await usuario_real("admin")
    r = await cargar(session, e, e.wod_id, 100_000)
    await session.execute(
        text("UPDATE members.members SET deleted_at = now() WHERE id = :i"), {"i": e.socio_id}
    )

    await anular_resultado(session, admin.id, r.id)

    filas = await records_de(session, e.socio_id)
    assert filas[0]["invalidated_reason"] == "voided"


# `member_marks` solo cuando hay algo que reponer ----------------------------------------------


async def test_corregir_un_resultado_sin_record_no_llama_a_member_marks(
    session: AsyncSession, e: Escena, monkeypatch: pytest.MonkeyPatch
) -> None:
    await cargar(session, e, e.wod_id, 100_000)
    w_a = await wod_en(session, e, "2026-10-13", "A")
    menor = await cargar(session, e, w_a, 60_000)
    contador = ContadorMarcas(monkeypatch)

    await cargar(session, e, w_a, 65_000, anterior_id=menor.id)

    filas = await records_de(session, e.socio_id)
    assert len(filas) == 1 and invalidados(filas) == []
    assert contador.llamadas == []


async def test_corregir_un_rm_repone_con_un_solo_member_marks_filtrado_en_sql(
    session: AsyncSession, e: Escena, monkeypatch: pytest.MonkeyPatch
) -> None:
    w_b = await wod_en(session, e, "2026-10-14", "B")
    malo = await cargar(session, e, w_b, 1_000_000)
    contador = ContadorMarcas(monkeypatch)

    await cargar(session, e, w_b, 92_000, anterior_id=malo.id)

    assert len(contador.llamadas) == 1
    llamada = contador.llamadas[0]
    assert llamada["member_id"] == e.socio_id
    assert llamada["only_load"] is True
    assert set(llamada["wod_ids"]) == {e.wod_id, w_b}, "los WODs load con ese principal"
    assert llamada["limit"] == derive.RESTORE_MAX_MARKS + 1


async def test_corregir_un_benchmark_repone_con_member_marks_por_benchmark_id(
    session: AsyncSession, e: Escena, monkeypatch: pytest.MonkeyPatch
) -> None:
    bm = await make_benchmark(session, e.coach, name="Helen", score_type="time")
    datos: dict[str, Any] = {"score_type": "time", "time_cap_s": 600, "benchmark_id": bm.id}
    w1 = await wod_en(session, e, "2026-10-14", "H1", **datos)
    r1 = await poner_en(session, e, w1, seconds=280)
    contador = ContadorMarcas(monkeypatch)

    await poner_en(session, e, w1, anterior_id=r1.id, seconds=290)

    assert len(contador.llamadas) == 1
    assert contador.llamadas[0]["benchmark_id"] == bm.id
    assert contador.llamadas[0]["limit"] == derive.RESTORE_MAX_MARKS + 1


# Tope de marcas candidatas (S9-D30) -----------------------------------------------------------


async def _escena_con_tres_candidatas(session: AsyncSession, e: Escena) -> Any:
    """100 kg (récord) y tres marcas menores sin récord (40, 50 y 60 kg)."""
    cien = await cargar(session, e, e.wod_id, 100_000)
    await cargar(session, e, await wod_en(session, e, "2026-10-13", "A"), 40_000)
    await cargar(session, e, await wod_en(session, e, "2026-10-14", "B"), 50_000)
    await cargar(session, e, await wod_en(session, e, "2026-10-15", "C"), 60_000)
    return cien


async def test_con_mas_marcas_que_el_tope_alerta_con_el_conteo_y_no_repone(
    session: AsyncSession,
    e: Escena,
    usuario_real: CrearUsuario,
    alertas: AlertasCapturadas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = await usuario_real("admin")
    cien = await _escena_con_tres_candidatas(session, e)
    monkeypatch.setattr(derive, "RESTORE_MAX_MARKS", 2)

    salida = await anular_resultado(session, admin.id, cien.id)

    assert salida.status == "voided", "la anulación se confirma aunque la reposición se omita"
    filas = await records_de(session, e.socio_id)
    assert por_resultado(filas, cien.id)["invalidated_reason"] == "voided"
    assert vivos(filas) == [], "no repone"
    recibidas = alertas.de("athletes_restore_capped")
    assert len(recibidas) == 1
    assert set(recibidas[0]) == {"marcas"}, "sin ids de socio ni de resultado"
    assert isinstance(recibidas[0]["marcas"], int) and recibidas[0]["marcas"] > 2
    assert alertas.de("athletes_derive_skipped") == []


async def test_con_exactamente_el_tope_de_marcas_si_repone_y_no_alerta(
    session: AsyncSession,
    e: Escena,
    usuario_real: CrearUsuario,
    alertas: AlertasCapturadas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = await usuario_real("admin")
    cien = await _escena_con_tres_candidatas(session, e)
    monkeypatch.setattr(derive, "RESTORE_MAX_MARKS", 3)

    await anular_resultado(session, admin.id, cien.id)

    filas = await records_de(session, e.socio_id)
    assert [f["value_g"] for f in vivos(filas)] == [60_000]
    assert alertas.de("athletes_restore_capped") == []


def test_el_tope_por_omision_es_200() -> None:
    assert derive.RESTORE_MAX_MARKS == 200


# Presupuesto de sentencias (S9-D30) -----------------------------------------------------------


async def _hueco(session: AsyncSession, dias: tuple[str, str, str]) -> tuple[Escena, Any, Any]:
    """90, 1.000 (error) y 95 kg en tres WODs: la escena, el WOD del error y su resultado."""
    e = await escena_serie(session, dias[0])
    await cargar(session, e, e.wod_id, 90_000)
    w_b = await wod_en(session, e, dias[1], f"B {dias[1]}")
    malo = await cargar(session, e, w_b, 1_000_000)
    await cargar(session, e, await wod_en(session, e, dias[2], f"C {dias[2]}"), 95_000)
    return e, w_b, malo


async def test_presupuesto_de_sentencias_de_una_correccion_con_reposicion(
    session: AsyncSession,
) -> None:
    """S9-D30: con corrección y reposición hay a lo sumo 12 sentencias de más sobre
    `athletes.`, `results.` y `wods.` (el contador excluye SAVEPOINT y RELEASE). Si el Verde
    necesita más, lo justifica en el cuaderno y lo aprueba `database-reviewer`."""
    tablas = ("athletes.", "results.", "wods.")
    con, w_con, malo_con = await _hueco(session, ("2026-10-01", "2026-10-02", "2026-10-03"))
    sin, w_sin, malo_sin = await _hueco(session, ("2026-10-05", "2026-10-06", "2026-10-07"))

    with contar_sentencias(session, tablas) as vistas_con:
        await cargar(session, con, w_con, 92_000, anterior_id=malo_con.id)
    # Quita los handlers de `athletes` (el bus se restaura solo al salir de la prueba).
    for handlers in list(events._subscribers.values()):
        for h in list(handlers):
            if getattr(h, "__module__", "") == "app.modules.athletes.derive":
                handlers.remove(h)
    with contar_sentencias(session, tablas) as vistas_sin:
        await cargar(session, sin, w_sin, 92_000, anterior_id=malo_sin.id)

    assert vigente_g(await records_de(session, con.socio_id)) == 95_000, "hubo reposición"
    assert vigente_g(await records_de(session, sin.socio_id)) == 1_000_000, "sin handlers no"
    assert 0 < len(vistas_con) - len(vistas_sin) <= 12

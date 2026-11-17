"""`athletes.service.add_record` y `list_records` con PostgreSQL real (S9-B1, US-180). Rojo B1.

Récords manuales (S9-D8, S9-D10, S9-D12, S9-D14):
- RM: el movimiento debe existir, estar activo y medirse en `kg` (422 `field = "movement_id"`);
  `value_g` de 1 a 1.000.000. Benchmark: existir (422 `field = "benchmark_id"`) y una marca que
  cumpla el `score_type` (`results.validate_score`), sin `capped`.
- Uno menor o igual que el vigente queda como histórico y NO emite `PersonalRecordSet`; uno mayor
  queda vigente y emite (solo ids, tipo, origen y fecha).
- `achieved_on` de 2000-01-01 a hoy de Bogotá (la fixture `reloj` fija hoy = 2026-10-21).
- Socio inexistente o dado de baja: 404 `member_not_found` al escribir; la lista del baja se lee.
  Un récord NO exige autorización de datos (no es dato de salud).
- Auditoría: una fila `insert` por récord con el socio como sujeto. `is_current` y los nombres del
  catálogo salen por lote (el número de consultas no crece con la página).
La serialización de dos altas a la vez va en `test_records_concurrency.py`.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.errors import DomainError
from app.core.pagination import PageParams
from app.modules.athletes import service
from app.modules.athletes.events import PersonalRecordSet
from app.modules.members.exceptions import MemberNotFound
from tests.athletes._apoyo import (
    HOY,
    alta_record,
    auditoria_de_records,
    cuerpo_benchmark,
    cuerpo_rm,
    filas_de_records,
)
from tests.conftest import CapturarEventos, CrearUsuario, UsuarioPrueba
from tests.factories.athletes import make_record
from tests.factories.explain import capturar_sql
from tests.factories.wods import make_benchmark, make_movement
from tests.notifications._apoyo_avisos import ANTES, socio

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

PAGINA = PageParams(limit=25, offset=0)


@pytest.fixture
async def coach(usuario_real: CrearUsuario) -> UsuarioPrueba:
    return await usuario_real("coach")


async def _error(session: AsyncSession, coach: UsuarioPrueba, socio_id: UUID, cuerpo: Any) -> Any:
    with pytest.raises(DomainError) as info:
        await alta_record(session, coach.id, socio_id, cuerpo)
    return info.value


# RM ---------------------------------------------------------------------------------------------


async def test_un_rm_valido_se_guarda_manual_vigente_y_con_el_nombre_del_movimiento(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=False)
    mov = await make_movement(session, coach.id, "Back Squat", "kg")

    salida = await alta_record(session, coach.id, miembro.id, cuerpo_rm(mov.id))

    assert salida.kind == "rm" and salida.source == "manual"
    assert (salida.movement_id, salida.movement_name) == (mov.id, "Back Squat")
    assert (salida.value_g, salida.achieved_on) == (100_000, date(2026, 10, 20))
    assert (salida.benchmark_id, salida.benchmark_name, salida.score_type) == (None, None, None)
    assert (salida.level, salida.seconds, salida.rounds, salida.reps, salida.load_g) == (
        None,
        None,
        None,
        None,
        None,
    )
    assert salida.capped is False and salida.is_current is True
    assert (salida.result_id, salida.wod_id) == (None, None)
    assert (salida.invalidated_at, salida.invalidated_reason) == (None, None)
    assert salida.recorded_by == coach.id
    (fila,) = await filas_de_records(session, miembro.id)
    assert fila["id"] == salida.id and fila["source"] == "manual" and fila["kind"] == "rm"
    assert (fila["created_by"], fila["member_id"]) == (coach.id, miembro.id)
    assert (fila["result_id"], fila["wod_id"], fila["invalidated_at"]) == (None, None, None)
    assert fila["capped"] is False and fila["value_g"] == 100_000


async def test_un_rm_emite_el_evento_sin_valor_solo_si_queda_vigente(
    session: AsyncSession, coach: UsuarioPrueba, capturar_eventos: CapturarEventos
) -> None:
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Deadlift", "kg")
    recibidos = capturar_eventos(PersonalRecordSet)

    primero = await alta_record(session, coach.id, miembro.id, cuerpo_rm(mov.id))

    assert len(recibidos) == 1
    evento = recibidos[0]
    assert (evento.record_id, evento.member_id) == (primero.id, miembro.id)
    assert (evento.kind, evento.source, evento.achieved_on) == ("rm", "manual", date(2026, 10, 20))
    assert (evento.movement_id, evento.benchmark_id) == (mov.id, None)
    assert not hasattr(evento, "value_g") and not hasattr(evento, "value")


async def test_un_rm_menor_o_igual_queda_historico_y_no_emite(
    session: AsyncSession, coach: UsuarioPrueba, capturar_eventos: CapturarEventos
) -> None:
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Clean", "kg")
    recibidos = capturar_eventos(PersonalRecordSet)
    base = await alta_record(session, coach.id, miembro.id, cuerpo_rm(mov.id, value_g=100_000))

    menor = await alta_record(session, coach.id, miembro.id, cuerpo_rm(mov.id, value_g=90_000))
    # L1: el idéntico exacto da 409; con la misma marca un día después empata (gana el antiguo)
    otro_dia = cuerpo_rm(mov.id, value_g=100_000, achieved_on="2026-10-21")
    igual = await alta_record(session, coach.id, miembro.id, otro_dia)

    assert base.is_current is True
    assert menor.is_current is False and igual.is_current is False
    assert len(recibidos) == 1 and recibidos[0].record_id == base.id
    assert len(await filas_de_records(session, miembro.id)) == 3  # se guardan los tres


async def test_un_rm_mayor_pasa_a_ser_el_vigente_y_emite(
    session: AsyncSession, coach: UsuarioPrueba, capturar_eventos: CapturarEventos
) -> None:
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Snatch", "kg")
    recibidos = capturar_eventos(PersonalRecordSet)
    viejo = await alta_record(session, coach.id, miembro.id, cuerpo_rm(mov.id, value_g=100_000))

    nuevo = await alta_record(session, coach.id, miembro.id, cuerpo_rm(mov.id, value_g=110_000))

    assert nuevo.is_current is True
    assert [e.record_id for e in recibidos] == [viejo.id, nuevo.id]
    pagina = await service.list_records(session, miembro.id, PAGINA)
    vigentes = {r.id: r.is_current for r in pagina.items}
    assert vigentes == {viejo.id: False, nuevo.id: True}


async def test_el_vigente_se_calcula_por_movimiento(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    a = await make_movement(session, coach.id, "Press", "kg")
    b = await make_movement(session, coach.id, "Jerk", "kg")
    await alta_record(session, coach.id, miembro.id, cuerpo_rm(a.id, value_g=100_000))

    otro = await alta_record(session, coach.id, miembro.id, cuerpo_rm(b.id, value_g=50_000))

    assert otro.is_current is True  # el RM de otro movimiento no compite con el de `a`


@pytest.mark.parametrize("valor", [1, 1_000_000])
async def test_los_limites_de_value_g_se_aceptan(
    valor: int, session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Limite", "kg")

    salida = await alta_record(session, coach.id, miembro.id, cuerpo_rm(mov.id, value_g=valor))

    assert salida.value_g == valor


@pytest.mark.parametrize("valor", [0, -5, 1_000_001])
async def test_value_g_fuera_de_rango_422_value_g_sin_repetir_el_valor(
    valor: int, session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Fuera", "kg")

    error = await _error(session, coach, miembro.id, cuerpo_rm(mov.id, value_g=valor))

    assert (error.status, error.code, error.field) == (422, "validation_error", "value_g")
    assert str(valor) not in str(error.message)
    assert await filas_de_records(session, miembro.id) == []


async def test_un_rm_en_un_movimiento_que_no_se_mide_en_kg_422_movement_id(
    session: AsyncSession, coach: UsuarioPrueba, capturar_eventos: CapturarEventos
) -> None:
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Pull-up", "reps")
    recibidos = capturar_eventos(PersonalRecordSet)

    error = await _error(session, coach, miembro.id, cuerpo_rm(mov.id))

    assert (error.status, error.field) == (422, "movement_id")
    assert await filas_de_records(session, miembro.id) == [] and recibidos == []


async def test_un_rm_en_un_movimiento_inactivo_422_movement_id(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Retirado", "kg")
    await session.execute(
        text("UPDATE wods.movements SET is_active = false WHERE id = :i"), {"i": mov.id}
    )
    await session.commit()

    error = await _error(session, coach, miembro.id, cuerpo_rm(mov.id))

    assert (error.status, error.field) == (422, "movement_id")
    assert await filas_de_records(session, miembro.id) == []


async def test_un_rm_en_un_movimiento_inexistente_422_movement_id(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)

    error = await _error(session, coach, miembro.id, cuerpo_rm(uuid4()))

    assert (error.status, error.field) == (422, "movement_id")


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"movement_id": None}, "movement_id"),
        ({"value_g": None}, "value_g"),
        ({"benchmark_id": str(uuid4())}, "benchmark_id"),
        ({"level": "rx"}, "level"),
        ({"seconds": 10}, "seconds"),
        ({"rounds": 1}, "rounds"),
        ({"reps": 5}, "reps"),
        ({"load_g": 1_000}, "load_g"),
    ],
)
async def test_rm_exige_movimiento_y_valor_y_rechaza_los_campos_de_benchmark(
    cambios: dict[str, Any], campo: str, session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Forma", "kg")

    error = await _error(session, coach, miembro.id, cuerpo_rm(mov.id, **cambios))

    assert (error.status, error.code, error.field) == (422, "validation_error", campo)
    assert await filas_de_records(session, miembro.id) == []


# Benchmark --------------------------------------------------------------------------------------


async def test_un_benchmark_valido_se_guarda_con_nombre_y_tipo_de_marca(
    session: AsyncSession, coach: UsuarioPrueba, capturar_eventos: CapturarEventos
) -> None:
    miembro = await socio(session)
    bm = await make_benchmark(session, coach.id, "Fran", "time")
    recibidos = capturar_eventos(PersonalRecordSet)

    salida = await alta_record(session, coach.id, miembro.id, cuerpo_benchmark(bm.id))

    assert salida.kind == "benchmark" and salida.source == "manual"
    assert (salida.benchmark_id, salida.benchmark_name, salida.score_type) == (
        bm.id,
        "Fran",
        "time",
    )
    assert (salida.movement_id, salida.movement_name, salida.value_g) == (None, None, None)
    assert (salida.level, salida.seconds, salida.capped) == ("rx", 300, False)
    assert salida.is_current is True
    assert len(recibidos) == 1
    assert (recibidos[0].kind, recibidos[0].benchmark_id, recibidos[0].movement_id) == (
        "benchmark",
        bm.id,
        None,
    )


async def test_un_benchmark_mas_rapido_es_vigente_y_uno_mas_lento_es_historico(
    session: AsyncSession, coach: UsuarioPrueba, capturar_eventos: CapturarEventos
) -> None:
    miembro = await socio(session)
    bm = await make_benchmark(session, coach.id, "Helen", "time")
    recibidos = capturar_eventos(PersonalRecordSet)
    a = await alta_record(session, coach.id, miembro.id, cuerpo_benchmark(bm.id, seconds=300))

    mejor = await alta_record(session, coach.id, miembro.id, cuerpo_benchmark(bm.id, seconds=250))
    peor = await alta_record(session, coach.id, miembro.id, cuerpo_benchmark(bm.id, seconds=400))
    igual = await alta_record(
        session,
        coach.id,
        miembro.id,
        cuerpo_benchmark(bm.id, seconds=250, achieved_on="2026-10-21"),
    )

    assert (mejor.is_current, peor.is_current, igual.is_current) == (True, False, False)
    assert [e.record_id for e in recibidos] == [a.id, mejor.id]


async def test_un_scaled_rapido_no_gana_a_un_rx_lento(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    bm = await make_benchmark(session, coach.id, "Diane", "time")
    await alta_record(session, coach.id, miembro.id, cuerpo_benchmark(bm.id, seconds=300))

    escalado = await alta_record(
        session, coach.id, miembro.id, cuerpo_benchmark(bm.id, level="scaled", seconds=100)
    )

    assert escalado.is_current is False


async def test_benchmark_de_tipo_load_y_rounds_reps_comparan_por_su_marca(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    carga = await make_benchmark(session, coach.id, "Max Clean", "load")
    amrap = await make_benchmark(session, coach.id, "Cindy", "rounds_reps")

    c1 = await alta_record(
        session,
        coach.id,
        miembro.id,
        cuerpo_benchmark(carga.id, seconds=None, load_g=100_000),
    )
    c2 = await alta_record(
        session,
        coach.id,
        miembro.id,
        cuerpo_benchmark(carga.id, seconds=None, load_g=110_000),
    )
    a1 = await alta_record(
        session,
        coach.id,
        miembro.id,
        cuerpo_benchmark(amrap.id, seconds=None, rounds=5, reps=10),
    )
    a2 = await alta_record(
        session,
        coach.id,
        miembro.id,
        cuerpo_benchmark(amrap.id, seconds=None, rounds=5, reps=12),
    )

    assert (c1.is_current, c2.is_current) == (True, True)  # el segundo es mayor y gana
    assert (a1.is_current, a2.is_current) == (True, True)
    pagina = await service.list_records(session, miembro.id, PAGINA)
    assert {r.id: r.is_current for r in pagina.items} == {
        c1.id: False,
        c2.id: True,
        a1.id: False,
        a2.id: True,
    }


async def test_un_benchmark_inexistente_422_benchmark_id(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)

    error = await _error(session, coach, miembro.id, cuerpo_benchmark(uuid4()))

    assert (error.status, error.field) == (422, "benchmark_id")
    assert await filas_de_records(session, miembro.id) == []


@pytest.mark.parametrize(
    ("tipo", "cambios", "campo"),
    [
        ("time", {"seconds": None}, "seconds"),
        ("time", {"seconds": 0}, "seconds"),
        ("time", {"seconds": 86_401}, "seconds"),
        ("time", {"reps": 5}, "reps"),
        ("time", {"load_g": 5}, "load_g"),
        ("rounds_reps", {"seconds": None, "rounds": 5}, "reps"),
        ("rounds_reps", {"seconds": 10, "rounds": 5, "reps": 2}, "seconds"),
        ("reps", {"seconds": None}, "reps"),
        ("load", {"seconds": None}, "load_g"),
        ("load", {"seconds": None, "load_g": 1_000_001}, "load_g"),
    ],
)
async def test_una_marca_que_no_cumple_el_tipo_422_con_el_campo(
    tipo: str, cambios: dict[str, Any], campo: str, session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    bm = await make_benchmark(session, coach.id, f"Bm {tipo}", tipo)

    error = await _error(session, coach, miembro.id, cuerpo_benchmark(bm.id, **cambios))

    assert (error.status, error.code, error.field) == (422, "validation_error", campo)
    assert await filas_de_records(session, miembro.id) == []


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"benchmark_id": None}, "benchmark_id"),
        ({"level": None}, "level"),
        ({"movement_id": str(uuid4())}, "movement_id"),
        ({"value_g": 1_000}, "value_g"),
    ],
)
async def test_benchmark_exige_id_y_nivel_y_rechaza_los_campos_de_rm(
    cambios: dict[str, Any], campo: str, session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    bm = await make_benchmark(session, coach.id, "Forma Bm", "time")

    error = await _error(session, coach, miembro.id, cuerpo_benchmark(bm.id, **cambios))

    assert (error.status, error.field) == (422, campo)


# Fecha ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("dia", ["2000-01-01", HOY.isoformat()])
async def test_achieved_on_en_los_limites_se_acepta(
    dia: str, session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Fecha", "kg")

    salida = await alta_record(session, coach.id, miembro.id, cuerpo_rm(mov.id, achieved_on=dia))

    assert salida.achieved_on.isoformat() == dia


@pytest.mark.parametrize("dia", ["1999-12-31", "2026-10-22", "2030-01-01"])
async def test_achieved_on_fuera_de_rango_422_achieved_on(
    dia: str, session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Fecha mala", "kg")

    error = await _error(session, coach, miembro.id, cuerpo_rm(mov.id, achieved_on=dia))

    assert (error.status, error.field) == (422, "achieved_on")
    assert await filas_de_records(session, miembro.id) == []


# Socio ------------------------------------------------------------------------------------------


async def test_socio_inexistente_o_dado_de_baja_404_al_escribir(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    mov = await make_movement(session, coach.id, "Baja", "kg")
    baja = await socio(session, deleted_at=ANTES, status="inactive")
    baja_id = baja.id

    with pytest.raises(MemberNotFound):
        await alta_record(session, coach.id, uuid4(), cuerpo_rm(mov.id))
    with pytest.raises(MemberNotFound):
        await alta_record(session, coach.id, baja_id, cuerpo_rm(mov.id))

    assert await filas_de_records(session, baja_id) == []


async def test_la_lista_de_un_socio_dado_de_baja_se_lee_y_la_de_uno_inexistente_404(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    baja = await socio(session, deleted_at=ANTES, status="inactive")
    await make_record(session, baja.id)
    baja_id = baja.id

    pagina = await service.list_records(session, baja_id, PAGINA)

    assert pagina.total == 1
    with pytest.raises(MemberNotFound):
        await service.list_records(session, uuid4(), PAGINA)


async def test_un_record_no_exige_autorizacion_de_datos(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session, consentido=False)
    mov = await make_movement(session, coach.id, "Sin consentimiento", "kg")

    salida = await alta_record(session, coach.id, miembro.id, cuerpo_rm(mov.id))

    assert salida.is_current is True


# Auditoría --------------------------------------------------------------------------------------


async def test_el_alta_deja_una_fila_insert_con_el_socio_como_sujeto(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Auditado", "kg")

    salida = await alta_record(session, coach.id, miembro.id, cuerpo_rm(mov.id))

    filas = await auditoria_de_records(session, salida.id)
    assert [f["action"] for f in filas] == ["insert"]
    assert filas[0]["user_id"] == coach.id
    assert filas[0]["subject_member_id"] == miembro.id
    assert filas[0]["after"]["source"] == "manual"
    assert filas[0]["after"]["value_g"] == 100_000


# Lista ------------------------------------------------------------------------------------------


async def test_la_lista_ordena_por_fecha_y_alta_descendentes_y_trae_los_nombres(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Orden", "kg")
    bm = await make_benchmark(session, coach.id, "Orden Bm", "time")
    viejo = await make_record(
        session, miembro.id, movement_id=mov.id, achieved_on=date(2026, 1, 5), actor=coach.id
    )
    nuevo = await make_record(
        session, miembro.id, movement_id=mov.id, value_g=120_000, achieved_on=date(2026, 9, 5),
        actor=coach.id,
    )  # fmt: skip
    marca = await make_record(
        session, miembro.id, kind="benchmark", benchmark_id=bm.id, achieved_on=date(2026, 9, 5),
        actor=coach.id,
    )  # fmt: skip

    pagina = await service.list_records(session, miembro.id, PAGINA)

    assert [r.id for r in pagina.items] == [marca.id, nuevo.id, viejo.id]
    assert pagina.total == 3
    por_id = {r.id: r for r in pagina.items}
    assert (
        por_id[nuevo.id].movement_name == "Orden" and por_id[marca.id].benchmark_name == "Orden Bm"
    )
    assert por_id[marca.id].score_type == "time"
    assert por_id[nuevo.id].recorded_by == coach.id
    assert por_id[nuevo.id].recorded_by_name  # «Registró»: el nombre del usuario


async def test_la_lista_filtra_por_kind_y_pagina(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Filtro", "kg")
    bm = await make_benchmark(session, coach.id, "Filtro Bm", "time")
    await make_record(session, miembro.id, movement_id=mov.id, actor=coach.id)
    await make_record(session, miembro.id, movement_id=mov.id, value_g=90_000, actor=coach.id)
    await make_record(session, miembro.id, kind="benchmark", benchmark_id=bm.id, actor=coach.id)

    rms = await service.list_records(session, miembro.id, PAGINA, kind="rm")
    marcas = await service.list_records(session, miembro.id, PAGINA, kind="benchmark")
    corta = await service.list_records(session, miembro.id, PageParams(limit=1, offset=1))

    assert (rms.total, marcas.total) == (2, 1)
    assert all(r.kind == "rm" for r in rms.items) and marcas.items[0].kind == "benchmark"
    assert (corta.total, len(corta.items), corta.limit, corta.offset) == (3, 1, 1, 1)


async def test_los_invalidados_salen_solo_con_include_invalidated_y_no_son_vigentes(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Invalidado", "kg")
    vivo = await make_record(
        session, miembro.id, movement_id=mov.id, value_g=100_000, actor=coach.id
    )
    malo = await make_record(
        session, miembro.id, movement_id=mov.id, value_g=150_000, invalidated=True, actor=coach.id
    )

    por_defecto = await service.list_records(session, miembro.id, PAGINA)
    todos = await service.list_records(session, miembro.id, PAGINA, include_invalidated=True)

    assert [r.id for r in por_defecto.items] == [vivo.id] and por_defecto.total == 1
    assert por_defecto.items[0].is_current is True  # el invalidado más alto no compite
    por_id = {r.id: r for r in todos.items}
    assert set(por_id) == {vivo.id, malo.id} and todos.total == 2
    assert por_id[malo.id].is_current is False
    assert por_id[malo.id].invalidated_at is not None
    assert por_id[malo.id].invalidated_reason == "manual_error"
    assert por_id[vivo.id].is_current is True


async def test_is_current_sale_con_un_numero_de_consultas_que_no_crece_con_la_pagina(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    mov = await make_movement(session, coach.id, "Consultas", "kg")
    for i in range(2):
        await make_record(
            session, miembro.id, movement_id=mov.id, value_g=50_000 + i, actor=coach.id
        )
    session.expunge_all()
    with capturar_sql(session, "athletes.personal_records") as pocas:
        await service.list_records(session, miembro.id, PAGINA)
    for i in range(8):
        await make_record(
            session, miembro.id, movement_id=uuid4(), value_g=40_000 + i, actor=coach.id
        )
    session.expunge_all()
    with capturar_sql(session, "athletes.personal_records") as muchas:
        pagina = await service.list_records(session, miembro.id, PAGINA)

    assert len(pagina.items) == 10
    assert len(muchas) == len(pocas) and len(muchas) <= 3  # página, total y UNA de vigentes


async def test_el_actor_de_la_fabrica_es_quien_registra(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    miembro = await socio(session)
    registro = await make_record(session, miembro.id, actor=coach.id)

    with actor_scope(coach.id):
        pagina = await service.list_records(session, miembro.id, PAGINA)

    assert pagina.items[0].id == registro.id and pagina.items[0].recorded_by == coach.id

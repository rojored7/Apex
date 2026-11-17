"""`athletes.service.list_rms` con PostgreSQL real (S9-C2, US-184 CA2; blueprint §3 ruta 6). Rojo.

- Un ítem por movimiento con su RM vigente (valor en gramos, origen, fecha), por nombre.
- El SQL `DISTINCT ON (movement_id)` da EXACTAMENTE lo mismo que `rules.pick_current` sobre los
  mismos datos, con empates de valor, fecha, alta e id (S9-D10, N-45).
- Los invalidados quedan fuera; los benchmarks y los récords de otro socio, también.
- `kind` va como literal SQL y el plan genérico usa `ix_personal_records_rm` (S8-D50, S9-D55).
- Pagina y acepta `q` por nombre (regla de datos 6); el socio dado de baja se lee; 404 si no existe.
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.core.pagination import PageParams
from app.modules.athletes import reads, service
from app.modules.athletes.models import PersonalRecord
from app.modules.athletes.rules import RecordRow, pick_current
from app.modules.members.exceptions import MemberNotFound
from tests.factories.athletes import make_record
from tests.factories.explain import capturar_sql
from tests.factories.members import make_members
from tests.factories.users import make_user
from tests.factories.wods import make_benchmark, make_movement
from tests.notifications._apoyo_avisos import socio

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

PAGINA = PageParams(limit=25, offset=0)
BASE = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


async def _mov(session: AsyncSession, nombre: str) -> UUID:
    coach = await make_user(session, role="coach")
    return (await make_movement(session, coach.id, nombre, "kg")).id


@pytest.fixture
async def mundo(session: AsyncSession) -> dict[str, UUID]:
    sentadilla = await _mov(session, "Back Squat")
    peso_muerto = await _mov(session, "Deadlift")
    envion = await _mov(session, "Clean & Jerk")
    miembro = await socio(session, consentido=False)
    otro = (await make_members(session, 1))[0]
    return {
        "socio": miembro.id,
        "otro": otro.id,
        "sentadilla": sentadilla,
        "muerto": peso_muerto,
        "envion": envion,
    }


async def test_un_item_por_movimiento_ordenado_por_nombre(
    session: AsyncSession, mundo: dict[str, UUID]
) -> None:
    s = mundo["socio"]
    await make_record(session, s, movement_id=mundo["sentadilla"], value_g=100_000)
    await make_record(session, s, movement_id=mundo["sentadilla"], value_g=120_000)
    await make_record(session, s, movement_id=mundo["muerto"], value_g=150_000)
    await make_record(session, s, movement_id=mundo["envion"], value_g=80_000)

    pagina = await service.list_rms(session, s, PAGINA)

    assert pagina.total == 3
    assert [(i.movement_name, i.value_g) for i in pagina.items] == [
        ("Back Squat", 120_000),
        ("Clean & Jerk", 80_000),
        ("Deadlift", 150_000),
    ]


async def test_el_item_trae_record_origen_y_fecha(
    session: AsyncSession, mundo: dict[str, UUID]
) -> None:
    s = mundo["socio"]
    manual = await make_record(
        session, s, movement_id=mundo["muerto"], value_g=150_000, achieved_on=date(2026, 9, 3)
    )
    derivado = await make_record(
        session,
        s,
        movement_id=mundo["sentadilla"],
        value_g=130_000,
        source="derived",
        achieved_on=date(2026, 9, 10),
    )

    pagina = await service.list_rms(session, s, PAGINA)

    por_mov = {i.movement_id: i for i in pagina.items}
    assert (por_mov[mundo["muerto"]].record_id, por_mov[mundo["muerto"]].source) == (
        manual.id,
        "manual",
    )
    assert por_mov[mundo["muerto"]].achieved_on == date(2026, 9, 3)
    assert (por_mov[mundo["sentadilla"]].record_id, por_mov[mundo["sentadilla"]].source) == (
        derivado.id,
        "derived",
    )
    assert set(pagina.items[0].model_dump()) == {
        "movement_id",
        "movement_name",
        "record_id",
        "value_g",
        "source",
        "achieved_on",
    }


async def test_los_invalidados_quedan_fuera_y_el_siguiente_es_el_vigente(
    session: AsyncSession, mundo: dict[str, UUID]
) -> None:
    s = mundo["socio"]
    mejor = await make_record(session, s, movement_id=mundo["sentadilla"], value_g=120_000)
    anterior = await make_record(session, s, movement_id=mundo["sentadilla"], value_g=100_000)
    await make_record(session, s, movement_id=mundo["muerto"], value_g=200_000, invalidated=True)
    assert mejor.id != anterior.id

    antes = await service.list_rms(session, s, PAGINA)
    await session.execute(
        text(
            "UPDATE athletes.personal_records SET invalidated_at = clock_timestamp(), "
            "invalidated_reason = 'manual_error', invalidated_by = created_by, "
            "updated_at = clock_timestamp() WHERE id = :i"
        ),
        {"i": mejor.id},
    )
    despues = await service.list_rms(session, s, PAGINA)

    assert [(i.record_id, i.value_g) for i in antes.items] == [(mejor.id, 120_000)]
    assert [(i.record_id, i.value_g) for i in despues.items] == [(anterior.id, 100_000)]


async def test_los_benchmarks_y_los_records_de_otro_socio_no_aparecen(
    session: AsyncSession, mundo: dict[str, UUID]
) -> None:
    s = mundo["socio"]
    fran = (await make_benchmark(session, await _coach(session), "Fran", "time")).id
    await make_record(session, s, kind="benchmark", benchmark_id=fran)
    await make_record(session, mundo["otro"], movement_id=mundo["muerto"], value_g=999_000)
    await make_record(session, s, movement_id=mundo["envion"], value_g=70_000)

    pagina = await service.list_rms(session, s, PAGINA)

    assert [i.value_g for i in pagina.items] == [70_000]


async def _coach(session: AsyncSession) -> UUID:
    return (await make_user(session, role="coach")).id


async def test_socio_sin_records_da_pagina_vacia(
    session: AsyncSession, mundo: dict[str, UUID]
) -> None:
    pagina = await service.list_rms(session, mundo["socio"], PAGINA)

    assert (pagina.total, pagina.items) == (0, [])


async def test_un_movimiento_fuera_del_catalogo_sale_sin_nombre_al_final(
    session: AsyncSession, mundo: dict[str, UUID]
) -> None:
    s = mundo["socio"]
    await make_record(session, s, movement_id=mundo["muerto"], value_g=150_000)
    await make_record(session, s, movement_id=uuid4(), value_g=60_000)

    pagina = await service.list_rms(session, s, PAGINA)

    assert [i.movement_name for i in pagina.items] == ["Deadlift", None]


async def test_pagina_y_total_reflejan_el_numero_de_movimientos(
    session: AsyncSession, mundo: dict[str, UUID]
) -> None:
    s = mundo["socio"]
    for clave in ("sentadilla", "muerto", "envion"):
        await make_record(session, s, movement_id=mundo[clave])

    p1 = await service.list_rms(session, s, PageParams(limit=2, offset=0))
    p2 = await service.list_rms(session, s, PageParams(limit=2, offset=2))
    p3 = await service.list_rms(session, s, PageParams(limit=2, offset=9))

    assert (p1.total, len(p1.items), p2.total, len(p2.items)) == (3, 2, 3, 1)
    assert (p3.total, p3.items) == (3, [])
    assert [i.movement_name for i in p1.items + p2.items] == [
        "Back Squat",
        "Clean & Jerk",
        "Deadlift",
    ]


async def test_q_filtra_por_nombre_sin_tildes_ni_mayusculas_y_el_total_lo_refleja(
    session: AsyncSession, mundo: dict[str, UUID]
) -> None:
    s = mundo["socio"]
    for clave in ("sentadilla", "muerto", "envion"):
        await make_record(session, s, movement_id=mundo[clave])
    tilde = await _mov(session, "Sentadilla Frontal Ñandú")
    await make_record(session, s, movement_id=tilde)

    por_nombre = await service.list_rms(session, s, PAGINA, q="DEAD")
    por_tilde = await service.list_rms(session, s, PAGINA, q="nandu")
    ninguno = await service.list_rms(session, s, PAGINA, q="zzz")
    comodin = await service.list_rms(session, s, PAGINA, q="%")

    assert [i.movement_name for i in por_nombre.items] == ["Deadlift"]
    assert por_nombre.total == 1
    assert [i.movement_name for i in por_tilde.items] == ["Sentadilla Frontal Ñandú"]
    assert ninguno.total == 0 and comodin.total == 0


async def test_un_socio_dado_de_baja_tambien_se_lee(
    session: AsyncSession, mundo: dict[str, UUID]
) -> None:
    s = mundo["socio"]
    await make_record(session, s, movement_id=mundo["muerto"], value_g=150_000)
    await session.execute(
        text("UPDATE members.members SET deleted_at = now() WHERE id = :i"), {"i": s}
    )

    pagina = await service.list_rms(session, s, PAGINA)

    assert pagina.total == 1


async def test_socio_inexistente_da_404_member_not_found(session: AsyncSession) -> None:
    with pytest.raises(MemberNotFound) as info:
        await service.list_rms(session, uuid4(), PAGINA)

    assert isinstance(info.value, DomainError) and info.value.status == 404


async def test_leer_los_rms_no_deja_filas_de_cifrado_ni_de_auditoria(
    session: AsyncSession, mundo: dict[str, UUID]
) -> None:
    s = mundo["socio"]
    await make_record(session, s, movement_id=mundo["muerto"])
    ops = await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops"))
    audit = await session.scalar(text("SELECT count(*) FROM audit.audit_log"))

    await service.list_rms(session, s, PAGINA)

    assert await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops")) == ops
    assert await session.scalar(text("SELECT count(*) FROM audit.audit_log")) == audit


# --- SQL == pick_current ---------------------------------------------------------------------


def _fila(r: PersonalRecord) -> RecordRow:
    return RecordRow(
        id=r.id,
        kind=r.kind,
        movement_id=r.movement_id,
        benchmark_id=r.benchmark_id,
        value_g=r.value_g,
        level=r.level,
        seconds=r.seconds,
        rounds=r.rounds,
        reps=r.reps,
        load_g=r.load_g,
        capped=r.capped,
        achieved_on=r.achieved_on,
        created_at=r.created_at,
        invalidated_at=r.invalidated_at,
        source=r.source,
    )


async def test_el_distinct_on_da_lo_mismo_que_pick_current_con_empates(
    session: AsyncSession, mundo: dict[str, UUID]
) -> None:
    s = mundo["socio"]
    azar = random.Random(42)  # noqa: S311
    movimientos = [mundo["sentadilla"], mundo["muerto"], mundo["envion"]]
    n = 0
    for _ in range(45):
        n += 1
        await make_record(
            session,
            s,
            movement_id=azar.choice(movimientos),
            value_g=azar.choice([90_000, 100_000, 100_000, 110_000]),
            achieved_on=date(2026, 9, azar.randint(1, 4)),
            # `id` ascendente por dentro y alta repetida: fuerza los empates hasta el id
            created_at=BASE + timedelta(minutes=azar.choice([0, 0, 1, 2])),
            id=UUID(int=azar.getrandbits(100)),
            invalidated=azar.random() < 0.15,
        )

    consulta = select(PersonalRecord).where(PersonalRecord.member_id == s)
    filas = list((await session.scalars(consulta)).all())
    esperado: dict[UUID, UUID] = {}
    for m in movimientos:
        elegido = pick_current([_fila(f) for f in filas if f.movement_id == m])
        if elegido is not None:
            esperado[m] = elegido.id
    assert len(esperado) >= 2

    desde_sql = {
        f.movement_id: f.id for f in (await session.scalars(reads.current_rms_query(s))).all()
    }

    assert desde_sql == esperado
    pagina = await service.list_rms(session, s, PAGINA)
    assert {i.movement_id: i.record_id for i in pagina.items} == esperado


# --- literal de `kind` e índice ---------------------------------------------------------------


def test_la_consulta_lleva_kind_como_literal_y_la_columna_desnuda() -> None:
    sql = str(reads.current_rms_query(uuid4()).compile(dialect=postgresql.dialect()))

    assert "kind = 'rm'" in sql and "kind = %(" not in sql
    assert "DISTINCT ON" in sql.upper()
    assert "invalidated_at IS NULL" in sql


async def test_usa_ix_personal_records_rm_con_plan_generico(session: AsyncSession) -> None:
    with capturar_sql(session, "athletes.personal_records") as vistas:
        await reads.list_rms(session, (await make_members(session, 1))[0].id, PAGINA)
    sql, parametros = vistas[0]
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    await session.execute(text("SET LOCAL plan_cache_mode = force_generic_plan"))
    conexion = await session.connection()
    await conexion.exec_driver_sql(f"PREPARE p_rms AS {sql}")
    args = ", ".join(f"'{p}'" for p in tuple(parametros))
    filas = await conexion.exec_driver_sql(f"EXPLAIN EXECUTE p_rms({args})")
    plan = "\n".join(str(f[0]) for f in filas.all())

    assert "ix_personal_records_rm" in plan, plan
    assert "Seq Scan" not in plan, plan

"""Siembra de benchmarks (S8-A2, US-166, N-46; S8-D6, L-6). Privado del módulo.

`BENCHMARKS` es la lista fija (pura) de los doce benchmarks clásicos. `seed_benchmarks(session)`
los inserta con `INSERT ... ON CONFLICT (name_norm) DO NOTHING`: la segunda corrida no crea nada y
una edición (o un nombre que solo difiere en mayúsculas o espacios) nunca se pisa. Como el
`INSERT` de Core no pasa por el hook del ORM, escribe a mano una fila de auditoría `insert` por
cada benchmark CREADO: el conteo que devuelve es el de esas filas. El actor lo fija quien llama
(`unit_of_work` del CLI); la transacción es la del llamador (una sola, N-15).
"""

from __future__ import annotations

import logging
from typing import Final, NamedTuple
from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record, serialize_row
from app.core.context import get_actor
from app.modules.wods.models import Benchmark
from app.modules.wods.rules import normalize_movement_name

logger = logging.getLogger("app.wods")


class SeedBenchmark(NamedTuple):
    name: str
    score_type: str
    description: str


BENCHMARKS: Final[tuple[SeedBenchmark, ...]] = (
    SeedBenchmark(
        "Fran",
        "time",
        "21-15-9 repeticiones de thrusters (43 kg / 30 kg) y dominadas. Por tiempo.",
    ),
    SeedBenchmark(
        "Grace", "time", "30 clean and jerk (61 kg / 43 kg) lo más rápido posible. Por tiempo."
    ),
    SeedBenchmark(
        "Helen",
        "time",
        "3 rondas: 400 m de carrera, 21 swings con kettlebell (24 kg / 16 kg) y 12 dominadas. "
        "Por tiempo.",
    ),
    SeedBenchmark(
        "Diane",
        "time",
        "21-15-9 repeticiones de peso muerto (102 kg / 70 kg) y handstand push-ups. Por tiempo.",
    ),
    SeedBenchmark(
        "Elizabeth",
        "time",
        "21-15-9 repeticiones de cleans (61 kg / 43 kg) y fondos en anillas. Por tiempo.",
    ),
    SeedBenchmark("Isabel", "time", "30 snatch (61 kg / 43 kg) lo más rápido posible. Por tiempo."),
    SeedBenchmark("Karen", "time", "150 wall balls (9 kg / 6 kg) al blanco. Por tiempo."),
    SeedBenchmark(
        "Annie",
        "time",
        "50-40-30-20-10 repeticiones de doble salto de cuerda y abdominales. Por tiempo.",
    ),
    SeedBenchmark(
        "Jackie",
        "time",
        "1.000 m de remo, 50 thrusters (20 kg / 15 kg) y 30 dominadas. Por tiempo.",
    ),
    SeedBenchmark(
        "Cindy",
        "rounds_reps",
        "AMRAP de 20 minutos: 5 dominadas, 10 flexiones y 15 sentadillas al aire. "
        "Rondas y repeticiones.",
    ),
    SeedBenchmark(
        "Mary",
        "rounds_reps",
        "AMRAP de 20 minutos: 5 handstand push-ups, 10 sentadillas a una pierna y 15 dominadas. "
        "Rondas y repeticiones.",
    ),
    SeedBenchmark(
        "Murph",
        "time",
        "1,6 km de carrera, 100 dominadas, 200 flexiones, 300 sentadillas al aire y 1,6 km de "
        "carrera. Por tiempo.",
    ),
)


async def seed_benchmarks(session: AsyncSession) -> int:
    """Crea los benchmarks que falten y devuelve cuántos creó (la segunda corrida da 0)."""
    actor = get_actor()
    creados = 0
    for definido in BENCHMARKS:
        nuevo_id = uuid4()
        valores = {
            "id": nuevo_id,
            "name": definido.name,
            "name_norm": normalize_movement_name(definido.name),
            "description": definido.description,
            "score_type": definido.score_type,
            "created_by": actor,
        }
        consulta = (
            pg_insert(Benchmark)
            .values(**valores)
            .on_conflict_do_nothing(index_elements=[Benchmark.name_norm])
            .returning(Benchmark.id)
        )
        if (await session.execute(consulta)).scalar_one_or_none() is None:
            continue
        creados += 1
        await record(
            session,
            action="insert",
            table_name="wods.benchmarks",
            record_id=nuevo_id,
            before=None,
            after=serialize_row(valores, encrypted=frozenset(), redacted=frozenset()),
            user_id=actor,
        )
    logger.info("wods: siembra de benchmarks", extra={"benchmarks_created": creados})
    return creados


__all__ = ["BENCHMARKS", "SeedBenchmark", "seed_benchmarks"]

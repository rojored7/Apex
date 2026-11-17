"""Apoyo de las pruebas de invalidación de récords (S9-B5, US-181; S9-D10, S9-D11, S9-D30, S9-D42).

Construye escenas con VARIOS WODs de un mismo socio (hay un solo WOD por día: `uq_wods_date`) y los
tres movimientos de la vida de un resultado: registrar, corregir y anular, siempre como el service
(una petición = una transacción dentro del savepoint de la prueba).

- `escena_serie(session, primer_dia)`: escena de carga cuyo primer WOD cae en `primer_dia`.
- `wod_en(session, e, dia, titulo, **cambios)`: otro WOD con los mismos movimientos.
- `poner_en(session, e, wod_id, **marca)`: `record_result` en ese WOD; `anterior_id` corrige.
- `anular_resultado(session, e, result_id, by=...)`: `void_result` como el admin dado.
- `vivos(filas, kind)`, `invalidados(filas)`, `por_resultado(filas, result_id)`: lecturas de las
  filas crudas de `athletes.personal_records`.
- `ContadorMarcas`: envuelve `results.service.member_marks` y cuenta las llamadas.
"""

from __future__ import annotations

import dataclasses
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.results import service as results_service
from app.modules.results.schemas import ResultOut, VoidIn
from tests.factories.wods import make_wod
from tests.results._apoyo import Escena, escena, registrar


async def escena_serie(
    session: AsyncSession, primer_dia: str, *, score_type: str = "load"
) -> Escena:
    """Un socio, un coach y el primer WOD (de `score_type`) en `primer_dia`, sin clase."""
    return await escena(
        session,
        score_type=score_type,
        time_cap_s=None if score_type == "load" else 600,
        fecha=primer_dia,
        con_clase=False,
    )


async def wod_en(session: AsyncSession, e: Escena, dia: str, titulo: str, **cambios: Any) -> UUID:
    """Otro WOD del mismo coach y con los MISMOS movimientos (mismo principal) en `dia`."""
    cuerpo: dict[str, Any] = {
        "date": dia,
        "title": titulo,
        "score_type": "load",
        "time_cap_s": None,
    }
    cuerpo.update(cambios)
    return (await make_wod(session, e.coach, list(e.movimientos), **cuerpo)).id


async def poner_en(
    session: AsyncSession, e: Escena, wod_id: UUID, *, anterior_id: UUID | None = None, **marca: Any
) -> ResultOut:
    """Registra (o corrige, con `anterior_id`) el resultado del socio en ese WOD, como el coach."""
    if anterior_id is not None:
        marca["supersedes_id"] = anterior_id
    return await registrar(session, dataclasses.replace(e, wod_id=wod_id), **marca)


async def cargar(
    session: AsyncSession, e: Escena, wod_id: UUID, load_g: int, **marca: Any
) -> ResultOut:
    """Un resultado de carga (`rx`) en gramos enteros, sin tiempo."""
    return await poner_en(session, e, wod_id, load_g=load_g, seconds=None, **marca)


async def anular_resultado(
    session: AsyncSession, admin: UUID, result_id: UUID, motivo: str = "Socio equivocado"
) -> ResultOut:
    with actor_scope(admin):
        return await results_service.void_result(
            session, result_id, VoidIn(reason=motivo), by=admin
        )


def vivos(filas: list[dict[str, Any]], kind: str = "rm") -> list[dict[str, Any]]:
    return [f for f in filas if f["kind"] == kind and f["invalidated_at"] is None]


def invalidados(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [f for f in filas if f["invalidated_at"] is not None]


def por_resultado(filas: list[dict[str, Any]], result_id: UUID, kind: str = "rm") -> dict[str, Any]:
    halladas = [f for f in filas if f["result_id"] == result_id and f["kind"] == kind]
    assert len(halladas) == 1, f"se esperaba un récord de {result_id}, hay {len(halladas)}"
    return halladas[0]


class ContadorMarcas:
    """Cuenta las llamadas a `results.service.member_marks` (la reposición lo llama una vez por
    objetivo tocado; sin récord invalidado no se llama nunca)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.llamadas: list[dict[str, Any]] = []
        original = results_service.member_marks

        async def contar(session: AsyncSession, member_id: UUID, **filtros: Any) -> Any:
            self.llamadas.append({"member_id": member_id, **filtros})
            return await original(session, member_id, **filtros)

        monkeypatch.setattr(results_service, "member_marks", contar)

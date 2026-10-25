"""Resumen de membresías y su caché de proceso (US-092; S3-D53, S3-D60, E11, E13). Privado (D7).

Se separó de `queries.py` en la revisión de Fase 4 del Sprint 3 (M2 y PL5, S3-D90) sin cambiar
el comportamiento; la fachada `service.py` re-exporta `summary`.

- `summary(session, *, today=None) -> MembershipSummaryOut`: la caché de proceso
  (`SummaryCache`, clave `(hoy, expiring_days)`, TTL `SUMMARY_CACHE_TTL_S`) y, si no sirve,
  `members.service.active_ids` en lotes de `SUMMARY_ID_BATCH` (una sentencia por lote:
  `queries._summary_counts` con `DISTINCT ON (member_id)` ordenado por
  `queries.member_status_rank_expr` y `count(*) FILTER` por estado), sumando los lotes.
- `reset_summary_cache()` y `configure_summary_cache(ttl_s)`: vaciar la caché y fijar su TTL
  (las pruebas: `sin_cache_de_resumen` pone 0).
- `_mark_summary_dirty(evento, session)`: el handler de los eventos que cambian el resumen
  (`MembershipSold`, `MembershipActivated`, `MembershipActivationReverted`, `MembershipFrozen`,
  `MembershipCancelled`, `PaymentRegistered`, `PaymentVoided` y, desde Fase 4, `MemberDeactivated`
  y `MemberReactivated`, S3-D89; suscrito al final de `service.py`): solo escribe
  `session.info[SUMMARY_DIRTY_KEY] = True`. La caché se vacía después del commit real (un
  listener de `Session` que ignora la liberación de un SAVEPOINT, E13) y la marca se descarta con
  el rollback de la transacción (no con el de un SAVEPOINT). Los dos listeners se registran una
  sola vez al importar este archivo (`event.contains`).

Restricción (S3-D53, ampliada en S3-D93): la caché es del PROCESO. La invalidación solo ocurre en
el proceso que confirma; el api corre en un solo proceso de Uvicorn (sin `--workers`, RUNBOOK §4).
Con varios procesos, otro proceso serviría su entrada hasta que venza el TTL.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

from app.core.clock import current_clock
from app.core.events import DomainEvent
from app.core.pagination import chunked
from app.modules.members import service as members_service
from app.modules.memberships import queries
from app.modules.memberships.schemas import MembershipSummaryOut

SUMMARY_ID_BATCH: Final = 1000
"""Ids de socios por sentencia del resumen (S3-D60): `member_id = ANY(:lote)`."""
SUMMARY_CACHE_TTL_S: Final = 30
"""Vida de una entrada de la caché del resumen, en segundos del reloj de la app (S3-D53)."""
SUMMARY_DIRTY_KEY: Final = "apex.summary_dirty"
"""Marca en `session.info` de una transacción que cambió el resumen (E11, E13)."""

SUMMARY_CACHE_MAX_ENTRIES: Final = 32
"""Tope de entradas de la caché del resumen (una por día y `expiring_days`; LOW-3 de B7)."""

type SummaryKey = tuple[date, int]


@dataclass(frozen=True, slots=True)
class _SummaryEntry:
    value: MembershipSummaryOut
    stored_at: datetime


class SummaryCache:
    """Caché de proceso del resumen (S3-D53): clave `(hoy, expiring_days)`; una entrada sirve
    mientras `current_clock().now_utc() - stored_at < ttl_s` (con `ttl_s = 0` nunca sirve).

    `generation` sube con cada `clear()`: un `put` con la generación leída antes de calcular se
    descarta si entre tanto se vació (un commit que invalidó mientras otra petición leía; MEDIUM-2
    de la revisión de B7). Como mucho `SUMMARY_CACHE_MAX_ENTRIES` entradas (LOW-3): `put` purga
    las vencidas y, si sigue lleno, saca la más vieja."""

    def __init__(self, ttl_s: int = SUMMARY_CACHE_TTL_S) -> None:
        self.ttl_s = ttl_s
        self.generation = 0
        self._entries: dict[SummaryKey, _SummaryEntry] = {}

    def _age_s(self, entrada: _SummaryEntry) -> float:
        return (current_clock().now_utc() - entrada.stored_at).total_seconds()

    def get(self, key: SummaryKey) -> MembershipSummaryOut | None:
        entrada = self._entries.get(key)
        if entrada is None:
            return None
        if self._age_s(entrada) >= self.ttl_s:
            del self._entries[key]
            return None
        return entrada.value

    def put(
        self, key: SummaryKey, value: MembershipSummaryOut, generation: int | None = None
    ) -> None:
        if self.ttl_s <= 0 or (generation is not None and generation != self.generation):
            return
        for vencida in [k for k, e in self._entries.items() if self._age_s(e) >= self.ttl_s]:
            del self._entries[vencida]
        if key not in self._entries and len(self._entries) >= SUMMARY_CACHE_MAX_ENTRIES:
            del self._entries[min(self._entries, key=lambda k: self._entries[k].stored_at)]
        self._entries[key] = _SummaryEntry(value, current_clock().now_utc())

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self.generation += 1
        self._entries.clear()


_summary_cache = SummaryCache()
_summary_lock: tuple[asyncio.AbstractEventLoop, asyncio.Lock] | None = None


def reset_summary_cache() -> None:
    """Vacía la caché del resumen."""
    _summary_cache.clear()


def configure_summary_cache(ttl_s: int) -> None:
    """Fija el TTL de la caché del resumen (`0` la apaga) y la vacía."""
    if ttl_s < 0:
        raise ValueError("ttl_s no puede ser negativo")
    _summary_cache.ttl_s = ttl_s
    _summary_cache.clear()


def _summary_cache_get(key: SummaryKey) -> MembershipSummaryOut | None:
    return _summary_cache.get(key)


def _summary_cache_put(
    key: SummaryKey, value: MembershipSummaryOut, generation: int | None = None
) -> None:
    _summary_cache.put(key, value, generation)


async def _mark_summary_dirty(evento: DomainEvent, session: AsyncSession) -> None:
    """Handler de los eventos que cambian el resumen (docstring del módulo): solo marca la
    transacción; la caché se vacía tras el commit real (`_invalidate_summary_after_commit`)."""
    session.info[SUMMARY_DIRTY_KEY] = True


def _invalidate_summary_after_commit(session: Session) -> None:
    """`after_commit` de `Session` (E11, E13): se despacha también al liberar un SAVEPOINT, antes
    de cerrarlo; ahí todavía no hay commit real y no se toca nada."""
    if session.in_nested_transaction():
        return
    if session.info.pop(SUMMARY_DIRTY_KEY, False):
        _summary_cache.clear()


def _forget_summary_mark_after_rollback(
    session: Session, previous_transaction: SessionTransaction
) -> None:
    """`after_soft_rollback` (E13): el rollback de la transacción descarta la marca; el de un
    SAVEPOINT no (la transacción que lo contiene ya pudo cambiar el resumen)."""
    if not previous_transaction.nested:
        session.info.pop(SUMMARY_DIRTY_KEY, None)


if not event.contains(Session, "after_commit", _invalidate_summary_after_commit):
    event.listen(Session, "after_commit", _invalidate_summary_after_commit)
if not event.contains(Session, "after_soft_rollback", _forget_summary_mark_after_rollback):
    event.listen(Session, "after_soft_rollback", _forget_summary_mark_after_rollback)


def _summary_flight_lock() -> asyncio.Lock:
    """Un solo cálculo del resumen a la vez por proceso y bucle (MEDIUM-2 de la revisión de B7):
    las peticiones que llegan con la caché vacía esperan al primero y leen lo que dejó."""
    global _summary_lock
    bucle = asyncio.get_running_loop()
    if _summary_lock is None or _summary_lock[0] is not bucle:
        _summary_lock = (bucle, asyncio.Lock())
    return _summary_lock[1]


async def _summary_compute(
    session: AsyncSession, today: date, expiring_days: int
) -> MembershipSummaryOut:
    """`members.active_ids` y una sentencia por lote de `SUMMARY_ID_BATCH` (leído al llamar).
    `queries._summary_counts` se busca en el módulo al llamar (las pruebas lo reemplazan)."""
    vivos = sorted(await members_service.active_ids(session))
    totales = dict.fromkeys(queries.SUMMARY_FIELDS, 0)
    for lote in chunked(vivos, SUMMARY_ID_BATCH):
        conteos = await queries._summary_counts(session, lote, today, expiring_days)
        for campo, cuantos in conteos.items():
            totales[campo] += cuantos
    return MembershipSummaryOut(**totales)


async def summary(session: AsyncSession, *, today: date | None = None) -> MembershipSummaryOut:
    """US-092: socios no dados de baja por estado resuelto (docstring del módulo). Una sesión con
    cambios sin confirmar que mueven el resumen (la marca `SUMMARY_DIRTY_KEY`) lo calcula sin
    leer ni escribir la caché: ve lo suyo y nunca deja en la caché algo que puede revertirse
    (MEDIUM-1 de la revisión de B7)."""
    hoy, dias = await queries._today_and_expiring_days(session, today)
    if session.info.get(SUMMARY_DIRTY_KEY) or _summary_cache.ttl_s <= 0:
        return await _summary_compute(session, hoy, dias)
    clave: SummaryKey = (hoy, dias)
    guardado = _summary_cache_get(clave)
    if guardado is not None:
        return guardado
    async with _summary_flight_lock():
        guardado = _summary_cache_get(clave)
        if guardado is not None:
            return guardado
        generacion = _summary_cache.generation
        resultado = await _summary_compute(session, hoy, dias)
        _summary_cache_put(clave, resultado, generacion)
    return resultado

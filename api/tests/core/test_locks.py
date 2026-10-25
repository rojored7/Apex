"""`core.locks.lock_member` (S3-B1; S3-D54, D3, L-1, S3-D43, S3-D67).

Con `dos_sesiones` (dos conexiones con commit real):
- mientras una sesión tiene el candado de un socio, la otra espera y lo obtiene en cuanto la
  primera termina su transacción (es un candado de transacción: no hay que soltarlo a mano);
- con `SET LOCAL lock_timeout = '200ms'` la segunda recibe `DatabaseBusy` (503 `busy`), con el
  55P03 encadenado en `__cause__`;
- la llave es `hashtextextended(<uuid>, 0)` calculada por PostgreSQL: la misma para el mismo UUID
  (el candado aparece en `pg_locks` con esa llave) y distinta para otro (otro socio no espera).
Cada prueba revierte las dos sesiones en `finally`: ningún candado queda vivo.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import DatabaseBusy, sqlstate_of
from app.core.locks import MEMBER_LOCK_NAMESPACE, MEMBER_LOCK_SQL, lock_member

ESPERA_CORTA = "SET LOCAL lock_timeout = '200ms'"
LLAVE_ESPERADA = text("SELECT hashtextextended(:m, 0)")
CANDADOS_ASESORES = text(
    "SELECT (classid::bigint << 32) | objid::bigint AS llave FROM pg_locks "
    "WHERE locktype = 'advisory' AND pid = pg_backend_pid() AND granted"
)


async def _soltar(*sesiones: AsyncSession) -> None:
    for sesion in sesiones:
        await sesion.rollback()


def test_la_sentencia_usa_hashtextextended_con_la_semilla_cero() -> None:
    # PL2 de la revisión de Fase 4 del Sprint 3: la semilla viaja como parámetro (`:ns`).
    assert MEMBER_LOCK_SQL == "SELECT pg_advisory_xact_lock(hashtextextended(:m, :ns))"
    assert MEMBER_LOCK_NAMESPACE == 0


async def test_la_segunda_sesion_espera_hasta_que_la_primera_termina(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    primera, segunda = dos_sesiones
    socio = uuid4()
    try:
        await lock_member(primera, socio)
        espera = asyncio.create_task(lock_member(segunda, socio))
        await asyncio.sleep(0.3)
        assert not espera.done(), "la segunda sesión debía esperar el candado"
        await primera.commit()  # termina la transacción: el candado se libera solo
        await asyncio.wait_for(espera, timeout=5)
    finally:
        await _soltar(primera, segunda)


async def test_con_lock_timeout_corto_la_segunda_recibe_database_busy(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    primera, segunda = dos_sesiones
    socio = uuid4()
    try:
        await lock_member(primera, socio)
        await segunda.execute(text(ESPERA_CORTA))
        with pytest.raises(DatabaseBusy) as error:
            await lock_member(segunda, socio)
        assert (error.value.status, error.value.code) == (503, "busy")
        assert error.value.headers["Retry-After"] == "1"
        causa = error.value.__cause__
        assert isinstance(causa, DBAPIError) and sqlstate_of(causa) == "55P03"
    finally:
        await _soltar(primera, segunda)


async def test_otro_socio_no_espera(dos_sesiones: tuple[AsyncSession, AsyncSession]) -> None:
    primera, segunda = dos_sesiones
    try:
        await lock_member(primera, uuid4())
        await segunda.execute(text(ESPERA_CORTA))
        await lock_member(segunda, uuid4())  # otra llave: no espera ni da 55P03
    finally:
        await _soltar(primera, segunda)


async def test_la_llave_es_hashtextextended_del_uuid(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    primera, segunda = dos_sesiones
    socio = UUID("5a0c1e2d-3f4b-4c5d-8e6f-708192a3b4c5")
    try:
        await lock_member(primera, socio)
        esperada = await primera.scalar(LLAVE_ESPERADA, {"m": str(socio)})
        otra = await primera.scalar(LLAVE_ESPERADA, {"m": str(uuid4())})
        tomadas = set((await primera.execute(CANDADOS_ASESORES)).scalars())
        assert esperada in tomadas
        assert otra not in tomadas and otra != esperada
    finally:
        await _soltar(primera, segunda)


async def test_el_candado_se_libera_al_revertir(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
) -> None:
    primera, segunda = dos_sesiones
    socio = uuid4()
    try:
        await lock_member(primera, socio)
        await primera.rollback()
        await segunda.execute(text(ESPERA_CORTA))
        await lock_member(segunda, socio)
        assert len(set((await segunda.execute(CANDADOS_ASESORES)).scalars())) == 1
    finally:
        await _soltar(primera, segunda)

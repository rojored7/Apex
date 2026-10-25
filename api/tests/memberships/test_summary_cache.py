"""Caché del resumen de membresías (S3-B7; M-10, S3-D53, S3-D60, E11, E13).

La fixture autouse `sin_cache_de_resumen` apaga la caché en `tests/memberships`; cada prueba de
este archivo la vuelve a encender con `configure_summary_cache(SUMMARY_CACHE_TTL_S)` (30 s) y
mide con `contador_de_consultas` las sentencias a `memberships.memberships` (una lectura servida
por la caché no envía ninguna). Reloj congelado en `T0` = 2026-10-21T15:00:00Z.

- Dos llamadas seguidas: una sola consulta. A los 29 s sigue sirviendo; a los 31 s vuelve a
  consultar (el TTL se mide con el reloj de la app).
- La clave es `(hoy, expiring_days)`: cambiar `expiring_days` en settings consulta de nuevo (y
  el resultado cambia); volver al valor anterior sirve la entrada que ya estaba.
- `reset_summary_cache()` la vacía.
- Los handlers `_mark_summary_dirty` solo marcan `session.info["apex.summary_dirty"]`; están
  suscritos a los siete eventos que cambian el resumen.
- Invalidación tras el commit real (E11, E13), con `dos_sesiones` (commit real; la caché es del
  proceso y la comparten las dos): con la caché cebada por la segunda sesión, un `sell` en la
  primera (con su `begin_nested()`: flush y liberación del SAVEPOINT) NO la invalida y la
  segunda sigue sirviendo; tras `commit()` de la primera la segunda vuelve a consultar y ve la
  venta. Lo mismo con `PaymentRegistered` (registrar el pago que activa). Un `rollback` tras
  marcar no invalida y descarta la marca (un commit posterior sin cambios tampoco invalida). El
  rollback de un SAVEPOINT dentro de una transacción ya marcada no pierde la marca: el commit
  invalida igual (nunca se conservan datos viejos tras confirmar, S3-D53).
- Revisión de seguridad del Verde: una sesión marcada calcula sin leer ni escribir la caché
  (MEDIUM-1); un vaciado durante el cálculo descarta lo calculado y dos resúmenes a la vez con
  la caché vacía calculan una sola vez (MEDIUM-2); el resumen es inmutable (LOW-2) y la caché no
  pasa de `SUMMARY_CACHE_MAX_ENTRIES` (LOW-3).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import events
from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring
from app.modules.memberships import queries, service
from app.modules.memberships.queries import (
    SUMMARY_CACHE_TTL_S,
    SUMMARY_DIRTY_KEY,
    configure_summary_cache,
    reset_summary_cache,
)
from app.modules.memberships.schemas import MembershipSummaryOut
from app.modules.payments import service as payments_service
from tests.conftest import T0, ContadorDeConsultas
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.memberships._apoyo import TABLA_MEMBRESIAS, guardar_politica, vender

EVENTOS_QUE_CAMBIAN_EL_RESUMEN = (
    service.MembershipSold,
    service.MembershipActivated,
    service.MembershipActivationReverted,
    service.MembershipFrozen,
    service.MembershipCancelled,
    payments_service.PaymentRegistered,
    payments_service.PaymentVoided,
)


@pytest.fixture
def con_cache() -> Iterator[None]:
    """La caché con el TTL de producción (30 s) en esta prueba; `sin_cache_de_resumen` la
    vuelve a apagar al salir."""
    configure_summary_cache(SUMMARY_CACHE_TTL_S)
    yield


async def _socio(session: AsyncSession, nombre: str) -> Any:
    return await make_member(
        session,
        first_name=nombre,
        last_name="Cache",
        document=unique_document(),
        phone=None,
        email=None,
    )


async def _consultas_del_resumen(
    session: AsyncSession, contador: ContadorDeConsultas
) -> tuple[MembershipSummaryOut, int]:
    """El resumen y cuántas sentencias envió a `memberships.memberships`."""
    with contador.midiendo():
        resumen = await service.summary(session)
    return resumen, contador.de(TABLA_MEMBRESIAS)


# Con la sesión de la prueba -----------------------------------------------------------------------


@pytest.fixture
async def una_vigente(session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock) -> UUID:
    """Un socio con una `active` que termina el 2026-10-26 (faltan 5 días: `expiring` con
    `expiring_days` 7 y `active` con 3)."""
    plan = await make_plan(session)
    socio = await _socio(session, "Vigente")
    membresia = await make_membership(
        session, socio, plan, status="active", start=date(2026, 9, 26), end=date(2026, 10, 26)
    )
    return membresia.id


async def test_dos_llamadas_seguidas_dan_una_sola_consulta(
    session: AsyncSession,
    una_vigente: UUID,
    con_cache: None,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    primero, consultas = await _consultas_del_resumen(session, contador_de_consultas)
    assert consultas >= 1
    assert primero.expiring == 1
    segundo, consultas = await _consultas_del_resumen(session, contador_de_consultas)
    assert (segundo, consultas) == (primero, 0)


async def test_el_ttl_de_30_s_se_mide_con_el_reloj_de_la_app(
    session: AsyncSession,
    una_vigente: UUID,
    con_cache: None,
    reloj: FrozenClock,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    await service.summary(session)
    reloj.set(T0 + timedelta(seconds=29))
    assert (await _consultas_del_resumen(session, contador_de_consultas))[1] == 0
    reloj.set(T0 + timedelta(seconds=31))
    assert (await _consultas_del_resumen(session, contador_de_consultas))[1] >= 1


async def test_la_clave_cambia_con_expiring_days(
    session: AsyncSession,
    una_vigente: UUID,
    con_cache: None,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    con_7, _ = await _consultas_del_resumen(session, contador_de_consultas)
    assert (con_7.expiring, con_7.active) == (1, 0)
    await guardar_politica(session, expiring_days=3)
    con_3, consultas = await _consultas_del_resumen(session, contador_de_consultas)
    assert consultas >= 1
    assert (con_3.expiring, con_3.active) == (0, 1)
    await guardar_politica(session, version=1, expiring_days=7)
    otra_vez_7, consultas = await _consultas_del_resumen(session, contador_de_consultas)
    assert (otra_vez_7, consultas) == (con_7, 0)


async def test_reset_summary_cache_vacia_la_cache(
    session: AsyncSession,
    una_vigente: UUID,
    con_cache: None,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    await service.summary(session)
    reset_summary_cache()
    assert (await _consultas_del_resumen(session, contador_de_consultas))[1] >= 1


async def test_con_ttl_0_nunca_sirve_de_la_cache(
    session: AsyncSession, una_vigente: UUID, contador_de_consultas: ContadorDeConsultas
) -> None:
    """Lo que hace la fixture autouse `sin_cache_de_resumen` en el resto de `tests/memberships`."""
    await service.summary(session)
    assert (await _consultas_del_resumen(session, contador_de_consultas))[1] >= 1


async def test_vender_y_confirmar_invalida_la_cache(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    con_cache: None,
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    """Con la sesión de la prueba, `commit()` confirma la transacción de la `Session` (libera el
    savepoint externo de la fixture): para la sesión es el commit real."""
    plan = await make_plan(session)
    socio = await _socio(session, "Venta")
    antes, _ = await _consultas_del_resumen(session, contador_de_consultas)
    assert antes.pending_payment == 0
    await vender(session, SYSTEM_USER_ID, member_id=socio.id, plan_id=plan.id)
    despues, consultas = await _consultas_del_resumen(session, contador_de_consultas)
    assert consultas >= 1
    assert despues.pending_payment == 1


# Los handlers solo marcan la sesión ---------------------------------------------------------------


async def test_el_handler_solo_marca_la_sesion(session: AsyncSession) -> None:
    session.info.pop(SUMMARY_DIRTY_KEY, None)
    evento = service.MembershipCancelled(
        membership_id=SYSTEM_USER_ID, member_id=SYSTEM_USER_ID, reason_len=16
    )
    await queries._mark_summary_dirty(evento, session)
    assert session.info[SUMMARY_DIRTY_KEY] is True
    assert SUMMARY_DIRTY_KEY == "apex.summary_dirty"
    session.info.pop(SUMMARY_DIRTY_KEY, None)


@pytest.mark.parametrize("evento", EVENTOS_QUE_CAMBIAN_EL_RESUMEN, ids=lambda e: e.__name__)
def test_el_handler_esta_suscrito_a_los_siete_eventos(evento: type[events.DomainEvent]) -> None:
    suscritos = events.subscribers_for(evento)
    assert sum(1 for h in suscritos if h is queries._mark_summary_dirty) == 1


# Commit real con dos sesiones (E11, E13) ----------------------------------------------------------


@pytest.fixture
async def dos_con_cache(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    bus_confirmado: Keyring,
    reloj: FrozenClock,
    con_cache: None,
) -> AsyncIterator[tuple[AsyncSession, AsyncSession, UUID, UUID]]:
    """Un plan y un socio confirmados en la primera sesión; devuelve las dos sesiones, el plan y
    el socio."""
    primera, segunda = dos_sesiones
    plan = await make_plan(primera, name="Mensual caché")
    socio = await _socio(primera, "Real")
    yield primera, segunda, plan.id, socio.id


async def _resumen_de_la_segunda(
    segunda: AsyncSession, contador: ContadorDeConsultas
) -> tuple[MembershipSummaryOut, int]:
    """El resumen leído por la segunda sesión, en su propia transacción (como una petición)."""
    resultado = await _consultas_del_resumen(segunda, contador)
    await segunda.commit()
    return resultado


async def _vender_sin_confirmar(primera: AsyncSession, plan: UUID, socio: UUID) -> None:
    with actor_scope(SYSTEM_USER_ID):
        await service.sell(primera, member_id=socio, plan_id=plan)


async def test_un_sell_con_savepoint_no_invalida_hasta_el_commit_real(
    dos_con_cache: tuple[AsyncSession, AsyncSession, UUID, UUID],
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    primera, segunda, plan, socio = dos_con_cache
    cebado, consultas = await _resumen_de_la_segunda(segunda, contador_de_consultas)
    assert consultas >= 1 and cebado.pending_payment == 0
    await _vender_sin_confirmar(primera, plan, socio)  # flush y RELEASE SAVEPOINT de `sell`
    assert primera.info.get(SUMMARY_DIRTY_KEY) is True
    servido, consultas = await _resumen_de_la_segunda(segunda, contador_de_consultas)
    assert (servido, consultas) == (cebado, 0)
    await primera.commit()
    nuevo, consultas = await _resumen_de_la_segunda(segunda, contador_de_consultas)
    assert consultas >= 1
    assert nuevo.pending_payment == 1
    assert not primera.info.get(SUMMARY_DIRTY_KEY)


async def test_registrar_el_pago_que_activa_invalida_solo_tras_el_commit(
    dos_con_cache: tuple[AsyncSession, AsyncSession, UUID, UUID],
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    primera, segunda, plan, socio = dos_con_cache
    await _vender_sin_confirmar(primera, plan, socio)
    await primera.commit()
    membresia = await primera.scalar(
        text("SELECT id FROM memberships.memberships WHERE member_id = :m"), {"m": socio}
    )
    await primera.commit()
    cebado, _ = await _resumen_de_la_segunda(segunda, contador_de_consultas)
    assert (cebado.pending_payment, cebado.active) == (1, 0)
    with actor_scope(SYSTEM_USER_ID):
        await payments_service.register(
            primera, membership_id=membresia, amount_cop=120_000, method="cash", role="admin"
        )
    servido, consultas = await _resumen_de_la_segunda(segunda, contador_de_consultas)
    assert (servido, consultas) == (cebado, 0)
    await primera.commit()
    nuevo, consultas = await _resumen_de_la_segunda(segunda, contador_de_consultas)
    assert consultas >= 1
    assert (nuevo.pending_payment, nuevo.active) == (0, 1)


async def test_un_rollback_tras_marcar_no_invalida_y_descarta_la_marca(
    dos_con_cache: tuple[AsyncSession, AsyncSession, UUID, UUID],
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    primera, segunda, plan, socio = dos_con_cache
    cebado, _ = await _resumen_de_la_segunda(segunda, contador_de_consultas)
    await _vender_sin_confirmar(primera, plan, socio)
    await primera.rollback()
    assert not primera.info.get(SUMMARY_DIRTY_KEY)
    servido, consultas = await _resumen_de_la_segunda(segunda, contador_de_consultas)
    assert (servido, consultas) == (cebado, 0)
    await primera.execute(text("SELECT 1"))
    await primera.commit()  # una transacción sin cambios: la marca ya no existe
    servido, consultas = await _resumen_de_la_segunda(segunda, contador_de_consultas)
    assert (servido, consultas) == (cebado, 0)


class _Abortar(Exception):
    """Fuerza el rollback de un SAVEPOINT en la prueba."""


async def test_el_rollback_de_un_savepoint_no_pierde_la_marca_de_la_transaccion(
    dos_con_cache: tuple[AsyncSession, AsyncSession, UUID, UUID],
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    primera, segunda, plan, socio = dos_con_cache
    cebado, _ = await _resumen_de_la_segunda(segunda, contador_de_consultas)
    await _vender_sin_confirmar(primera, plan, socio)
    with pytest.raises(_Abortar):
        async with primera.begin_nested():
            await primera.execute(text("SELECT 1"))
            raise _Abortar
    await primera.commit()
    nuevo, consultas = await _resumen_de_la_segunda(segunda, contador_de_consultas)
    assert consultas >= 1
    assert nuevo.pending_payment == cebado.pending_payment + 1


# Revisión de seguridad del Verde de B7 (MEDIUM-1, MEDIUM-2, LOW-2, LOW-3) ------------------------


async def test_una_sesion_con_cambios_sin_confirmar_no_escribe_la_cache(
    dos_con_cache: tuple[AsyncSession, AsyncSession, UUID, UUID],
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    """MEDIUM-1: la sesión marcada ve su venta sin confirmar, pero ese resultado no llega a la
    caché; tras su rollback, nadie ve una venta que nunca existió."""
    primera, segunda, plan, socio = dos_con_cache
    await _vender_sin_confirmar(primera, plan, socio)
    propio, consultas = await _consultas_del_resumen(primera, contador_de_consultas)
    assert consultas >= 1 and propio.pending_payment == 1
    ajeno, consultas = await _resumen_de_la_segunda(segunda, contador_de_consultas)
    assert consultas >= 1 and ajeno.pending_payment == 0
    await primera.rollback()
    servido, consultas = await _resumen_de_la_segunda(segunda, contador_de_consultas)
    assert (servido, consultas) == (ajeno, 0)


async def test_un_vaciado_durante_el_calculo_descarta_el_resultado(
    session: AsyncSession,
    una_vigente: UUID,
    con_cache: None,
    contador_de_consultas: ContadorDeConsultas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MEDIUM-2: si un commit vacía la caché mientras otra petición calcula, lo calculado (que
    puede ser anterior a ese commit) no se guarda."""
    original = queries._summary_counts

    async def con_commit_en_medio(*args: Any, **kwargs: Any) -> dict[str, int]:
        reset_summary_cache()  # lo que hace `after_commit` de otra sesión
        return await original(*args, **kwargs)

    monkeypatch.setattr(queries, "_summary_counts", con_commit_en_medio)
    await service.summary(session)
    monkeypatch.setattr(queries, "_summary_counts", original)
    assert (await _consultas_del_resumen(session, contador_de_consultas))[1] >= 1
    assert (await _consultas_del_resumen(session, contador_de_consultas))[1] == 0


async def test_dos_resumenes_a_la_vez_con_la_cache_vacia_calculan_una_sola_vez(
    dos_con_cache: tuple[AsyncSession, AsyncSession, UUID, UUID],
    contador_de_consultas: ContadorDeConsultas,
) -> None:
    """MEDIUM-2: un solo cálculo a la vez; el segundo lee lo que dejó el primero."""
    primera, segunda, _, _ = dos_con_cache
    with contador_de_consultas.midiendo():
        uno, dos = await asyncio.gather(service.summary(primera), service.summary(segunda))
    assert uno == dos
    assert contador_de_consultas.de(TABLA_MEMBRESIAS) == 1
    await primera.commit()
    await segunda.commit()


def test_el_resumen_es_inmutable() -> None:
    """LOW-2: la caché entrega la misma instancia a todos; nadie puede cambiarla."""
    resumen = MembershipSummaryOut(active=1, expiring=0, expired=0, frozen=0, pending_payment=0)
    with pytest.raises(ValidationError):
        resumen.active = 99  # type: ignore[misc]


def test_la_cache_no_pasa_de_su_tope_de_entradas(reloj: FrozenClock) -> None:
    """LOW-3: como mucho `SUMMARY_CACHE_MAX_ENTRIES` entradas; sale la más vieja."""
    cache = queries.SummaryCache(SUMMARY_CACHE_TTL_S)
    cero = MembershipSummaryOut(active=0, expiring=0, expired=0, frozen=0, pending_payment=0)
    for dia in range(100):
        reloj.set(T0 + timedelta(microseconds=dia))
        cache.put((date(2026, 1, 1) + timedelta(days=dia), 7), cero)
    assert len(cache) == queries.SUMMARY_CACHE_MAX_ENTRIES
    assert cache.get((date(2026, 1, 1), 7)) is None
    assert cache.get((date(2026, 1, 1) + timedelta(days=99), 7)) == cero

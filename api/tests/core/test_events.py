"""Bus de eventos sin base (US-014, T6)."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock, reset_clock, set_clock
from app.core.events import (
    MAX_EVENT_DEPTH,
    DomainEvent,
    EventDepthExceeded,
    clear_subscribers,
    emit,
    subscribe,
    subscribers_for,
)


@dataclass(frozen=True, slots=True)
class PagoRegistrado(DomainEvent):
    membership_id: str
    amount_cop: int


@dataclass(frozen=True, slots=True)
class OtroEvento(DomainEvent):
    valor: int = 0


class SesionFalsa:
    pass


SESION = cast(AsyncSession, SesionFalsa())


@pytest.fixture(autouse=True)
def _limpio() -> None:
    clear_subscribers()


async def test_dos_suscriptores_reciben_la_misma_sesion_en_orden() -> None:
    llamadas: list[tuple[str, object]] = []

    async def primero(evento: PagoRegistrado, session: AsyncSession) -> None:
        llamadas.append(("primero", session))

    async def segundo(evento: PagoRegistrado, session: AsyncSession) -> None:
        llamadas.append(("segundo", session))

    subscribe(PagoRegistrado, primero)
    subscribe(PagoRegistrado, segundo)
    await emit(PagoRegistrado(membership_id="m1", amount_cop=120_000), SESION)

    assert [n for n, _ in llamadas] == ["primero", "segundo"]
    assert all(s is SESION for _, s in llamadas)


def test_el_evento_es_inmutable() -> None:
    evento = PagoRegistrado(membership_id="m1", amount_cop=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        evento.amount_cop = 2  # type: ignore[misc]


async def test_emitir_sin_suscriptores_no_falla() -> None:
    await emit(OtroEvento(), SESION)


async def test_despacho_por_tipo_exacto() -> None:
    recibidos: list[str] = []

    async def handler(evento: OtroEvento, session: AsyncSession) -> None:
        recibidos.append(type(evento).__name__)

    subscribe(OtroEvento, handler)
    await emit(PagoRegistrado(membership_id="m", amount_cop=1), SESION)
    assert recibidos == []
    await emit(OtroEvento(), SESION)
    assert recibidos == ["OtroEvento"]


async def test_cadena_de_eventos_corta_en_profundidad_maxima() -> None:
    veces = 0

    async def reemite(evento: OtroEvento, session: AsyncSession) -> None:
        nonlocal veces
        veces += 1
        await emit(OtroEvento(valor=evento.valor + 1), session)

    subscribe(OtroEvento, reemite)
    with pytest.raises(EventDepthExceeded):
        await emit(OtroEvento(), SESION)
    assert veces == MAX_EVENT_DEPTH == 5


async def test_una_excepcion_del_handler_se_propaga_al_emisor() -> None:
    async def falla(evento: OtroEvento, session: AsyncSession) -> None:
        raise ValueError("el handler falló")

    subscribe(OtroEvento, falla)
    with pytest.raises(ValueError, match="el handler falló"):
        await emit(OtroEvento(), SESION)


def test_subscribe_es_idempotente() -> None:
    async def handler(evento: OtroEvento, session: AsyncSession) -> None:
        pass

    subscribe(OtroEvento, handler)
    subscribe(OtroEvento, handler)
    assert subscribers_for(OtroEvento) == (handler,)
    assert subscribers_for(PagoRegistrado) == ()


def test_occurred_at_sale_del_reloj_actual() -> None:
    instante = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
    token = set_clock(FrozenClock(instante))
    try:
        evento = PagoRegistrado(membership_id="m", amount_cop=1)
    finally:
        reset_clock(token)
    assert evento.occurred_at == instante
    assert evento.occurred_at.tzinfo is not None

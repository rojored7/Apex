"""Reglas de los filtros de la lista de pagos (S3-B8, US-098; D26, M-4, M-8, L-2, S3-D47,
S3-D51, S3-D57).

Puras:
- `PaymentFilters` (dataclass congelada; todo `None` por defecto) y `build_filters(filters,
  member_ids_from_q)`: sin filtros no hay condiciones. Su semántica se fija ejecutando las
  condiciones contra cuatro pagos reales (`cuatro_pagos`), un filtro por vez: el rango es
  `[from, to)` (incluye `from`, excluye `to`); `voided` y `backdated` son tri-estado (`None` no
  filtra); `q` es `lower(reference) = lower(q)` o `member_id` en los ids de la búsqueda de socios;
  sin `q` los ids no filtran.
- `check_date_range(from_, to, today)` (M-4, S3-D47): `from` y `to` entre `DATE_FLOOR`
  (2020-01-01T00:00Z, el mismo piso de `paid_at`) y `date_ceiling(today)` (hoy más 5 años);
  invertidas fallan en `to`. Error `InvalidDateRange` (422 `validation_error`) con el `field`
  que falla (`from` o `to`); años 1 y 9999 dan 422, nunca `OverflowError`.
- `partial_email` (L-2, S3-D57): primera letra, `•••` y `@dominio` completo (la última `@`).
- `is_backdated(paid_at, created_at)` (M-8, S3-D51): `created_at - paid_at` mayor que 24 h.
- `PaymentListQuery`: alias `from`, fechas con zona, `method` del `Literal`, `q` hasta 100
  caracteres, `extra="forbid"`.

"Hoy" es 2026-10-21. Los cuatro pagos (montos y horas a mano):
- p1: membresía M1 (socio A), efectivo 10.000, 2026-10-05T15:00Z, registró U1, referencia
  `NEQ-100`, registrado 1 h después;
- p2: M1, Nequi 20.000, 2026-10-10T15:00Z, U2, anulado, registrado 1 h después;
- p3: M2 (socio B), Bre-B 30.000, 2026-10-15T15:00Z, U1, registrado 25 h después (`backdated`);
- p4: M2, efectivo 40.000, 2026-10-20T15:00Z, U2, registrado 23 h después (no `backdated`).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from app.modules.payments import rules
from app.modules.payments.exceptions import InvalidDateRange
from app.modules.payments.models import Payment
from app.modules.payments.schemas import PaymentListQuery
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan

HOY = date(2026, 10, 21)
U1 = UUID("0000000b-0000-4000-8000-0000000b8001")
U2 = UUID("0000000b-0000-4000-8000-0000000b8002")


def _utc(dia: int, hora: int = 15) -> datetime:
    return datetime(2026, 10, dia, hora, 0, tzinfo=UTC)


# Puras: estructura -------------------------------------------------------------------------------


def test_payment_filters_es_congelada_y_vacia_por_defecto() -> None:
    filtros = rules.PaymentFilters()
    assert dataclasses.is_dataclass(filtros)
    assert all(getattr(filtros, campo.name) is None for campo in dataclasses.fields(filtros))
    assert {campo.name for campo in dataclasses.fields(filtros)} == {
        "q",
        "from_",
        "to",
        "method",
        "registered_by",
        "voided",
        "backdated",
        "member_id",
        "membership_id",
    }
    with pytest.raises(dataclasses.FrozenInstanceError):
        filtros.q = "x"  # type: ignore[misc]


def test_sin_filtros_no_hay_condiciones() -> None:
    assert rules.build_filters(rules.PaymentFilters(), ()) == []


# Semántica de `build_filters` sobre pagos reales -------------------------------------------------


@dataclass(frozen=True)
class CuatroPagos:
    ids: dict[str, UUID]
    socio_a: UUID
    socio_b: UUID
    m1: UUID
    m2: UUID

    def nombres(self, encontrados: Collection[UUID]) -> set[str]:
        por_id = {v: k for k, v in self.ids.items()}
        return {por_id[i] for i in encontrados if i in por_id}


@pytest.fixture
async def cuatro_pagos(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> CuatroPagos:
    plan = await make_plan(session)
    socio_a = await make_member(session)
    socio_b = await make_member(
        session,
        first_name="Pedro",
        last_name="Ruiz",
        document=unique_document(),
        phone=None,
        email=None,
    )
    m1 = await make_membership(session, socio_a, plan, status="active")
    m2 = await make_membership(session, socio_b, plan, status="active")
    datos: dict[str, tuple[Any, str, int, datetime, UUID, timedelta, dict[str, Any]]] = {
        "p1": (m1, "cash", 10_000, _utc(5), U1, timedelta(hours=1), {"reference": "NEQ-100"}),
        "p2": (m1, "nequi", 20_000, _utc(10), U2, timedelta(hours=1), {"voided": True}),
        "p3": (m2, "breb", 30_000, _utc(15), U1, timedelta(hours=25), {}),
        "p4": (m2, "cash", 40_000, _utc(20), U2, timedelta(hours=23), {}),
    }
    ids: dict[str, UUID] = {}
    for nombre, (membresia, medio, monto, pagado, quien, demora, extra) in datos.items():
        pago = await make_payment(
            session,
            membresia,
            amount=monto,
            method=medio,
            paid_at=pagado,
            registered_by=quien,
            created_at=pagado + demora,
            **extra,
        )
        ids[nombre] = pago.id
    return CuatroPagos(ids=ids, socio_a=socio_a.id, socio_b=socio_b.id, m1=m1.id, m2=m2.id)


async def _con(
    session: AsyncSession, datos: CuatroPagos, ids_de_q: Collection[UUID] = (), **filtros: Any
) -> set[str]:
    condiciones = rules.build_filters(rules.PaymentFilters(**filtros), ids_de_q)
    encontrados = (await session.scalars(select(Payment.id).where(*condiciones))).all()
    return datos.nombres(encontrados)


TODOS = {"p1", "p2", "p3", "p4"}


@pytest.mark.parametrize(
    ("filtros", "esperados"),
    [
        ({}, TODOS),
        ({"method": "cash"}, {"p1", "p4"}),
        ({"method": "breb"}, {"p3"}),
        ({"registered_by": U1}, {"p1", "p3"}),
        ({"voided": True}, {"p2"}),
        ({"voided": False}, {"p1", "p3", "p4"}),
        ({"voided": None}, TODOS),
        ({"backdated": True}, {"p3"}),
        ({"backdated": False}, {"p1", "p2", "p4"}),
        ({"backdated": None}, TODOS),
        ({"method": "cash", "voided": False, "backdated": False}, {"p1", "p4"}),
    ],
    ids=[
        "sin-filtro",
        "efectivo",
        "breb",
        "registro-u1",
        "anulados",
        "vigentes",
        "voided-ausente",
        "backdated",
        "no-backdated",
        "backdated-ausente",
        "combinados",
    ],
)
async def test_cada_filtro_aislado(
    session: AsyncSession,
    cuatro_pagos: CuatroPagos,
    filtros: dict[str, Any],
    esperados: set[str],
) -> None:
    assert await _con(session, cuatro_pagos, **filtros) == esperados


async def test_filtro_por_socio_y_por_membresia(
    session: AsyncSession, cuatro_pagos: CuatroPagos
) -> None:
    assert await _con(session, cuatro_pagos, member_id=cuatro_pagos.socio_b) == {"p3", "p4"}
    assert await _con(session, cuatro_pagos, membership_id=cuatro_pagos.m1) == {"p1", "p2"}
    combinado = await _con(session, cuatro_pagos, member_id=cuatro_pagos.socio_b, method="cash")
    assert combinado == {"p4"}


async def test_el_rango_incluye_from_y_excluye_to(
    session: AsyncSession, cuatro_pagos: CuatroPagos
) -> None:
    assert await _con(session, cuatro_pagos, from_=_utc(10), to=_utc(20)) == {"p2", "p3"}
    assert await _con(session, cuatro_pagos, from_=_utc(10)) == {"p2", "p3", "p4"}
    assert await _con(session, cuatro_pagos, to=_utc(10)) == {"p1"}
    assert await _con(session, cuatro_pagos, from_=_utc(10), to=_utc(10)) == set()


async def test_q_compara_la_referencia_completa_sin_mayusculas(
    session: AsyncSession, cuatro_pagos: CuatroPagos
) -> None:
    assert await _con(session, cuatro_pagos, q="neq-100") == {"p1"}
    assert await _con(session, cuatro_pagos, q="NEQ-100") == {"p1"}
    assert await _con(session, cuatro_pagos, q="neq-1") == set()  # no es parcial


async def test_q_sin_coincidencias_de_socio_ni_de_referencia_no_da_nada(
    session: AsyncSession, cuatro_pagos: CuatroPagos
) -> None:
    assert await _con(session, cuatro_pagos, q="Zzyzx") == set()


async def test_q_usa_los_ids_de_la_busqueda_de_socios(
    session: AsyncSession, cuatro_pagos: CuatroPagos
) -> None:
    assert await _con(session, cuatro_pagos, {cuatro_pagos.socio_b}, q="ruiz") == {"p3", "p4"}
    combinado = await _con(session, cuatro_pagos, {cuatro_pagos.socio_b}, q="ruiz", voided=False)
    assert combinado == {"p3", "p4"}


async def test_sin_q_los_ids_de_busqueda_no_filtran(
    session: AsyncSession, cuatro_pagos: CuatroPagos
) -> None:
    assert await _con(session, cuatro_pagos, {cuatro_pagos.socio_b}) == TODOS


# Rango de fechas (M-4, S3-D47) ----------------------------------------------------------------


def test_el_piso_de_fechas_es_el_de_paid_at() -> None:
    assert datetime(2020, 1, 1, tzinfo=UTC) == rules.DATE_FLOOR
    assert rules.DATE_FLOOR == rules.PAID_AT_FLOOR


def test_el_techo_es_hoy_mas_cinco_anios() -> None:
    techo = rules.date_ceiling(HOY)
    assert techo.utcoffset() is not None
    assert datetime(2031, 10, 20, tzinfo=UTC) <= techo < datetime(2032, 10, 21, tzinfo=UTC)


def test_el_techo_de_un_29_de_febrero_no_falla() -> None:
    assert rules.date_ceiling(date(2028, 2, 29)).year == 2033


@pytest.mark.parametrize(
    ("desde", "hasta", "campo"),
    [
        (datetime(2019, 12, 31, tzinfo=UTC), None, "from"),
        (None, datetime(2019, 12, 31, tzinfo=UTC), "to"),
        (datetime(2032, 10, 21, tzinfo=UTC), None, "from"),
        (None, datetime(2032, 10, 21, tzinfo=UTC), "to"),
        (_utc(20), _utc(10), "to"),
        (datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=5))), None, "from"),
        (None, datetime(9999, 12, 31, 23, 59, tzinfo=UTC), "to"),
        (None, datetime(1, 1, 1, tzinfo=UTC), "to"),
    ],
    ids=[
        "desde-2019-12-31",
        "hasta-2019-12-31",
        "desde-hoy-mas-6-anios",
        "hasta-hoy-mas-6-anios",
        "invertidas",
        "desde-anio-1",
        "hasta-anio-9999",
        "hasta-anio-1",
    ],
)
def test_fechas_fuera_de_rango_dan_422_con_el_campo(
    desde: datetime | None, hasta: datetime | None, campo: str
) -> None:
    with pytest.raises(InvalidDateRange) as error:
        rules.check_date_range(desde, hasta, HOY)
    assert (error.value.status, error.value.code, error.value.field) == (
        422,
        "validation_error",
        campo,
    )
    assert "2019" not in error.value.message and "9999" not in error.value.message


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [
        (None, None),
        (datetime(2020, 1, 1, tzinfo=UTC), datetime(2031, 10, 20, tzinfo=UTC)),
        (_utc(10), _utc(10)),
        (datetime(2026, 10, 1, tzinfo=timezone(timedelta(hours=-5))), None),
    ],
    ids=["sin-fechas", "bordes", "mismo-instante", "con-desfase"],
)
def test_fechas_dentro_del_rango_pasan(desde: datetime | None, hasta: datetime | None) -> None:
    rules.check_date_range(desde, hasta, HOY)


# Correo parcial (L-2, S3-D57) ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("correo", "parcial"),
    [
        ("laura@box.co", "l•••@box.co"),
        ("a@box.co", "a•••@box.co"),
        ("ñandu@box.co", "ñ•••@box.co"),
        ("a@b@box.co", "a•••@box.co"),
        ("@box.co", "•••@box.co"),
        ("sinarroba", "s•••"),
        ("", "•••"),
    ],
    ids=["normal", "una-letra", "no-ascii", "dos-arrobas", "sin-local", "sin-arroba", "vacio"],
)
def test_partial_email(correo: str, parcial: str) -> None:
    assert rules.partial_email(correo) == parcial


def test_partial_email_no_deja_ver_la_parte_local() -> None:
    parcial = rules.partial_email("laura.perez@box.co")
    assert "aura" not in parcial and "perez" not in parcial
    assert parcial.endswith("@box.co")


# Pago retroactivo (M-8, S3-D51) --------------------------------------------------------------


@pytest.mark.parametrize(
    ("demora", "esperado"),
    [
        (timedelta(hours=23), False),
        (timedelta(hours=24), False),
        (timedelta(hours=24, seconds=1), True),
        (timedelta(hours=25), True),
        (timedelta(days=40), True),
        (timedelta(0), False),
        (timedelta(hours=-3), False),
    ],
    ids=["23h", "24h-exactas", "24h-y-1s", "25h", "40d", "mismo-instante", "pago-posterior"],
)
def test_is_backdated(demora: timedelta, esperado: bool) -> None:
    pagado = _utc(10)
    assert rules.is_backdated(pagado, pagado + demora) is esperado


# Esquema de entrada ----------------------------------------------------------------------------


def test_el_esquema_lee_from_por_su_alias() -> None:
    filtros = PaymentListQuery.model_validate(
        {"from": "2026-10-01T05:00:00Z", "to": "2026-11-01T05:00:00Z", "voided": False}
    )
    assert filtros.from_ == datetime(2026, 10, 1, 5, tzinfo=UTC)
    assert filtros.to == datetime(2026, 11, 1, 5, tzinfo=UTC)
    assert (filtros.voided, filtros.backdated, filtros.method, filtros.q) == (
        False,
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    ("datos", "campo"),
    [
        ({"from": "2026-10-01T05:00:00"}, "from"),
        ({"to": "no-es-fecha"}, "to"),
        ({"method": "tarjeta"}, "method"),
        ({"q": "a" * 101}, "q"),
        ({"member_id": "no-es-uuid"}, "member_id"),
        ({"membership_id": "no-es-uuid"}, "membership_id"),
        ({"registered_by": "no-es-uuid"}, "registered_by"),
        ({"estado": "x"}, "estado"),
    ],
    ids=[
        "from-sin-zona",
        "to-mal-formada",
        "medio-desconocido",
        "q-101",
        "socio-no-uuid",
        "membresia-no-uuid",
        "registro-no-uuid",
        "campo-desconocido",
    ],
)
def test_el_esquema_rechaza_entradas_invalidas(datos: dict[str, Any], campo: str) -> None:
    with pytest.raises(ValidationError) as error:
        PaymentListQuery.model_validate(datos)
    assert error.value.errors()[0]["loc"] == (campo,)

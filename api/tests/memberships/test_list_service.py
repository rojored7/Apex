"""`memberships.service.list` (S3-B7, US-091; D5, D18, M-4, L-9, S3-D47, S3-D59).

Hoy es 2026-10-21 (`reloj`), `expiring_days` 7 (política por defecto). Escenario (`escenario`),
un socio por membresía salvo que se diga, plan "Mensual" (30 días, 120.000) y "Trimestral" (90
días, 300.000); fechas y estados efectivos calculados a mano:
- Felipe Ortiz: `active` guardada del 2026-08-01 al 2026-08-31 → `expired` (D5, sin job);
- Lucía Gómez (documento `KNOWN`): `active` del 2026-09-25 al 2026-10-25 (faltan 4) →
  `expiring`; pagos 60.000 vigente y 30.000 anulado → `paid_cop` 60.000;
- Pedro Ruiz: `active` del 2026-09-27 al 2026-10-27 (faltan 6) → `expiring`;
- Carlos Díaz: `active` del 2026-09-28 al 2026-10-28 (faltan 7, el borde) → `expiring`;
- Diana Mora: `active` del 2026-09-29 al 2026-10-29 (faltan 8) → `active`;
- Hugo León: `active` del 2026-10-01 al 2026-11-15 con congelación del 20 al 23 de octubre →
  `frozen`;
- Eva Paz: `pending_payment` del 2026-10-21 al 2026-11-20 → `pending_payment`;
- Ana Ruiz (dada de baja): Trimestral `active` del 2026-10-01 al 2026-12-30 → `active`;
- Gina Vélez: `cancelled` del 2026-10-01 al 2026-10-31.

Sin `status` la lista excluye las anuladas; el orden es `end_date, id`: Felipe (08-31), Lucía
(10-25), Pedro (10-27), Carlos (10-28), Diana (10-29), Hugo (11-15), Eva (11-20), Ana (12-30).

Además: `q` por apellido y por documento (índice ciego, incluye dados de baja: S3-B7 D18), `q`
sin coincidencias, `total` con `offset`, cero `decrypt`, una sentencia por servicio vecino por
página (`contador_de_consultas`) y M-4 (`ends_*` entre 2020-01-01 y hoy más 5 años; invertidas
en `ends_to`); `status` de 101 caracteres no pasa el esquema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring
from app.core.pagination import Page, PageParams
from app.modules.memberships import service
from app.modules.memberships.exceptions import DateRangeInvalid, StatusFilterInvalid
from app.modules.memberships.schemas import MembershipListQuery, MembershipRow
from tests.conftest import T0, ContadorDeConsultas
from tests.factories.members import KNOWN, make_member, unique_document
from tests.factories.memberships import make_freeze, make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.memberships._apoyo import CAMPOS_ROW, TABLA_CONGELACIONES, TABLA_MEMBRESIAS

HOY = date(2026, 10, 21)
ORDEN_SIN_FILTRO = ["felipe", "lucia", "pedro", "carlos", "diana", "hugo", "eva", "ana"]


@dataclass(frozen=True)
class Escenario:
    membresias: dict[str, UUID]
    socios: dict[str, UUID]
    mensual: UUID
    trimestral: UUID

    def nombres(self, pagina: Page[MembershipRow]) -> list[str]:
        por_id = {v: k for k, v in self.membresias.items()}
        return [por_id[fila.id] for fila in pagina.items]


async def _socio(session: AsyncSession, nombre: str, apellido: str, **cambios: Any) -> Any:
    datos: dict[str, Any] = {
        "first_name": nombre,
        "last_name": apellido,
        "document": unique_document(),
        "phone": None,
        "email": None,
        **cambios,
    }
    return await make_member(session, **datos)


@pytest.fixture
async def escenario(session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock) -> Escenario:
    mensual = await make_plan(session, name="Mensual")
    trimestral = await make_plan(session, name="Trimestral", price_cop=300_000, duration_days=90)
    socios = {
        "felipe": await _socio(session, "Felipe", "Ortiz"),
        "lucia": await make_member(session),  # Lucía Gómez, documento KNOWN
        "pedro": await _socio(session, "Pedro", "Ruiz"),
        "carlos": await _socio(session, "Carlos", "Díaz"),
        "diana": await _socio(session, "Diana", "Mora"),
        "hugo": await _socio(session, "Hugo", "León"),
        "eva": await _socio(session, "Eva", "Paz"),
        "ana": await _socio(session, "Ana", "Ruiz", deleted_at=T0 - timedelta(days=1)),
        "gina": await _socio(session, "Gina", "Vélez"),
    }
    datos: dict[str, tuple[Any, str, date, date]] = {
        "felipe": (mensual, "active", date(2026, 8, 1), date(2026, 8, 31)),
        "lucia": (mensual, "active", date(2026, 9, 25), date(2026, 10, 25)),
        "pedro": (mensual, "active", date(2026, 9, 27), date(2026, 10, 27)),
        "carlos": (mensual, "active", date(2026, 9, 28), date(2026, 10, 28)),
        "diana": (mensual, "active", date(2026, 9, 29), date(2026, 10, 29)),
        "hugo": (mensual, "active", date(2026, 10, 1), date(2026, 11, 15)),
        "eva": (mensual, "pending_payment", date(2026, 10, 21), date(2026, 11, 20)),
        "ana": (trimestral, "active", date(2026, 10, 1), date(2026, 12, 30)),
        "gina": (mensual, "cancelled", date(2026, 10, 1), date(2026, 10, 31)),
    }
    membresias: dict[str, Any] = {}
    for nombre, (plan, estado, inicio, fin) in datos.items():
        membresias[nombre] = await make_membership(
            session, socios[nombre], plan, status=estado, start=inicio, end=fin
        )
    await make_freeze(session, membresias["hugo"], date(2026, 10, 20), date(2026, 10, 23))
    await make_payment(session, membresias["lucia"], amount=60_000)
    await make_payment(session, membresias["lucia"], amount=30_000, voided=True)
    return Escenario(
        membresias={n: m.id for n, m in membresias.items()},
        socios={n: s.id for n, s in socios.items()},
        mensual=mensual.id,
        trimestral=trimestral.id,
    )


async def listar(
    session: AsyncSession, *, limit: int = 25, offset: int = 0, **filtros: Any
) -> Page[MembershipRow]:
    with actor_scope(SYSTEM_USER_ID):
        return await service.list(
            session, MembershipListQuery(**filtros), PageParams(limit=limit, offset=offset)
        )


# Filtros y orden (D18) ----------------------------------------------------------------------------


async def test_sin_filtro_excluye_anuladas_y_ordena_por_fin(
    session: AsyncSession, escenario: Escenario
) -> None:
    pagina = await listar(session)
    assert escenario.nombres(pagina) == ORDEN_SIN_FILTRO
    assert pagina.total == 8
    assert (pagina.limit, pagina.offset) == (25, 0)


async def test_las_filas_traen_el_contrato_y_el_estado_efectivo(
    session: AsyncSession, escenario: Escenario
) -> None:
    pagina = await listar(session)
    estados = {n: f.status for n, f in zip(escenario.nombres(pagina), pagina.items, strict=True)}
    assert estados == {
        "felipe": "expired",
        "lucia": "expiring",
        "pedro": "expiring",
        "carlos": "expiring",
        "diana": "active",
        "hugo": "frozen",
        "eva": "pending_payment",
        "ana": "active",
    }
    lucia = pagina.items[1]
    assert set(lucia.model_dump()) == CAMPOS_ROW
    assert lucia.member_id == escenario.socios["lucia"]
    assert lucia.member_name == "Lucía Gómez"
    assert (lucia.plan_id, lucia.plan_name) == (escenario.mensual, "Mensual")
    assert (lucia.agreed_price_cop, lucia.paid_cop) == (120_000, 60_000)  # el anulado no suma
    assert (lucia.start_date, lucia.end_date) == (date(2026, 9, 25), date(2026, 10, 25))
    assert (lucia.classes_total, lucia.classes_remaining) == (None, None)
    assert pagina.items[0].paid_cop == 0  # Felipe, sin pagos


async def test_filtro_expiring_da_las_tres_por_vencer_en_orden_de_fin(
    session: AsyncSession, escenario: Escenario
) -> None:
    pagina = await listar(session, status="expiring")
    assert escenario.nombres(pagina) == ["lucia", "pedro", "carlos"]
    assert pagina.total == 3
    assert {f.status for f in pagina.items} == {"expiring"}


async def test_filtro_expiring_con_rango_de_fin(
    session: AsyncSession, escenario: Escenario
) -> None:
    pagina = await listar(
        session, status="expiring", ends_from=date(2026, 10, 26), ends_to=date(2026, 10, 28)
    )
    assert escenario.nombres(pagina) == ["pedro", "carlos"]
    rango = await listar(session, ends_from=date(2026, 10, 25), ends_to=date(2026, 10, 29))
    assert escenario.nombres(rango) == ["lucia", "pedro", "carlos", "diana"]  # extremos incluidos


@pytest.mark.parametrize(
    ("estado", "esperados"),
    [
        ("pending_payment", ["eva"]),
        ("frozen", ["hugo"]),
        ("expired", ["felipe"]),
        ("cancelled", ["gina"]),
        ("active,pending_payment", ["diana", "eva", "ana"]),
        ("expired,expiring", ["felipe", "lucia", "pedro", "carlos"]),
    ],
)
async def test_filtro_por_estado_efectivo(
    session: AsyncSession, escenario: Escenario, estado: str, esperados: list[str]
) -> None:
    pagina = await listar(session, status=estado)
    assert escenario.nombres(pagina) == esperados
    assert pagina.total == len(esperados)


async def test_filtro_por_plan_y_por_socio_y_su_combinacion(
    session: AsyncSession, escenario: Escenario
) -> None:
    assert escenario.nombres(await listar(session, plan_id=escenario.trimestral)) == ["ana"]
    assert escenario.nombres(await listar(session, member_id=escenario.socios["pedro"])) == [
        "pedro"
    ]
    combinado = await listar(
        session, status="expiring", plan_id=escenario.mensual, member_id=escenario.socios["pedro"]
    )
    assert escenario.nombres(combinado) == ["pedro"]
    vacio = await listar(session, status="expiring", plan_id=escenario.trimestral)
    assert (vacio.items, vacio.total) == ([], 0)


# Búsqueda (D18: `members.search_ids(include_deleted=True)`) ---------------------------------------


async def test_q_por_apellido_incluye_socios_dados_de_baja(
    session: AsyncSession, escenario: Escenario
) -> None:
    pagina = await listar(session, q="ruiz")
    assert escenario.nombres(pagina) == ["pedro", "ana"]
    assert pagina.total == 2


async def test_q_por_documento_con_el_indice_ciego(
    session: AsyncSession, escenario: Escenario
) -> None:
    pagina = await listar(session, q=KNOWN["document"])
    assert escenario.nombres(pagina) == ["lucia"]


async def test_q_combina_con_el_filtro_de_estado(
    session: AsyncSession, escenario: Escenario
) -> None:
    assert escenario.nombres(await listar(session, q="ruiz", status="expiring")) == ["pedro"]


async def test_q_sin_coincidencias_da_una_pagina_vacia(
    session: AsyncSession, escenario: Escenario, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo():
        pagina = await listar(session, q="Zzyzx")
    assert (pagina.items, pagina.total) == ([], 0)
    assert contador_de_consultas.de("plans.plans") == 0
    assert contador_de_consultas.de("payments.payments") == 0


# Paginación, lotes y cifrado ----------------------------------------------------------------------


async def test_total_no_depende_de_la_pagina(session: AsyncSession, escenario: Escenario) -> None:
    pagina = await listar(session, limit=3, offset=3)
    assert escenario.nombres(pagina) == ["carlos", "diana", "hugo"]
    assert (pagina.total, pagina.limit, pagina.offset) == (8, 3, 3)
    ultima = await listar(session, limit=3, offset=6)
    assert escenario.nombres(ultima) == ["eva", "ana"]


async def test_nombres_congelaciones_y_sumas_van_por_lote(
    session: AsyncSession, escenario: Escenario, contador_de_consultas: ContadorDeConsultas
) -> None:
    """Una sentencia a cada servicio vecino por página (sin N+1), con 8 filas en la página."""
    with contador_de_consultas.midiendo():
        pagina = await listar(session)
    assert len(pagina.items) == 8
    assert contador_de_consultas.de("members.members") == 1
    assert contador_de_consultas.de("plans.plans") == 1
    assert contador_de_consultas.de("payments.payments") == 1
    assert contador_de_consultas.solo_de(TABLA_CONGELACIONES, TABLA_MEMBRESIAS) <= 1


async def test_la_lista_nunca_descifra(session: AsyncSession, escenario: Escenario) -> None:
    await listar(session)
    await listar(session, q=KNOWN["document"])
    await listar(session, q="ruiz")
    decrypts = await session.scalar(
        text("SELECT count(*) FROM crypto.crypto_ops WHERE verb = 'decrypt'")
    )
    assert decrypts == 0


# Validación (D18, L-9, M-4, S3-D47) ---------------------------------------------------------------


@pytest.mark.parametrize("estado", ["vigente", "active,vigente", "ACTIVE"])
async def test_un_estado_desconocido_da_422_en_status(
    session: AsyncSession, escenario: Escenario, estado: str
) -> None:
    with pytest.raises(StatusFilterInvalid) as error:
        await listar(session, status=estado)
    assert (error.value.status, error.value.field) == (422, "status")


def test_un_status_de_101_caracteres_no_pasa_el_esquema() -> None:
    MembershipListQuery(status="a" * 100)
    with pytest.raises(ValidationError) as error:
        MembershipListQuery(status="a" * 101)
    assert error.value.errors()[0]["loc"] == ("status",)


def test_el_esquema_de_filtros_rechaza_campos_desconocidos() -> None:
    with pytest.raises(ValidationError):
        MembershipListQuery.model_validate({"estado": "active"})
    with pytest.raises(ValidationError):
        MembershipListQuery.model_validate({"plan_id": "no-es-uuid"})


@pytest.mark.parametrize(
    ("filtros", "campo"),
    [
        ({"ends_from": date(2019, 12, 31)}, "ends_from"),
        ({"ends_to": date(2019, 12, 31)}, "ends_to"),
        ({"ends_from": date(2032, 10, 21)}, "ends_from"),
        ({"ends_to": date(2032, 10, 21)}, "ends_to"),
        ({"ends_from": date(2026, 11, 1), "ends_to": date(2026, 10, 31)}, "ends_to"),
        ({"ends_from": date(1, 1, 1)}, "ends_from"),
        ({"ends_to": date(9999, 12, 31)}, "ends_to"),
    ],
    ids=[
        "desde-antes-de-2020",
        "hasta-antes-de-2020",
        "desde-hoy-mas-6-anos",
        "hasta-hoy-mas-6-anos",
        "invertidas",
        "anio-1",
        "anio-9999",
    ],
)
async def test_fechas_de_fin_fuera_de_rango_dan_422_con_el_campo(
    session: AsyncSession, escenario: Escenario, filtros: dict[str, date], campo: str
) -> None:
    with pytest.raises(DateRangeInvalid) as error:
        await listar(session, **filtros)
    assert (error.value.status, error.value.code, error.value.field) == (
        422,
        "validation_error",
        campo,
    )


async def test_los_bordes_del_rango_de_fechas_pasan(
    session: AsyncSession, escenario: Escenario
) -> None:
    """Piso 2020-01-01 incluido; un día antes de hoy más 5 años (2031-10-20) pasa."""
    pagina = await listar(session, ends_from=date(2020, 1, 1), ends_to=date(2031, 10, 20))
    assert pagina.total == 8
    mismo_dia = await listar(session, ends_from=date(2026, 10, 25), ends_to=date(2026, 10, 25))
    assert escenario.nombres(mismo_dia) == ["lucia"]


async def test_un_id_de_plan_o_socio_inexistente_da_una_pagina_vacia(
    session: AsyncSession, escenario: Escenario
) -> None:
    assert (await listar(session, plan_id=uuid4())).total == 0
    assert (await listar(session, member_id=uuid4())).total == 0

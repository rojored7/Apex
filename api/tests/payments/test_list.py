"""`payments.service.list` (S3-B8, US-098; D26, M-4, M-8, L-2, S3-D47, S3-D51, S3-D57, S3-D80).

Hoy es 2026-10-21T15:00Z (`reloj`). Escenario (`cuarenta`): 40 pagos de octubre, `k` de 0 a 39,
calculados a mano:
- `paid_at = 2026-10-01T14:00Z + 12 h * k` (k=0 el 1 de octubre a las 14:00Z; k=39 el 21 a las
  02:00Z): todos distintos, así el orden `paid_at DESC, id DESC` es k descendente;
- membresía por `k % 4`: 0 Lucía Gómez (documento `KNOWN`, "Mensual" del 2026-10-01 al
  2026-10-30), 1 Pedro Ruiz ("Mensual" del 2026-09-29 al 2026-10-28), 2 Ana Ruiz (dada de baja,
  "Trimestral" del 2026-10-01 al 2026-12-29), 3 Hugo León ("Mensual" del 2026-09-25 al
  2026-10-24);
- medio por `k % 3`: 0 efectivo, 1 Nequi, 2 Bre-B; monto `1.000 * (k + 1)`;
- registró la cajera `laura.cajera@test.apex` (coach) si k es par y `mario.admin@test.apex`
  (admin) si es impar: `registered_by_name` es `l•••@test.apex` o `m•••@test.apex` (L-2);
- anulados k = 5, 17 y 30; `backdated` k = 8 y 22 (registrados 50 h después del pago; el resto
  1 h después); referencia `NEQ-77001` solo en k = 12.

Conteos a mano: Nequi k = 1, 4, ..., 37 (13); registró la cajera 20; Pedro k = 1, 5, ..., 37
(10); `q="ruiz"` es Pedro y Ana (dada de baja: `search_ids(include_deleted=True)`), k % 4 en
{1, 2} (20); `q="ruiz"` con efectivo: k = 6, 9, 18, 21, 30, 33; el documento `KNOWN` es Lucía
(k = 0, 4, ..., 36).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring
from app.core.pagination import Page, PageParams
from app.modules.payments import service
from app.modules.payments.exceptions import InvalidDateRange
from app.modules.payments.schemas import PaymentListQuery, PaymentRow
from tests.conftest import T0, ContadorDeConsultas
from tests.factories.members import KNOWN, KNOWN_NORMALIZED, make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.payments import MOTIVO_ANULACION, make_payment
from tests.factories.plans import make_plan
from tests.factories.users import make_user
from tests.members._apoyo import operaciones
from tests.payments._apoyo import CAMPOS_ROW, TABLA_PAGOS

PRIMER_PAGO = datetime(2026, 10, 1, 14, 0, tzinfo=UTC)
ANULADOS = (5, 17, 30)
RETROACTIVOS = (8, 22)
SOCIOS = ("lucia", "pedro", "ana", "hugo")
MEDIOS = ("cash", "nequi", "breb")
CORREO_CAJERA = "laura.cajera@test.apex"
CORREO_ADMIN = "mario.admin@test.apex"


def pagado(k: int) -> datetime:
    return PRIMER_PAGO + timedelta(hours=12 * k)


@dataclass(frozen=True)
class Cuarenta:
    pagos: dict[int, UUID]
    socios: dict[str, UUID]
    membresias: dict[str, UUID]
    cajera: UUID
    admin: UUID

    def ks(self, pagina: Page[PaymentRow]) -> list[int]:
        por_id = {v: k for k, v in self.pagos.items()}
        return [por_id[fila.id] for fila in pagina.items]


async def _socio(session: AsyncSession, nombre: str, apellido: str, **cambios: Any) -> Any:
    return await make_member(
        session,
        first_name=nombre,
        last_name=apellido,
        document=unique_document(),
        phone=None,
        email=None,
        **cambios,
    )


@pytest.fixture
async def cuarenta(session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock) -> Cuarenta:
    mensual = await make_plan(session, name="Mensual")
    trimestral = await make_plan(session, name="Trimestral", price_cop=300_000, duration_days=90)
    socios = {
        "lucia": await make_member(session),  # Lucía Gómez, documento KNOWN
        "pedro": await _socio(session, "Pedro", "Ruiz"),
        "ana": await _socio(session, "Ana", "Ruiz", deleted_at=T0 - timedelta(days=1)),
        "hugo": await _socio(session, "Hugo", "León"),
    }
    datos = {
        "lucia": (mensual, date(2026, 10, 1), date(2026, 10, 30)),
        "pedro": (mensual, date(2026, 9, 29), date(2026, 10, 28)),
        "ana": (trimestral, date(2026, 10, 1), date(2026, 12, 29)),
        "hugo": (mensual, date(2026, 9, 25), date(2026, 10, 24)),
    }
    membresias = {
        nombre: await make_membership(
            session, socios[nombre], plan, status="active", start=inicio, end=fin
        )
        for nombre, (plan, inicio, fin) in datos.items()
    }
    cajera = await make_user(session, role="coach", email=CORREO_CAJERA)
    admin = await make_user(session, role="admin", email=CORREO_ADMIN)
    pagos: dict[int, UUID] = {}
    for k in range(40):
        demora = timedelta(hours=50) if k in RETROACTIVOS else timedelta(hours=1)
        pago = await make_payment(
            session,
            membresias[SOCIOS[k % 4]],
            amount=1_000 * (k + 1),
            method=MEDIOS[k % 3],
            paid_at=pagado(k),
            registered_by=cajera.id if k % 2 == 0 else admin.id,
            voided=k in ANULADOS,
            reference="NEQ-77001" if k == 12 else None,
            created_at=pagado(k) + demora,
        )
        pagos[k] = pago.id
    return Cuarenta(
        pagos=pagos,
        socios={n: s.id for n, s in socios.items()},
        membresias={n: m.id for n, m in membresias.items()},
        cajera=cajera.id,
        admin=admin.id,
    )


async def listar(
    session: AsyncSession, *, limit: int = 25, offset: int = 0, **filtros: Any
) -> Page[PaymentRow]:
    """Una petición: `service.list` bajo un actor y el commit de `get_session` (el commit vacía
    la bitácora `crypto_ops` de la unidad de trabajo)."""
    with actor_scope(SYSTEM_USER_ID):
        pagina = await service.list(
            session,
            PaymentListQuery.model_validate(filtros),
            PageParams(limit=limit, offset=offset),
        )
        await session.commit()
    return pagina


# Orden, página y total -------------------------------------------------------------------------


async def test_la_primera_pagina_trae_25_en_orden_descendente_y_total_40(
    session: AsyncSession, cuarenta: Cuarenta
) -> None:
    pagina = await listar(session)
    assert cuarenta.ks(pagina) == list(range(39, 14, -1))
    assert (pagina.total, pagina.limit, pagina.offset) == (40, 25, 0)
    segunda = await listar(session, offset=25)
    assert cuarenta.ks(segunda) == list(range(14, -1, -1))
    assert segunda.total == 40


async def test_el_rango_del_mes_de_bogota_trae_los_40(
    session: AsyncSession, cuarenta: Cuarenta
) -> None:
    pagina = await listar(
        session,
        **{
            "from": datetime(2026, 10, 1, 5, tzinfo=UTC),
            "to": datetime(2026, 11, 1, 5, tzinfo=UTC),
        },
    )
    assert pagina.total == 40


async def test_la_fila_trae_el_contrato_con_nombres_y_fechas_de_los_services_vecinos(
    session: AsyncSession, cuarenta: Cuarenta
) -> None:
    pagina = await listar(session, limit=200)
    filas = dict(zip(cuarenta.ks(pagina), pagina.items, strict=True))
    doce = filas[12]
    assert set(doce.model_dump()) == CAMPOS_ROW
    assert doce.id == cuarenta.pagos[12]
    assert (doce.paid_at, doce.amount_cop, doce.method, doce.reference) == (
        datetime(2026, 10, 7, 14, tzinfo=UTC),
        13_000,
        "cash",
        "NEQ-77001",
    )
    assert (doce.voided, doce.void_reason, doce.backdated) == (False, None, False)
    assert (doce.registered_by, doce.registered_by_name) == (cuarenta.cajera, "l•••@test.apex")
    assert (doce.membership_id, doce.member_id) == (
        cuarenta.membresias["lucia"],
        cuarenta.socios["lucia"],
    )
    assert (doce.member_first_name, doce.member_last_name, doce.plan_name) == (
        "Lucía",
        "Gómez",
        "Mensual",
    )
    assert (doce.membership_start_date, doce.membership_end_date) == (
        date(2026, 10, 1),
        date(2026, 10, 30),
    )


async def test_anulados_retroactivos_y_dados_de_baja_en_la_fila(
    session: AsyncSession, cuarenta: Cuarenta
) -> None:
    filas = dict(zip(*_ks_y_filas(cuarenta, await listar(session, limit=200)), strict=True))
    treinta = filas[30]  # Ana Ruiz (dada de baja), efectivo, anulado, la cajera
    assert (treinta.voided, treinta.void_reason) == (True, MOTIVO_ANULACION)
    assert (treinta.member_first_name, treinta.member_last_name) == ("Ana", "Ruiz")
    assert (treinta.plan_name, treinta.membership_end_date) == ("Trimestral", date(2026, 12, 29))
    veintidos = filas[22]  # Ana Ruiz, Nequi, registrado 50 h después
    assert (veintidos.backdated, veintidos.method, veintidos.amount_cop) == (True, "nequi", 23_000)
    cinco = filas[5]  # Pedro Ruiz, Bre-B, anulado, el admin
    assert (cinco.voided, cinco.method, cinco.registered_by_name) == (
        True,
        "breb",
        "m•••@test.apex",
    )
    assert (cinco.member_first_name, cinco.membership_start_date) == ("Pedro", date(2026, 9, 29))
    assert [k for k, fila in filas.items() if fila.backdated] == [22, 8]
    assert all(type(fila.amount_cop) is int for fila in filas.values())


def _ks_y_filas(datos: Cuarenta, pagina: Page[PaymentRow]) -> tuple[list[int], list[PaymentRow]]:
    return datos.ks(pagina), list(pagina.items)


# Filtros (D26, S3-D51) -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filtros", "esperados"),
    [
        ({"voided": True}, [30, 17, 5]),
        ({"backdated": True}, [22, 8]),
        ({"method": "nequi"}, [37, 34, 31, 28, 25, 22, 19, 16, 13, 10, 7, 4, 1]),
        ({"q": "neq-77001"}, [12]),
        ({"q": "NEQ-77001"}, [12]),
        ({"q": "ruiz", "method": "cash"}, [33, 30, 21, 18, 9, 6]),
        ({"q": "ruiz", "method": "cash", "voided": False}, [33, 21, 18, 9, 6]),
        ({"q": KNOWN["document"]}, [36, 32, 28, 24, 20, 16, 12, 8, 4, 0]),
        ({"q": "Zzyzx"}, []),
        ({"voided": True, "backdated": True}, []),
    ],
    ids=[
        "anulados",
        "retroactivos",
        "nequi",
        "referencia-minusculas",
        "referencia-mayusculas",
        "apellido-y-efectivo",
        "apellido-efectivo-vigentes",
        "documento",
        "sin-coincidencias",
        "anulado-y-retroactivo",
    ],
)
async def test_cada_filtro(
    session: AsyncSession, cuarenta: Cuarenta, filtros: dict[str, Any], esperados: list[int]
) -> None:
    pagina = await listar(session, **filtros)
    assert cuarenta.ks(pagina) == esperados
    assert pagina.total == len(esperados)


@pytest.mark.parametrize(
    ("filtros", "total"),
    [
        ({"voided": False}, 37),
        ({"backdated": False}, 38),
        ({"q": "ruiz"}, 20),
        ({"q": "rui"}, 20),
    ],
    ids=["vigentes", "no-retroactivos", "apellido", "apellido-parcial"],
)
async def test_totales_de_los_filtros_complementarios(
    session: AsyncSession, cuarenta: Cuarenta, filtros: dict[str, Any], total: int
) -> None:
    pagina = await listar(session, **filtros)
    assert pagina.total == total
    assert len(pagina.items) == min(total, 25)


async def test_registro_socio_y_membresia(session: AsyncSession, cuarenta: Cuarenta) -> None:
    cajera = await listar(session, registered_by=cuarenta.cajera)
    assert cajera.total == 20
    assert all(fila.registered_by == cuarenta.cajera for fila in cajera.items)
    pedro = await listar(session, member_id=cuarenta.socios["pedro"])
    assert cuarenta.ks(pedro) == [37, 33, 29, 25, 21, 17, 13, 9, 5, 1]
    hugo = await listar(session, membership_id=cuarenta.membresias["hugo"])
    assert cuarenta.ks(hugo) == [39, 35, 31, 27, 23, 19, 15, 11, 7, 3]


async def test_el_rango_incluye_from_y_excluye_to(
    session: AsyncSession, cuarenta: Cuarenta
) -> None:
    pagina = await listar(session, **{"from": pagado(10), "to": pagado(20)})
    assert cuarenta.ks(pagina) == list(range(19, 9, -1))


async def test_q_por_apellido_incluye_socios_dados_de_baja(
    session: AsyncSession, cuarenta: Cuarenta
) -> None:
    pagina = await listar(session, q="ruiz", limit=200)
    assert sorted(cuarenta.ks(pagina)) == sorted(k for k in range(40) if k % 4 in (1, 2))
    assert {fila.member_last_name for fila in pagina.items} == {"Ruiz"}
    assert {fila.member_first_name for fila in pagina.items} == {"Pedro", "Ana"}


# Validación (M-4, S3-D47) ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filtros", "campo"),
    [
        ({"from": datetime(2019, 12, 31, tzinfo=UTC)}, "from"),
        ({"to": datetime(2032, 10, 21, tzinfo=UTC)}, "to"),
        ({"from": pagado(20), "to": pagado(10)}, "to"),
    ],
    ids=["desde-2019", "hasta-hoy-mas-6-anios", "invertidas"],
)
async def test_fechas_fuera_de_rango_dan_422_con_el_campo(
    session: AsyncSession, cuarenta: Cuarenta, filtros: dict[str, Any], campo: str
) -> None:
    with pytest.raises(InvalidDateRange) as error:
        await listar(session, **filtros)
    assert (error.value.status, error.value.field) == (422, campo)


# Lotes, cifrado y correo parcial (S3-D57, S3-D80) ---------------------------------------------


async def test_una_sentencia_por_servicio_vecino_por_pagina(
    session: AsyncSession, cuarenta: Cuarenta, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo():
        pagina = await listar(session)
    assert len(pagina.items) == 25
    assert contador_de_consultas.de("memberships.memberships") == 1
    assert contador_de_consultas.de("members.members") == 1  # nombres; sin `q` no busca
    assert contador_de_consultas.de("plans.plans") == 1
    assert contador_de_consultas.de("auth.users") == 1
    assert contador_de_consultas.de(TABLA_PAGOS) <= 2  # la página y su total


async def test_con_q_la_busqueda_de_socios_es_una_sentencia_mas(
    session: AsyncSession, cuarenta: Cuarenta, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo():
        pagina = await listar(session, q="ruiz")
    assert len(pagina.items) == 20
    assert contador_de_consultas.de("members.members") == 2  # `search_ids` y nombres
    assert contador_de_consultas.de("memberships.memberships") == 1
    assert contador_de_consultas.de("auth.users") == 1


async def test_q_sin_coincidencias_no_consulta_a_los_vecinos(
    session: AsyncSession, cuarenta: Cuarenta, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo():
        pagina = await listar(session, q="Zzyzx")
    assert (pagina.items, pagina.total) == ([], 0)
    assert contador_de_consultas.de("memberships.memberships") == 0
    assert contador_de_consultas.de("plans.plans") == 0
    assert contador_de_consultas.de("auth.users") == 0


async def test_la_fila_no_trae_datos_cifrados_ni_el_correo_completo(
    session: AsyncSession, cuarenta: Cuarenta
) -> None:
    texto = (await listar(session, limit=200)).model_dump_json()
    for valor in (*KNOWN_NORMALIZED, "apx1.", CORREO_CAJERA, CORREO_ADMIN, "laura.cajera"):
        assert valor not in texto, valor
    assert "l•••@test.apex" in texto and "m•••@test.apex" in texto


async def test_sin_q_no_hay_operaciones_de_cripto_y_con_q_solo_indices(
    session: AsyncSession, cuarenta: Cuarenta
) -> None:
    """Ningún `decrypt` nunca; sin `q` ninguna operación del bus; con `q` por documento solo el
    índice ciego de la búsqueda de socios."""
    antes = len(await operaciones(session))
    await listar(session, limit=200)
    await listar(session, voided=True, method="cash")
    assert len(await operaciones(session)) == antes
    indices = len(await operaciones(session, verb="index"))
    await listar(session, q=KNOWN["document"])
    assert len(await operaciones(session, verb="index")) > indices
    assert await operaciones(session, verb="decrypt") == []

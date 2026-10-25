"""`payments.service.list_for_member(session, member_id, voided, page, *, q=None)` (S3-B11,
US-101; D26, D28, M-8, L-2; condición 3 del impacto).

La pestaña "Pagos" de la ficha: los pagos de UN socio (de todas sus membresías) sobre la misma
consulta de `list` con `member_id` fijo, en orden `paid_at DESC, id DESC`, como `PaymentRow`
(con `backdated` y el correo parcial de quien registró). `voided` es tri-estado (`None` no
filtra). El socio se valida con `members.service.ensure_exists(include_deleted=True)`: un dado
de baja ve los suyos y uno inexistente da `MemberNotFound` (404). `q` es la referencia EXACTA sin
distinguir mayúsculas (D28) y nunca busca personas: no llama a `members.search_ids` (por eso la
ruta no tiene 429) y no deja filas `index` ni `decrypt` en `crypto_ops`.

Hoy es 2026-10-21T15:00Z (`reloj`). Escenario (`pestana`), socia Lucía Gómez con dos
membresías "Mensual": M1 del 2026-09-01 al 2026-09-30 y M2 del 2026-10-01 al 2026-10-30. Tres
pagos, calculados a mano:
- p1 (M1): 120.000 por Nequi el 2026-09-01T15:00Z, referencia `NEQ-1001`, registrado 1 h
  después;
- p2 (M2): 60.000 en efectivo el 2026-10-01T15:00Z, ANULADO, registrado 1 h después;
- p3 (M2): 120.000 por Bre-B el 2026-10-02T15:00Z, registrado 50 h después (`backdated`).
Descendente: p3, p2, p1. Pedro Ruiz tiene un pago con la MISMA referencia `NEQ-1001` (nunca
aparece en la pestaña de Lucía) y Ana Ruiz (dada de baja) uno de 90.000.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring
from app.core.pagination import Page, PageParams
from app.modules.members import service as members_service
from app.modules.members.exceptions import MemberNotFound
from app.modules.payments import service
from app.modules.payments.schemas import PaymentRow
from tests.conftest import T0, ContadorDeConsultas
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.factories.users import make_user
from tests.payments._apoyo import CAMPOS_ROW

REFERENCIA = "NEQ-1001"
CORREO_CAJERA = "laura.cajera@test.apex"


@dataclass(frozen=True)
class Pestana:
    pagos: dict[str, UUID]
    lucia: UUID
    pedro: UUID
    ana: UUID
    m1: UUID
    m2: UUID

    def claves(self, pagina: Page[PaymentRow]) -> list[str]:
        por_id = {v: k for k, v in self.pagos.items()}
        return [por_id[fila.id] for fila in pagina.items]


def _a_las(dia: date) -> datetime:
    return datetime(dia.year, dia.month, dia.day, 15, tzinfo=UTC)


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
async def pestana(session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock) -> Pestana:
    mensual = await make_plan(session, name="Mensual")
    cajera = await make_user(session, role="coach", email=CORREO_CAJERA)
    lucia = await make_member(session)  # Lucía Gómez
    pedro = await _socio(session, "Pedro", "Ruiz")
    ana = await _socio(session, "Ana", "Ruiz", deleted_at=T0 - timedelta(days=1))
    m1 = await make_membership(
        session, lucia, mensual, status="active", start=date(2026, 9, 1), end=date(2026, 9, 30)
    )
    m2 = await make_membership(
        session, lucia, mensual, status="active", start=date(2026, 10, 1), end=date(2026, 10, 30)
    )
    de_pedro = await make_membership(session, pedro, mensual, status="active")
    de_ana = await make_membership(session, ana, mensual, status="active")
    una_hora = timedelta(hours=1)
    p1_pagado = _a_las(date(2026, 9, 1))
    p2_pagado = _a_las(date(2026, 10, 1))
    p3_pagado = _a_las(date(2026, 10, 2))
    p1 = await make_payment(
        session,
        m1,
        amount=120_000,
        method="nequi",
        reference=REFERENCIA,
        paid_at=p1_pagado,
        registered_by=cajera.id,
        created_at=p1_pagado + una_hora,
    )
    p2 = await make_payment(
        session,
        m2,
        amount=60_000,
        method="cash",
        paid_at=p2_pagado,
        voided=True,
        registered_by=cajera.id,
        created_at=p2_pagado + una_hora,
    )
    p3 = await make_payment(
        session,
        m2,
        amount=120_000,
        method="breb",
        paid_at=p3_pagado,
        registered_by=cajera.id,
        created_at=p3_pagado + timedelta(hours=50),
    )
    pedro_pagado = _a_las(date(2026, 10, 21)) - timedelta(hours=3)
    de_pedro_pago = await make_payment(
        session,
        de_pedro,
        amount=120_000,
        method="nequi",
        reference=REFERENCIA,
        paid_at=pedro_pagado,
        created_at=pedro_pagado + una_hora,
    )
    ana_pagado = _a_las(date(2026, 10, 20))
    de_ana_pago = await make_payment(
        session, de_ana, amount=90_000, paid_at=ana_pagado, created_at=ana_pagado + una_hora
    )
    return Pestana(
        pagos={
            "p1": p1.id,
            "p2": p2.id,
            "p3": p3.id,
            "pedro": de_pedro_pago.id,
            "ana": de_ana_pago.id,
        },
        lucia=lucia.id,
        pedro=pedro.id,
        ana=ana.id,
        m1=m1.id,
        m2=m2.id,
    )


async def listar(
    session: AsyncSession,
    member_id: UUID,
    *,
    voided: bool | None = None,
    limit: int = 25,
    offset: int = 0,
    q: str | None = None,
) -> Page[PaymentRow]:
    """Una petición: el service bajo un actor y el commit de `get_session` (el commit vacía la
    bitácora `crypto_ops` de la unidad de trabajo)."""
    with actor_scope(SYSTEM_USER_ID):
        pagina = await service.list_for_member(
            session, member_id, voided, PageParams(limit=limit, offset=offset), q=q
        )
        await session.commit()
    return pagina


# Orden, contenido y filtro `voided` ---------------------------------------------------------------


async def test_tres_pagos_en_dos_membresias_en_orden_descendente(
    session: AsyncSession, pestana: Pestana
) -> None:
    pagina = await listar(session, pestana.lucia)
    assert pestana.claves(pagina) == ["p3", "p2", "p1"]
    assert (pagina.total, pagina.limit, pagina.offset) == (3, 25, 0)
    assert {f.membership_id for f in pagina.items} == {pestana.m1, pestana.m2}
    assert {f.member_id for f in pagina.items} == {pestana.lucia}


async def test_voided_false_devuelve_los_dos_vigentes(
    session: AsyncSession, pestana: Pestana
) -> None:
    pagina = await listar(session, pestana.lucia, voided=False)
    assert pestana.claves(pagina) == ["p3", "p1"]
    assert pagina.total == 2
    assert not any(f.voided for f in pagina.items)


async def test_voided_true_devuelve_el_anulado(session: AsyncSession, pestana: Pestana) -> None:
    pagina = await listar(session, pestana.lucia, voided=True)
    assert pestana.claves(pagina) == ["p2"]
    fila = pagina.items[0]
    assert fila.voided is True
    assert fila.void_reason is not None


async def test_la_fila_trae_el_contrato_con_backdated(
    session: AsyncSession, pestana: Pestana
) -> None:
    """M-8: `backdated` presente en toda fila; solo p3 (50 h después del pago) es retroactivo."""
    pagina = await listar(session, pestana.lucia)
    por_clave = dict(zip(pestana.claves(pagina), pagina.items, strict=True))
    for fila in pagina.items:
        assert set(fila.model_dump()) == CAMPOS_ROW
    assert {k: f.backdated for k, f in por_clave.items()} == {"p3": True, "p2": False, "p1": False}
    p1 = por_clave["p1"]
    assert (p1.amount_cop, p1.method, p1.reference) == (120_000, "nequi", REFERENCIA)
    assert (p1.member_first_name, p1.member_last_name, p1.plan_name) == (
        "Lucía",
        "Gómez",
        "Mensual",
    )
    assert (p1.membership_start_date, p1.membership_end_date) == (
        date(2026, 9, 1),
        date(2026, 9, 30),
    )
    assert p1.registered_by_name == "l" + chr(0x2022) * 3 + "@test.apex"  # parcial (L-2)
    assert por_clave["p3"].membership_end_date == date(2026, 10, 30)


async def test_un_socio_dado_de_baja_devuelve_sus_pagos(
    session: AsyncSession, pestana: Pestana
) -> None:
    pagina = await listar(session, pestana.ana)
    assert pestana.claves(pagina) == ["ana"]
    assert pagina.items[0].member_first_name == "Ana"


async def test_un_socio_inexistente_da_member_not_found(
    session: AsyncSession, pestana: Pestana
) -> None:
    with pytest.raises(MemberNotFound) as error:
        await listar(session, uuid4())
    assert (error.value.status, error.value.code) == (404, "member_not_found")
    with pytest.raises(MemberNotFound):
        await listar(session, uuid4(), q=REFERENCIA, voided=False)


async def test_un_socio_sin_pagos_da_una_pagina_vacia(
    session: AsyncSession, pestana: Pestana
) -> None:
    sin_pagos = await _socio(session, "Rosa", "Toro")
    pagina = await listar(session, sin_pagos.id)
    assert (pagina.items, pagina.total) == ([], 0)


async def test_total_no_depende_de_la_pagina(session: AsyncSession, pestana: Pestana) -> None:
    primera = await listar(session, pestana.lucia, limit=2)
    assert pestana.claves(primera) == ["p3", "p2"]
    assert (primera.total, primera.limit, primera.offset) == (3, 2, 0)
    segunda = await listar(session, pestana.lucia, limit=2, offset=2)
    assert pestana.claves(segunda) == ["p1"]
    assert segunda.total == 3


# `q`: referencia exacta (D28) --------------------------------------------------------------------


@pytest.mark.parametrize("q", [REFERENCIA, REFERENCIA.lower(), f"  {REFERENCIA}  "])
async def test_q_es_la_referencia_exacta_sin_distinguir_mayusculas(
    session: AsyncSession, pestana: Pestana, q: str
) -> None:
    pagina = await listar(session, pestana.lucia, q=q)
    assert pestana.claves(pagina) == ["p1"]  # el de Pedro con la misma referencia no aparece
    assert pagina.total == 1


@pytest.mark.parametrize("q", ["NEQ-10", "1001", "NEQ-1001X", "Lucía", "gomez", "ruiz"])
async def test_q_no_es_parcial_ni_busca_personas(
    session: AsyncSession, pestana: Pestana, q: str
) -> None:
    pagina = await listar(session, pestana.lucia, q=q)
    assert (pagina.items, pagina.total) == ([], 0)


@pytest.mark.parametrize("q", ["", "   "])
async def test_q_en_blanco_no_filtra(session: AsyncSession, pestana: Pestana, q: str) -> None:
    assert pestana.claves(await listar(session, pestana.lucia, q=q)) == ["p3", "p2", "p1"]


async def test_q_combina_con_voided(session: AsyncSession, pestana: Pestana) -> None:
    assert pestana.claves(await listar(session, pestana.lucia, q=REFERENCIA, voided=False)) == [
        "p1"
    ]
    assert (await listar(session, pestana.lucia, q=REFERENCIA, voided=True)).total == 0


async def test_q_nunca_llama_a_la_busqueda_de_socios(
    session: AsyncSession, pestana: Pestana, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def prohibida(*_args: Any, **_kwargs: Any) -> set[UUID]:
        raise AssertionError("list_for_member no busca personas")

    monkeypatch.setattr(members_service, "search_ids", prohibida)
    assert pestana.claves(await listar(session, pestana.lucia, q=REFERENCIA)) == ["p1"]
    assert (await listar(session, pestana.lucia, q="gomez")).total == 0


# Lotes y cifrado ----------------------------------------------------------------------------------


async def test_las_sentencias_no_crecen_con_las_filas(
    session: AsyncSession, pestana: Pestana, contador_de_consultas: ContadorDeConsultas
) -> None:
    """La pestaña de Pedro (1 pago) y la de Lucía (3, en dos membresías) envían el mismo número
    de sentencias: socio, plan, membresía y quien registró van por lote (`_enrich`)."""
    with contador_de_consultas.midiendo():
        await listar(session, pestana.pedro)
    uno = len(contador_de_consultas.sentencias)
    with contador_de_consultas.midiendo():
        await listar(session, pestana.lucia)
    tres = len(contador_de_consultas.sentencias)
    assert uno == tres


async def test_nunca_descifra_ni_calcula_indices(session: AsyncSession, pestana: Pestana) -> None:
    async def contar() -> Any:
        consulta = "SELECT count(*) FROM crypto.crypto_ops WHERE verb IN ('decrypt', 'index')"
        return await session.scalar(text(consulta))

    antes = await contar()
    await listar(session, pestana.lucia)
    await listar(session, pestana.lucia, q=REFERENCIA)
    await listar(session, pestana.lucia, q="gomez")
    await listar(session, pestana.ana, voided=False)
    assert await contar() == antes


def test_esta_en_la_fachada_de_pagos() -> None:
    assert "list_for_member" in service.__all__

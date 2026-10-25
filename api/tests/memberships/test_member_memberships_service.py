"""`memberships.service.list_for_member` (S3-B11, US-093; D5, D28; condición 3 del impacto).

La pestaña "Membresías" de la ficha: todas las membresías de UN socio, incluidas las anuladas,
de la más reciente a la más vieja (`start_date DESC, id`), como `MembershipOut` (con sus
congelaciones) y el estado EFECTIVO (D5). El socio se valida con
`members.service.ensure_exists(include_deleted=True)`: un dado de baja ve las suyas y uno
inexistente da `MemberNotFound` (404). `q` filtra por nombre de plan con
`plans.service.search_ids` (mismo pliegue de tildes que `plans.list`; incluye planes dados de
baja) y nunca busca personas (no llama a `members.search_ids`). Nombres, `paid_cop` y
congelaciones van por lote (sin N+1). Nunca descifra.

Hoy es 2026-10-21 (`reloj`), `expiring_days` 7. Escenario (`ficha`), socia Lucía Gómez:
- A "Plan Antiguo Único" (dado de baja; 100.000) `active` guardada del 2026-06-01 al 2026-06-30
  → `expired`; un pago de 100.000 → `paid_cop` 100.000;
- B "Trimestral Básico" (300.000) `cancelled` del 2026-07-01 al 2026-09-28;
- E "Mensual" `cancelled` del 2026-09-25 al 2026-10-24 (mismo inicio que C: desempata el id);
- C "Mensual" (120.000) `active` del 2026-09-25 al 2026-10-25 con congelaciones del 1 al 2 de
  octubre (2 días) y del 20 al 23 (4 días, contiene hoy) → `frozen`; pagos de 60.000 y 30.000
  anulado → `paid_cop` 60.000;
- D "Trimestral Básico" `pending_payment` del 2026-10-26 al 2027-01-23 → `pending_payment`.
Orden esperado: D, después C y E por id ascendente, B, A (total 5). Pedro Ruiz tiene una
membresía que nunca aparece; Ana Ruiz (dada de baja) tiene una "Mensual" `active` del
2026-10-01 al 2026-10-30.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
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
from app.modules.memberships import service
from app.modules.memberships.schemas import MembershipOut
from app.modules.plans import service as plans_service
from tests.conftest import T0, ContadorDeConsultas
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import MOTIVO_ANULACION, make_freeze, make_membership
from tests.factories.payments import make_payment
from tests.factories.plans import make_plan
from tests.memberships._apoyo import (
    CAMPOS_FREEZE,
    CAMPOS_MEMBERSHIP,
    TABLA_CONGELACIONES,
    TABLA_MEMBRESIAS,
)


@dataclass(frozen=True)
class Ficha:
    membresias: dict[str, UUID]
    lucia: UUID
    pedro: UUID
    ana: UUID
    ana_membresia: UUID
    mensual: UUID
    trimestral: UUID
    antiguo: UUID

    @property
    def orden(self) -> list[UUID]:
        m = self.membresias
        return [m["d"], *sorted([m["c"], m["e"]]), m["b"], m["a"]]

    def nombres(self, pagina: Page[MembershipOut]) -> list[str]:
        por_id = {v: k for k, v in self.membresias.items()}
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
async def ficha(session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock) -> Ficha:
    mensual = await make_plan(session, name="Mensual")
    trimestral = await make_plan(
        session, name="Trimestral Básico", price_cop=300_000, duration_days=90
    )
    antiguo = await make_plan(
        session, name="Plan Antiguo Único", price_cop=100_000, deleted_at=T0 - timedelta(days=60)
    )
    lucia = await make_member(session)  # Lucía Gómez
    pedro = await _socio(session, "Pedro", "Ruiz")
    ana = await _socio(session, "Ana", "Ruiz", deleted_at=T0 - timedelta(days=1))
    datos: dict[str, tuple[Any, str, date, date]] = {
        "a": (antiguo, "active", date(2026, 6, 1), date(2026, 6, 30)),
        "b": (trimestral, "cancelled", date(2026, 7, 1), date(2026, 9, 28)),
        "e": (mensual, "cancelled", date(2026, 9, 25), date(2026, 10, 24)),
        "c": (mensual, "active", date(2026, 9, 25), date(2026, 10, 25)),
        "d": (trimestral, "pending_payment", date(2026, 10, 26), date(2027, 1, 23)),
    }
    membresias: dict[str, Any] = {}
    for clave, (plan, estado, inicio, fin) in datos.items():
        membresias[clave] = await make_membership(
            session, lucia, plan, status=estado, start=inicio, end=fin
        )
    await make_freeze(session, membresias["c"], date(2026, 10, 1), date(2026, 10, 2))
    await make_freeze(session, membresias["c"], date(2026, 10, 20), date(2026, 10, 23))
    await make_payment(session, membresias["a"], amount=100_000)
    await make_payment(session, membresias["c"], amount=60_000)
    await make_payment(session, membresias["c"], amount=30_000, voided=True)
    await make_membership(session, pedro, mensual, status="active")
    de_ana = await make_membership(
        session, ana, mensual, status="active", start=date(2026, 10, 1), end=date(2026, 10, 30)
    )
    return Ficha(
        membresias={k: m.id for k, m in membresias.items()},
        lucia=lucia.id,
        pedro=pedro.id,
        ana=ana.id,
        ana_membresia=de_ana.id,
        mensual=mensual.id,
        trimestral=trimestral.id,
        antiguo=antiguo.id,
    )


async def listar(
    session: AsyncSession,
    member_id: UUID,
    *,
    limit: int = 25,
    offset: int = 0,
    q: str | None = None,
) -> Page[MembershipOut]:
    """Una petición: el service bajo un actor y el commit de `get_session` (el commit vacía la
    bitácora `crypto_ops` de la unidad de trabajo)."""
    with actor_scope(SYSTEM_USER_ID):
        pagina = await service.list_for_member(
            session, member_id, PageParams(limit=limit, offset=offset), q=q
        )
        await session.commit()
    return pagina


# Orden, contenido y estado efectivo -------------------------------------------------------------


async def test_ordena_por_inicio_descendente_e_id_e_incluye_las_anuladas(
    session: AsyncSession, ficha: Ficha
) -> None:
    pagina = await listar(session, ficha.lucia)
    assert [f.id for f in pagina.items] == ficha.orden
    assert (pagina.total, pagina.limit, pagina.offset) == (5, 25, 0)
    assert {ficha.membresias["b"], ficha.membresias["e"]} <= {f.id for f in pagina.items}


async def test_solo_trae_las_membresias_del_socio_pedido(
    session: AsyncSession, ficha: Ficha
) -> None:
    pagina = await listar(session, ficha.lucia)
    assert {f.member_id for f in pagina.items} == {ficha.lucia}
    de_pedro = await listar(session, ficha.pedro)
    assert de_pedro.total == 1
    assert de_pedro.items[0].member_id == ficha.pedro


async def test_el_estado_mostrado_es_el_efectivo(session: AsyncSession, ficha: Ficha) -> None:
    """D5: A está `active` guardada pero vencida; C está `active` guardada y congelada hoy."""
    pagina = await listar(session, ficha.lucia)
    estados = dict(zip(ficha.nombres(pagina), (f.status for f in pagina.items), strict=True))
    assert estados == {
        "d": "pending_payment",
        "c": "frozen",
        "e": "cancelled",
        "b": "cancelled",
        "a": "expired",
    }
    guardados: dict[UUID, str] = dict(
        (await session.execute(text("SELECT id, status FROM memberships.memberships"))).all()
    )
    assert guardados[ficha.membresias["a"]] == "active"
    assert guardados[ficha.membresias["c"]] == "active"


async def test_cada_fila_es_un_membership_out_con_nombres_y_congelaciones(
    session: AsyncSession, ficha: Ficha
) -> None:
    pagina = await listar(session, ficha.lucia)
    por_clave = dict(zip(ficha.nombres(pagina), pagina.items, strict=True))
    for fila in pagina.items:
        assert isinstance(fila, MembershipOut)
        assert set(fila.model_dump()) == CAMPOS_MEMBERSHIP
        assert fila.member_name == "Lucía Gómez"
    c = por_clave["c"]
    assert (c.plan_id, c.plan_name, c.agreed_price_cop) == (ficha.mensual, "Mensual", 120_000)
    assert (c.start_date, c.end_date) == (date(2026, 9, 25), date(2026, 10, 25))
    assert [(z.frozen_from, z.frozen_to, z.days) for z in c.freezes] == [
        (date(2026, 10, 1), date(2026, 10, 2), 2),
        (date(2026, 10, 20), date(2026, 10, 23), 4),
    ]
    assert all(set(z.model_dump()) == CAMPOS_FREEZE for z in c.freezes)
    assert [por_clave[k].freezes for k in ("a", "b", "d", "e")] == [[], [], [], []]
    a = por_clave["a"]
    assert (a.plan_id, a.plan_name) == (ficha.antiguo, "Plan Antiguo Único")  # plan dado de baja
    b = por_clave["b"]
    assert (b.plan_name, b.cancel_reason) == ("Trimestral Básico", MOTIVO_ANULACION)
    assert b.cancelled_at is not None
    assert (c.cancel_reason, c.cancelled_at) == (None, None)


async def test_paid_cop_suma_solo_los_pagos_no_anulados(
    session: AsyncSession, ficha: Ficha
) -> None:
    pagina = await listar(session, ficha.lucia)
    pagado = dict(zip(ficha.nombres(pagina), (f.paid_cop for f in pagina.items), strict=True))
    assert pagado == {"d": 0, "c": 60_000, "e": 0, "b": 0, "a": 100_000}


async def test_un_socio_dado_de_baja_devuelve_las_suyas(
    session: AsyncSession, ficha: Ficha
) -> None:
    pagina = await listar(session, ficha.ana)
    assert [f.id for f in pagina.items] == [ficha.ana_membresia]
    assert pagina.items[0].member_name == "Ana Ruiz"
    assert pagina.total == 1


async def test_un_socio_inexistente_da_member_not_found(
    session: AsyncSession, ficha: Ficha
) -> None:
    with pytest.raises(MemberNotFound) as error:
        await listar(session, uuid4())
    assert (error.value.status, error.value.code) == (404, "member_not_found")


async def test_un_socio_inexistente_da_404_aunque_venga_q(
    session: AsyncSession, ficha: Ficha
) -> None:
    with pytest.raises(MemberNotFound):
        await listar(session, uuid4(), q="mensual")


async def test_un_socio_sin_membresias_da_una_pagina_vacia(
    session: AsyncSession, ficha: Ficha
) -> None:
    sin_nada = await _socio(session, "Rosa", "Toro")
    pagina = await listar(session, sin_nada.id)
    assert (pagina.items, pagina.total) == ([], 0)


# Paginación --------------------------------------------------------------------------------------


async def test_total_no_depende_de_la_pagina(session: AsyncSession, ficha: Ficha) -> None:
    primera = await listar(session, ficha.lucia, limit=2)
    assert [f.id for f in primera.items] == ficha.orden[:2]
    assert (primera.total, primera.limit, primera.offset) == (5, 2, 0)
    segunda = await listar(session, ficha.lucia, limit=2, offset=2)
    assert [f.id for f in segunda.items] == ficha.orden[2:4]
    ultima = await listar(session, ficha.lucia, limit=2, offset=4)
    assert [f.id for f in ultima.items] == ficha.orden[4:]
    assert ultima.total == 5


# Búsqueda por nombre de plan (D28) ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("q", "claves"),
    [
        ("mensual", ["c", "e"]),
        ("basico", ["d", "b"]),
        ("TRIMESTRAL BÁSICO", ["d", "b"]),
        ("antiguo unico", ["a"]),
    ],
    ids=["mensual", "sin-tilde", "mayusculas-con-tilde", "plan-dado-de-baja"],
)
async def test_q_filtra_por_nombre_de_plan_con_tildes_plegadas(
    session: AsyncSession, ficha: Ficha, q: str, claves: list[str]
) -> None:
    pagina = await listar(session, ficha.lucia, q=q)
    esperados = [i for i in ficha.orden if i in {ficha.membresias[k] for k in claves}]
    assert [f.id for f in pagina.items] == esperados
    assert pagina.total == len(claves)


async def test_q_no_trae_membresias_de_otro_socio_con_el_mismo_plan(
    session: AsyncSession, ficha: Ficha
) -> None:
    pagina = await listar(session, ficha.pedro, q="mensual")
    assert pagina.total == 1
    assert pagina.items[0].member_id == ficha.pedro


@pytest.mark.parametrize("q", ["", "   "])
async def test_q_en_blanco_no_filtra(session: AsyncSession, ficha: Ficha, q: str) -> None:
    pagina = await listar(session, ficha.lucia, q=q)
    assert [f.id for f in pagina.items] == ficha.orden


async def test_q_sin_coincidencias_da_una_pagina_vacia_sin_consultar_vecinos(
    session: AsyncSession, ficha: Ficha, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo():
        pagina = await listar(session, ficha.lucia, q="Zzyzx")
    assert (pagina.items, pagina.total) == ([], 0)
    assert contador_de_consultas.de("payments.payments") == 0
    assert contador_de_consultas.de(TABLA_CONGELACIONES) == 0


async def test_q_usa_plans_search_ids_y_nunca_busca_personas(
    session: AsyncSession, ficha: Ficha, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D28: `q` es nombre de plan (`plans.service.search_ids`); `members.search_ids` (índices
    ciegos, cubeta de búsquedas de personas) no se llama: por eso la ruta no tiene 429."""
    original = plans_service.search_ids
    llamadas: list[str | None] = []

    async def espia(sesion: AsyncSession, q: str | None) -> set[UUID]:
        llamadas.append(q)
        return await original(sesion, q)

    async def prohibida(*_args: Any, **_kwargs: Any) -> set[UUID]:
        raise AssertionError("list_for_member no busca personas")

    monkeypatch.setattr(plans_service, "search_ids", espia)
    monkeypatch.setattr(members_service, "search_ids", prohibida)
    pagina = await listar(session, ficha.lucia, q="basico")
    assert pagina.total == 2
    assert llamadas == ["basico"]


async def test_sin_q_no_busca_planes(
    session: AsyncSession, ficha: Ficha, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def prohibida(*_args: Any, **_kwargs: Any) -> set[UUID]:
        raise AssertionError("sin q no se busca")

    monkeypatch.setattr(plans_service, "search_ids", prohibida)
    monkeypatch.setattr(members_service, "search_ids", prohibida)
    assert (await listar(session, ficha.lucia)).total == 5


# Lotes (sin N+1) y cifrado ------------------------------------------------------------------------


async def test_nombres_congelaciones_y_sumas_van_por_lote(
    session: AsyncSession, ficha: Ficha, contador_de_consultas: ContadorDeConsultas
) -> None:
    """Con 5 filas en la página: una sentencia de congelaciones, una de sumas y una de nombres de
    planes; socios a lo sumo dos (la existencia del socio y sus nombres)."""
    with contador_de_consultas.midiendo():
        pagina = await listar(session, ficha.lucia)
    assert len(pagina.items) == 5
    assert contador_de_consultas.solo_de(TABLA_CONGELACIONES, TABLA_MEMBRESIAS) == 1
    assert contador_de_consultas.de("payments.payments") == 1
    assert contador_de_consultas.de("plans.plans") == 1
    assert contador_de_consultas.de("members.members") <= 2


async def test_las_sentencias_no_crecen_con_las_filas(
    session: AsyncSession, ficha: Ficha, contador_de_consultas: ContadorDeConsultas
) -> None:
    """La página de Pedro (1 membresía) y la de Lucía (5, con congelaciones y pagos) envían el
    mismo número de sentencias: congelaciones, nombres y sumas van por lote."""
    with contador_de_consultas.midiendo():
        await listar(session, ficha.pedro)
    una = len(contador_de_consultas.sentencias)
    with contador_de_consultas.midiendo():
        await listar(session, ficha.lucia)
    cinco = len(contador_de_consultas.sentencias)
    assert una == cinco


async def test_nunca_descifra(session: AsyncSession, ficha: Ficha) -> None:
    async def contar() -> Any:
        consulta = "SELECT count(*) FROM crypto.crypto_ops WHERE verb IN ('decrypt', 'index')"
        return await session.scalar(text(consulta))

    antes = await contar()
    await listar(session, ficha.lucia)
    await listar(session, ficha.lucia, q="mensual")
    await listar(session, ficha.ana)
    assert await contar() == antes


def test_esta_en_la_fachada_de_membresias() -> None:
    assert "list_for_member" in service.__all__

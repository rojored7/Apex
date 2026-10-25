"""`members.service.list` con `membership_status` y `plan_id` (S3-B9b; US-071 criterios 1 a 7;
D22, G-03, G-04, N-01, N-20, S3-D71; blueprint B9 y plan B9b.2).

Hoy es 2026-10-21 en Bogotá (`reloj`) y `expiring_days` es 7 (la política por defecto). Planes
"Mensual" y "Trimestral". El padrón (`padron`):
- `al_dia`: Mensual `active` del 2026-10-01 al 2026-11-30 (faltan 40 días: `active`);
- `por_vencer`: Mensual `active` del 2026-09-26 al 2026-10-25 (faltan 4: `expiring`);
- `pendiente`: Mensual `pending_payment` del 2026-10-21 al 2026-11-20;
- `vencido`: Mensual guardada `active` del 2026-08-01 al 2026-08-31 (vencida por fecha: `expired`);
- `congelado`: Mensual `active` del 2026-10-01 al 2026-11-15 con congelación del 20 al 23;
- `vigente_y_futura`: Trimestral `active` del 2026-09-01 al 2026-11-29 y una renovación Mensual
  `pending_payment` del 2026-11-30 al 2026-12-29: decide la vigente (Trimestral, `active`, Q1);
- `sin_membresia` y `solo_anulada` (una Mensual `cancelled`): los dos `none`;
- `baja`: dado de baja con una Mensual `active` vigente: solo aparece con `status=deleted`.

Casos: cada estado da su conjunto; `none` es el complemento de los cinco estados entre los vivos;
los seis conjuntos parten a los vivos; `plan_id` filtra por el plan de la membresía que DECIDE (la
renovación Mensual de `vigente_y_futura` no lo pone en el Mensual); un plan inexistente da la
página vacía; `none` con `plan_id` da la página vacía sin consultar socios ni membresías; el dado
de baja aparece con `status=deleted` y su estado; los filtros se combinan con `q` y `sort`; la
rama de documento sigue usando `uq_members_document_idx_alive` (`EXPLAIN` de la consulta enviada
con un filtro de membresía activo); listar no descifra nada; cada página se decora con UNA
llamada a `memberships.service.status_for` con los ids de la página (`membership_status`,
`plan_name` y `membership_end_date`; sin entrada, `none`) y una sola sentencia a
`memberships.memberships` sin filtro de membresía (dos con él: el conjunto y el decorado).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring
from app.core.pagination import Page, PageParams
from app.modules.members import service
from app.modules.members.models import Member
from app.modules.members.schemas import MemberListQuery, MemberRowOut
from app.modules.memberships import service as memberships_service
from tests.conftest import T0, ContadorDeConsultas
from tests.factories.members import make_member, unique_document
from tests.factories.memberships import make_freeze, make_membership
from tests.factories.plans import make_plan
from tests.members._apoyo import CAMPOS_FILA, operaciones

TABLA_SOCIOS = "members.members"
TABLA_MEMBRESIAS = "memberships.memberships"
TABLA_PLANES = "plans.plans"
INDICE_DOCUMENTO = "uq_members_document_idx_alive"
DOCUMENTO_DE_LAURA = "1020304417"
ESTADOS = ("active", "expiring", "expired", "frozen", "pending_payment")


@dataclass(frozen=True)
class Padron:
    mensual: UUID
    trimestral: UUID
    al_dia: UUID
    por_vencer: UUID
    pendiente: UUID
    vencido: UUID
    congelado: UUID
    vigente_y_futura: UUID
    sin_membresia: UUID
    solo_anulada: UUID
    baja: UUID

    @property
    def vivos(self) -> set[UUID]:
        return {
            self.al_dia,
            self.por_vencer,
            self.pendiente,
            self.vencido,
            self.congelado,
            self.vigente_y_futura,
            self.sin_membresia,
            self.solo_anulada,
        }


async def _socio(session: AsyncSession, nombre: str, **cambios: Any) -> Member:
    datos: dict[str, Any] = {
        "first_name": nombre,
        "last_name": "Filtro",
        "document": unique_document(),
        "phone": None,
        "email": None,
        **cambios,
    }
    return await make_member(session, **datos)


@pytest.fixture
async def padron(session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock) -> Padron:
    mensual = await make_plan(session, name="Mensual")
    trimestral = await make_plan(session, name="Trimestral", price_cop=300_000, duration_days=90)
    al_dia = await _socio(session, "AlDia")
    await make_membership(
        session, al_dia, mensual, status="active", start=date(2026, 10, 1), end=date(2026, 11, 30)
    )
    por_vencer = await _socio(session, "PorVencer")
    await make_membership(
        session,
        por_vencer,
        mensual,
        status="active",
        start=date(2026, 9, 26),
        end=date(2026, 10, 25),
    )
    pendiente = await _socio(session, "Pendiente")
    await make_membership(
        session,
        pendiente,
        mensual,
        status="pending_payment",
        start=date(2026, 10, 21),
        end=date(2026, 11, 20),
    )
    vencido = await _socio(session, "Vencido")
    await make_membership(
        session, vencido, mensual, status="active", start=date(2026, 8, 1), end=date(2026, 8, 31)
    )
    congelado = await _socio(session, "Congelado")
    hielo = await make_membership(
        session,
        congelado,
        mensual,
        status="active",
        start=date(2026, 10, 1),
        end=date(2026, 11, 15),
    )
    await make_freeze(session, hielo, date(2026, 10, 20), date(2026, 10, 23))
    doble = await _socio(session, "VigenteFutura")
    await make_membership(
        session,
        doble,
        trimestral,
        status="active",
        start=date(2026, 9, 1),
        end=date(2026, 11, 29),
    )
    await make_membership(
        session,
        doble,
        mensual,
        status="pending_payment",
        start=date(2026, 11, 30),
        end=date(2026, 12, 29),
    )
    sin_membresia = await _socio(session, "SinMembresia")
    solo_anulada = await _socio(session, "SoloAnulada")
    await make_membership(session, solo_anulada, mensual, status="cancelled")
    baja = await _socio(session, "Baja", deleted_at=T0 - timedelta(days=1))
    await make_membership(
        session, baja, mensual, status="active", start=date(2026, 10, 1), end=date(2026, 11, 30)
    )
    return Padron(
        mensual=mensual.id,
        trimestral=trimestral.id,
        al_dia=al_dia.id,
        por_vencer=por_vencer.id,
        pendiente=pendiente.id,
        vencido=vencido.id,
        congelado=congelado.id,
        vigente_y_futura=doble.id,
        sin_membresia=sin_membresia.id,
        solo_anulada=solo_anulada.id,
        baja=baja.id,
    )


async def listar(
    session: AsyncSession, *, limit: int = 200, offset: int = 0, **filtros: Any
) -> Page[MemberRowOut]:
    """Una petición: `service.list` bajo un actor y el commit de `get_session`."""
    with actor_scope(SYSTEM_USER_ID):
        pagina = await service.list(
            session, MemberListQuery(**filtros), PageParams(limit=limit, offset=offset)
        )
        await session.commit()
    return pagina


def ids(pagina: Page[MemberRowOut]) -> set[UUID]:
    return {fila.id for fila in pagina.items}


def fila_de(pagina: Page[MemberRowOut], member_id: UUID) -> MemberRowOut:
    return next(fila for fila in pagina.items if fila.id == member_id)


# Un estado por filtro (US-071 criterios 1 a 4; RN-06, Q11) -----------------------------------


async def test_por_vencer_frente_a_al_dia(session: AsyncSession, padron: Padron) -> None:
    """Fin el 2026-10-25 (4 días, `expiring_days` 7) frente a fin el 2026-11-30."""
    por_vencer = await listar(session, membership_status="expiring")
    al_dia = await listar(session, membership_status="active")
    assert ids(por_vencer) == {padron.por_vencer}
    assert ids(al_dia) == {padron.al_dia, padron.vigente_y_futura}
    assert por_vencer.total == 1 and al_dia.total == 2
    assert fila_de(por_vencer, padron.por_vencer).membership_status == "expiring"
    assert fila_de(por_vencer, padron.por_vencer).membership_end_date == date(2026, 10, 25)
    assert fila_de(al_dia, padron.al_dia).membership_status == "active"


@pytest.mark.parametrize(
    ("estado", "clave"),
    [("pending_payment", "pendiente"), ("expired", "vencido"), ("frozen", "congelado")],
)
async def test_pendiente_vencido_y_congelado(
    session: AsyncSession, padron: Padron, estado: str, clave: str
) -> None:
    pagina = await listar(session, membership_status=estado)
    esperado: UUID = getattr(padron, clave)
    assert ids(pagina) == {esperado}
    assert pagina.items[0].membership_status == estado
    assert pagina.items[0].plan_name == "Mensual"


async def test_none_es_el_complemento_entre_los_vivos(
    session: AsyncSession, padron: Padron
) -> None:
    pagina = await listar(session, membership_status="none")
    assert ids(pagina) == {padron.sin_membresia, padron.solo_anulada}
    for fila in pagina.items:
        assert fila.membership_status == "none"
        assert fila.plan_name is None and fila.membership_end_date is None


async def test_los_seis_filtros_parten_a_los_vivos_sin_repetir(
    session: AsyncSession, padron: Padron
) -> None:
    vistos: list[UUID] = []
    for estado in (*ESTADOS, "none"):
        vistos.extend(ids(await listar(session, membership_status=estado)))
    assert len(vistos) == len(set(vistos))
    assert set(vistos) == padron.vivos


async def test_vigente_mas_futura_muestra_la_vigente(session: AsyncSession, padron: Padron) -> None:
    """Q1: decide la vigente Trimestral, no la renovación Mensual pendiente."""
    pagina = await listar(session)
    fila = fila_de(pagina, padron.vigente_y_futura)
    assert (fila.membership_status, fila.plan_name, fila.membership_end_date) == (
        "active",
        "Trimestral",
        date(2026, 11, 29),
    )
    assert ids(await listar(session, membership_status="pending_payment")) == {padron.pendiente}


async def test_sin_filtros_cada_fila_trae_su_estado_plan_y_fin(
    session: AsyncSession, padron: Padron
) -> None:
    pagina = await listar(session)
    assert ids(pagina) == padron.vivos
    esperado = {
        padron.al_dia: ("active", "Mensual", date(2026, 11, 30)),
        padron.por_vencer: ("expiring", "Mensual", date(2026, 10, 25)),
        padron.pendiente: ("pending_payment", "Mensual", date(2026, 11, 20)),
        padron.vencido: ("expired", "Mensual", date(2026, 8, 31)),
        padron.congelado: ("frozen", "Mensual", date(2026, 11, 15)),
        padron.vigente_y_futura: ("active", "Trimestral", date(2026, 11, 29)),
        padron.sin_membresia: ("none", None, None),
        padron.solo_anulada: ("none", None, None),
    }
    real = {f.id: (f.membership_status, f.plan_name, f.membership_end_date) for f in pagina.items}
    assert real == esperado
    assert all(set(f.model_dump()) == CAMPOS_FILA for f in pagina.items)


# Plan (US-071 criterios 5 y 6) ------------------------------------------------------------


async def test_el_plan_filtra_por_la_membresia_que_decide(
    session: AsyncSession, padron: Padron
) -> None:
    mensual = await listar(session, membership_status="active", plan_id=padron.mensual)
    trimestral = await listar(session, membership_status="active", plan_id=padron.trimestral)
    assert ids(mensual) == {padron.al_dia}
    assert ids(trimestral) == {padron.vigente_y_futura}
    pendiente_mensual = await listar(
        session, membership_status="pending_payment", plan_id=padron.mensual
    )
    assert ids(pendiente_mensual) == {padron.pendiente}  # la renovación no decide


async def test_solo_plan_trae_a_los_socios_cuya_membresia_que_decide_es_de_ese_plan(
    session: AsyncSession, padron: Padron
) -> None:
    """Sin `membership_status`, `plan_id` mira los cinco estados (nunca `none`)."""
    mensual = await listar(session, plan_id=padron.mensual)
    assert ids(mensual) == {
        padron.al_dia,
        padron.por_vencer,
        padron.pendiente,
        padron.vencido,
        padron.congelado,
    }
    assert ids(await listar(session, plan_id=padron.trimestral)) == {padron.vigente_y_futura}


async def test_un_plan_inexistente_da_la_pagina_vacia(
    session: AsyncSession, padron: Padron
) -> None:
    for filtros in ({"plan_id": uuid4()}, {"plan_id": uuid4(), "membership_status": "active"}):
        pagina = await listar(session, **filtros)
        assert pagina.items == [] and pagina.total == 0, filtros


async def test_none_con_plan_da_la_pagina_vacia_sin_consultar(
    session: AsyncSession, padron: Padron, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo():
        pagina = await listar(session, membership_status="none", plan_id=padron.mensual)
    assert pagina.items == [] and pagina.total == 0
    assert (pagina.limit, pagina.offset) == (200, 0)
    assert contador_de_consultas.de(TABLA_SOCIOS) == 0, contador_de_consultas.sentencias
    assert contador_de_consultas.de(TABLA_MEMBRESIAS) == 0, contador_de_consultas.sentencias


# Dados de baja (N-20) y combinación con los filtros de US-070 --------------------------------


async def test_el_dado_de_baja_aparece_con_status_deleted_y_su_estado(
    session: AsyncSession, padron: Padron
) -> None:
    activos = await listar(session, membership_status="active")
    assert padron.baja not in ids(activos)
    bajas = await listar(session, status="deleted", membership_status="active")
    assert ids(bajas) == {padron.baja}
    fila = bajas.items[0]
    assert fila.deleted_at is not None
    assert (fila.membership_status, fila.plan_name) == ("active", "Mensual")
    todas = await listar(session, status="deleted")
    assert fila_de(todas, padron.baja).membership_status == "active"
    assert ids(await listar(session, status="deleted", membership_status="none")) == set()


async def test_se_combina_con_q_sort_y_paginacion(session: AsyncSession, padron: Padron) -> None:
    laura = await make_member(
        session,
        first_name="Laura",
        last_name="Filtro",
        document=DOCUMENTO_DE_LAURA,
        phone=None,
        email=None,
    )
    assert ids(await listar(session, q="1.020.304.417", membership_status="none")) == {laura.id}
    assert ids(await listar(session, q="1.020.304.417", membership_status="active")) == set()
    nombres = await listar(session, q="vencido", membership_status="expired")
    assert ids(nombres) == {padron.vencido}
    primera = await listar(session, membership_status="active", sort="-first_name", limit=1)
    segunda = await listar(
        session, membership_status="active", sort="-first_name", limit=1, offset=1
    )
    assert (primera.total, segunda.total) == (2, 2)
    assert [f.first_name for f in (*primera.items, *segunda.items)] == ["VigenteFutura", "AlDia"]


async def test_el_status_inactive_se_combina_con_el_estado_de_membresia(
    session: AsyncSession, padron: Padron
) -> None:
    otro_plan = await make_plan(session, name="Clases sueltas")
    inactivo = await _socio(session, "Inactivo", status="inactive")
    await make_membership(
        session,
        inactivo,
        otro_plan,
        status="active",
        start=date(2026, 10, 1),
        end=date(2026, 11, 30),
    )
    assert ids(await listar(session, status="inactive", membership_status="active")) == {
        inactivo.id
    }
    activos = await listar(session, status="active", membership_status="active")
    assert ids(activos) == {padron.al_dia, padron.vigente_y_futura}


# Índice, cifrado y consultas --------------------------------------------------------------


def _usa_indice(plan: Any, indice: str) -> bool:
    if isinstance(plan, dict):
        if plan.get("Index Name") == indice:
            return True
        return any(_usa_indice(v, indice) for v in plan.values())
    if isinstance(plan, list):
        return any(_usa_indice(v, indice) for v in plan)
    return False


async def test_la_rama_de_documento_sigue_usando_el_indice_unico_parcial(
    session: AsyncSession, engine: AsyncEngine, padron: Padron
) -> None:
    """D22: el conjunto de ids va en la consulta externa; la subconsulta de documento conserva
    `deleted_at IS NULL` y el planificador puede usar `uq_members_document_idx_alive` (con
    `enable_seqscan = off`, porque con pocas filas un barrido secuencial sería más barato)."""
    await make_member(session, first_name="Laura", last_name="Filtro", document=DOCUMENTO_DE_LAURA)
    # Estadísticas frescas, como `test_list_perf.py`: sin ellas el plan depende de lo que dejaron
    # corridas anteriores (`relpages` de los índices crece con altas revertidas; Verde S3-B9b).
    await session.execute(text("ANALYZE members.members"))
    capturadas: list[tuple[str, Any]] = []

    def anotar(_c: Any, _cur: Any, sql: str, parametros: Any, *_a: Any) -> None:
        if "document_idx" in sql and sql.lstrip().upper().startswith(("SELECT", "WITH")):
            capturadas.append((sql, parametros))

    event.listen(engine.sync_engine, "before_cursor_execute", anotar)
    try:
        pagina = await listar(session, q="1.020.304.417", membership_status="none")
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", anotar)
    assert pagina.total == 1
    assert capturadas, "el service no envió una consulta con document_idx"
    conexion = await session.connection()
    await conexion.exec_driver_sql("SET LOCAL enable_seqscan = off")
    for sql, parametros in capturadas:
        resultado = await conexion.exec_driver_sql("EXPLAIN (FORMAT JSON) " + sql, parametros)
        plan = resultado.scalar_one()
        plan = json.loads(plan) if isinstance(plan, str) else plan
        assert _usa_indice(plan, INDICE_DOCUMENTO), json.dumps(plan)[:2000]


async def test_listar_con_filtros_de_membresia_no_descifra(
    session: AsyncSession, padron: Padron
) -> None:
    descifrados = len(await operaciones(session, verb="decrypt"))
    await listar(session)
    for estado in (*ESTADOS, "none"):
        await listar(session, membership_status=estado)
    await listar(session, plan_id=padron.mensual, status="deleted")
    await listar(session, q="1.020.304", membership_status="active")
    assert len(await operaciones(session, verb="decrypt")) == descifrados


class _EspiaStatusFor:
    def __init__(self) -> None:
        self.llamadas: list[list[UUID]] = []
        self.real = memberships_service.status_for

    async def __call__(self, session: AsyncSession, member_ids: Iterable[UUID], **kw: Any) -> Any:
        pedidos = list(member_ids)
        self.llamadas.append(pedidos)
        return await self.real(session, pedidos, **kw)


async def test_una_sola_llamada_a_status_for_por_pagina_con_los_ids_de_la_pagina(
    session: AsyncSession, padron: Padron, monkeypatch: pytest.MonkeyPatch
) -> None:
    espia = _EspiaStatusFor()
    monkeypatch.setattr(memberships_service, "status_for", espia)
    pagina = await listar(session, limit=3, sort="first_name")
    assert len(espia.llamadas) == 1
    assert sorted(espia.llamadas[0]) == sorted(f.id for f in pagina.items)
    espia.llamadas.clear()
    filtrada = await listar(session, membership_status="active", limit=200)
    assert len(espia.llamadas) == 1
    assert set(espia.llamadas[0]) == ids(filtrada)


async def test_las_columnas_decoradas_salen_de_una_sentencia_por_vecino(
    session: AsyncSession, padron: Padron, contador_de_consultas: ContadorDeConsultas
) -> None:
    """Sin filtro de membresía: una sentencia a `memberships.memberships` (el decorado) y una a
    `plans.plans` (los nombres); con filtro, una más a `memberships.memberships` (el conjunto)."""
    with contador_de_consultas.midiendo():
        await listar(session)
    assert contador_de_consultas.de(TABLA_MEMBRESIAS) == 1, contador_de_consultas.sentencias
    assert contador_de_consultas.de(TABLA_PLANES) == 1, contador_de_consultas.sentencias
    with contador_de_consultas.midiendo():
        await listar(session, membership_status="active", plan_id=padron.mensual)
    assert contador_de_consultas.de(TABLA_MEMBRESIAS) == 2, contador_de_consultas.sentencias
    assert contador_de_consultas.de(TABLA_PLANES) == 1, contador_de_consultas.sentencias
    socios = [s for s in contador_de_consultas.sentencias if TABLA_SOCIOS in s]
    assert socios, contador_de_consultas.sentencias
    assert all(TABLA_MEMBRESIAS not in s for s in socios), "JOIN entre esquemas (D22)"


async def test_una_pagina_vacia_no_consulta_membresias_para_decorar(
    session: AsyncSession, padron: Padron, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo():
        pagina = await listar(session, q="nadie-se-llama-asi")
    assert pagina.items == []
    assert contador_de_consultas.de(TABLA_MEMBRESIAS) == 0, contador_de_consultas.sentencias


async def test_sin_ninguna_membresia_none_trae_a_todos_y_los_demas_a_nadie(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> None:
    """Revisión de seguridad del Verde (LOW-2): con el conjunto vacío, `<> ALL('{}')` es
    verdadero y `= ANY('{}')` es falso; ningún caso cae en un `IN ()` inválido."""
    socios = {(await _socio(session, nombre)).id for nombre in ("Uno", "Dos")}
    assert ids(await listar(session, membership_status="none")) == socios
    for estado in ("active", "expiring", "expired", "frozen", "pending_payment"):
        pagina = await listar(session, membership_status=estado)
        assert pagina.items == [] and pagina.total == 0, estado
    assert (await listar(session, plan_id=uuid4())).total == 0

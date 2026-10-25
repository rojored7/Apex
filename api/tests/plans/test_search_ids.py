"""`plans.service.search_ids(session, q)` (S3-B11, D28; condición 3 del impacto).

La pestaña de membresías de la ficha filtra por nombre de plan con esta función nueva: el mismo
pliegue de tildes y mayúsculas de `plans.list` (`core.search.sql_fold` en columna y término,
comodines escapados), planes vivos o dados de baja (una membresía vieja puede ser de un plan que
ya no se vende) y, sin `q` (o en blanco), `set()` sin consultar la base. Una sola sentencia y
nunca toca el bus de criptografía (los planes no tienen campos cifrados).

Planes del escenario (`planes`): "Mensual Básico", "Trimestral", "Clase única", "Plan Niños
100%" y "Mensual" dado de baja (comparte nombre con ninguno vivo: `uq_plans_name_alive` solo
mira los vivos).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.plans import service
from tests.conftest import T0, ContadorDeConsultas
from tests.factories.plans import make_plan


@dataclass(frozen=True)
class Planes:
    basico: UUID
    trimestral: UUID
    unica: UUID
    ninos: UUID
    mensual_baja: UUID


@pytest.fixture
async def planes(session: AsyncSession) -> Planes:
    basico = await make_plan(session, name="Mensual Básico")
    trimestral = await make_plan(session, name="Trimestral", duration_days=90)
    unica = await make_plan(session, name="Clase única", duration_days=1)
    ninos = await make_plan(session, name="Plan Niños 100%")
    baja = await make_plan(session, name="Mensual", deleted_at=T0 - timedelta(days=30))
    return Planes(
        basico=basico.id,
        trimestral=trimestral.id,
        unica=unica.id,
        ninos=ninos.id,
        mensual_baja=baja.id,
    )


@pytest.mark.parametrize(
    ("q", "esperados"),
    [
        ("basico", {"basico"}),
        ("BÁSICO", {"basico"}),
        ("Básico", {"basico"}),
        ("unica", {"unica"}),
        ("ÚNICA", {"unica"}),
        ("ninos", {"ninos"}),
        ("NIÑOS", {"ninos"}),
        ("  trimestral  ", {"trimestral"}),
        ("plan", {"ninos"}),
    ],
    ids=[
        "sin-tilde",
        "mayusculas-con-tilde",
        "con-tilde",
        "u-sin-tilde",
        "u-mayuscula-con-tilde",
        "n-sin-virgulilla",
        "enie-mayuscula",
        "espacios-en-los-extremos",
        "prefijo",
    ],
)
async def test_busca_por_nombre_con_tildes_y_mayusculas_plegadas(
    session: AsyncSession, planes: Planes, q: str, esperados: set[str]
) -> None:
    ids = await service.search_ids(session, q)
    assert ids == {getattr(planes, nombre) for nombre in esperados}


async def test_incluye_los_planes_dados_de_baja(session: AsyncSession, planes: Planes) -> None:
    """Una membresía vieja puede ser de un plan dado de baja: la pestaña lo encuentra igual."""
    assert await service.search_ids(session, "mensual") == {planes.basico, planes.mensual_baja}


async def test_devuelve_un_set_de_uuid(session: AsyncSession, planes: Planes) -> None:
    ids = await service.search_ids(session, "trimestral")
    assert isinstance(ids, set)
    assert all(isinstance(i, UUID) for i in ids)


async def test_sin_coincidencias_da_un_set_vacio(session: AsyncSession, planes: Planes) -> None:
    assert await service.search_ids(session, "Zzyzx") == set()


@pytest.mark.parametrize("q", ["%", "_", "100\\", "a%b"])
async def test_los_comodines_de_like_se_comparan_literales(
    session: AsyncSession, planes: Planes, q: str
) -> None:
    """`%` y `_` no son comodines (patrón escapado y ligado): solo "Plan Niños 100%" tiene `%`."""
    ids = await service.search_ids(session, q)
    assert ids == ({planes.ninos} if q == "%" else set())


@pytest.mark.parametrize("q", [None, "", "   ", "\t "])
async def test_sin_q_da_un_set_vacio_sin_consultar(
    session: AsyncSession,
    planes: Planes,
    contador_de_consultas: ContadorDeConsultas,
    q: str | None,
) -> None:
    with contador_de_consultas.midiendo():
        ids = await service.search_ids(session, q)
    assert ids == set()
    assert contador_de_consultas.sentencias == []


async def test_es_una_sola_sentencia(
    session: AsyncSession, planes: Planes, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo():
        await service.search_ids(session, "mensual")
    assert len(contador_de_consultas.sentencias) == 1
    assert contador_de_consultas.de("plans.plans") == 1


async def test_nunca_toca_el_bus_de_criptografia(session: AsyncSession, planes: Planes) -> None:
    """Sin `decrypt` ni `index`: los planes no tienen campos cifrados (commit: la bitácora
    `crypto_ops` se escribe al confirmar)."""
    contar = text("SELECT count(*) FROM crypto.crypto_ops")
    antes = await session.scalar(contar)
    await service.search_ids(session, "basico")
    await service.search_ids(session, "mensual")
    await session.commit()
    assert await session.scalar(contar) == antes


def test_esta_en_el_contrato_publico_de_planes() -> None:
    assert "search_ids" in service.__all__

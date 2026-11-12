"""Filtro `consent=missing` de la lista y de la exportación de socios (S6-C5, US-151; S6-D20).

Escenario (`escenario`): seis socios con nombres ficticios.
- Con autorización: Ana (membresía activa), Bea (sin membresía).
- Sin autorización y vivos: Caro (activa), Dina (sin membresía), Elsa (inactiva, sin membresía).
- Sin autorización y dado de baja: Eva (no cuenta nunca).

Lo que se prueba:
- `GET /members?consent=missing` devuelve solo vivos con `data_consent_at IS NULL`, sin bajas;
- su `total` es `count_without_consent` y los ids son los de `CONSENT_MISSING_CONDITION` (el
  servicio no reimplementa la condición);
- se combina con `q`, `status` y `membership_status`; pagina con `total` estable; no cambia el
  orden relativo de la lista; sin `consent` la lista no cambia;
- cualquier valor distinto de `missing` da 422 `validation_error` con `field="consent"`;
- `GET /members/export?consent=missing` (admin) exporta solo esas filas.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from app.core.pagination import PageParams
from app.modules.members import service
from app.modules.members.models import Member
from app.modules.members.rules import CONSENT_MISSING_CONDITION
from app.modules.members.schemas import MemberListQuery
from app.modules.plans.models import Plan
from tests.conftest import Cabeceras, CrearUsuario
from tests.core._export_apoyo import parsear, sesion_propia
from tests.factories.memberships import make_membership
from tests.factories.plans import make_plan
from tests.members._apoyo import MEMBERS
from tests.notifications._apoyo_avisos import ANTES, socio

SIN_AUTORIZACION = ["Caro", "Dina", "Elsa"]


@pytest.fixture
async def escenario(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock
) -> dict[str, UUID]:
    plan: Plan = await make_plan(session, name="Mensual")
    ana = await socio(session, nombre="Ana", apellido="Uno", consentido=True)
    bea = await socio(session, nombre="Bea", apellido="Dos", consentido=True)
    caro = await socio(session, nombre="Caro", apellido="Tres", consentido=False)
    dina = await socio(session, nombre="Dina", apellido="Cuatro", consentido=False)
    elsa = await socio(
        session, nombre="Elsa", apellido="Cinco", consentido=False, status="inactive"
    )
    eva = await socio(
        session,
        nombre="Eva",
        apellido="Seis",
        consentido=False,
        deleted_at=ANTES,
        status="inactive",
    )
    await make_membership(session, ana, plan, status="active")
    await make_membership(session, caro, plan, status="active")
    return {
        nombre: miembro.id
        for nombre, miembro in {
            "ana": ana,
            "bea": bea,
            "caro": caro,
            "dina": dina,
            "elsa": elsa,
            "eva": eva,
        }.items()
    }


async def _lista(
    cliente: AsyncClient, cabeceras: Cabeceras, quien: Any, **params: Any
) -> dict[str, Any]:
    r = await cliente.get(MEMBERS, params=params, headers=cabeceras(quien))
    assert r.status_code == 200, r.text
    cuerpo: dict[str, Any] = r.json()
    return cuerpo


def _nombres(cuerpo: dict[str, Any]) -> list[str]:
    return [fila["first_name"] for fila in cuerpo["items"]]


async def test_la_lista_trae_solo_vivos_sin_autorizacion(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
) -> None:
    coach = await usuario_real("coach")
    cuerpo = await _lista(app_http, cabeceras, coach, consent="missing", limit=200)
    assert sorted(_nombres(cuerpo)) == SIN_AUTORIZACION
    assert "Eva" not in _nombres(cuerpo)


async def test_el_total_coincide_con_count_without_consent(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    cuerpo = await _lista(app_http, cabeceras, admin, consent="missing")
    assert cuerpo["total"] == await service.count_without_consent(session) == 3


async def test_los_ids_son_los_de_consent_missing_condition_sin_bajas(
    session: AsyncSession, escenario: dict[str, UUID]
) -> None:
    esperados = set(
        await session.scalars(
            select(Member.id).where(CONSENT_MISSING_CONDITION, Member.deleted_at.is_(None))
        )
    )
    pagina = await service.list(
        session, MemberListQuery(consent="missing"), PageParams(limit=200, offset=0)
    )
    assert {fila.id for fila in pagina.items} == esperados
    assert pagina.total == len(esperados) == 3


async def test_sin_consent_la_lista_no_cambia(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
) -> None:
    coach = await usuario_real("coach")
    cuerpo = await _lista(app_http, cabeceras, coach, limit=200)
    assert sorted(_nombres(cuerpo)) == ["Ana", "Bea", "Caro", "Dina", "Elsa"]
    assert cuerpo["total"] == 5


async def test_el_filtro_no_altera_el_orden_relativo_de_la_lista(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
) -> None:
    coach = await usuario_real("coach")
    completa = _nombres(await _lista(app_http, cabeceras, coach, limit=200))
    filtrada = _nombres(await _lista(app_http, cabeceras, coach, consent="missing", limit=200))
    assert filtrada == [n for n in completa if n in SIN_AUTORIZACION]


async def test_se_combina_con_q(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
) -> None:
    coach = await usuario_real("coach")
    cuerpo = await _lista(app_http, cabeceras, coach, consent="missing", q="Dina")
    assert _nombres(cuerpo) == ["Dina"] and cuerpo["total"] == 1
    cuerpo = await _lista(app_http, cabeceras, coach, consent="missing", q="Ana")
    assert cuerpo["items"] == [] and cuerpo["total"] == 0  # Ana tiene autorización


async def test_se_combina_con_status(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
) -> None:
    coach = await usuario_real("coach")
    cuerpo = await _lista(app_http, cabeceras, coach, consent="missing", status="inactive")
    assert _nombres(cuerpo) == ["Elsa"] and cuerpo["total"] == 1
    cuerpo = await _lista(app_http, cabeceras, coach, consent="missing", status="active")
    assert sorted(_nombres(cuerpo)) == ["Caro", "Dina"]


async def test_se_combina_con_membership_status(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
) -> None:
    coach = await usuario_real("coach")
    cuerpo = await _lista(app_http, cabeceras, coach, consent="missing", membership_status="active")
    assert _nombres(cuerpo) == ["Caro"] and cuerpo["total"] == 1
    cuerpo = await _lista(app_http, cabeceras, coach, consent="missing", membership_status="none")
    assert sorted(_nombres(cuerpo)) == ["Dina", "Elsa"] and cuerpo["total"] == 2


async def test_pagina_con_total_estable(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
) -> None:
    coach = await usuario_real("coach")
    primera = await _lista(app_http, cabeceras, coach, consent="missing", limit=2, offset=0)
    segunda = await _lista(app_http, cabeceras, coach, consent="missing", limit=2, offset=2)
    assert primera["total"] == segunda["total"] == 3
    assert len(primera["items"]) == 2 and len(segunda["items"]) == 1
    juntos = _nombres(primera) + _nombres(segunda)
    assert sorted(juntos) == SIN_AUTORIZACION and len(set(juntos)) == 3


@pytest.mark.parametrize("valor", ["x", "present", "MISSING", "true", ""])
async def test_un_valor_distinto_de_missing_da_422(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    valor: str,
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.get(MEMBERS, params={"consent": valor}, headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", "consent")


async def test_la_exportacion_trae_solo_los_socios_sin_autorizacion(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    with sesion_propia(session):
        r = await app_http.get(
            f"{MEMBERS}/export", params={"consent": "missing"}, headers=cabeceras(admin)
        )
    assert r.status_code == 200, r.text
    _, filas = parsear(r.content)
    assert len(filas) == 3
    assert sorted(f[0] for f in filas) == SIN_AUTORIZACION


async def test_la_exportacion_rechaza_un_valor_distinto_de_missing(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    escenario: dict[str, UUID],
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.get(f"{MEMBERS}/export", params={"consent": "x"}, headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "consent"


def test_la_condicion_de_sin_autorizacion_tiene_una_sola_definicion() -> None:
    """Revisión de seguridad de C5: `data_consent_at IS NULL` vive solo en `rules.py`
    (`CONSENT_MISSING_CONDITION`); `service.py` y `exports.py` la importan, nunca la repiten."""
    from pathlib import Path

    import app.modules.members.service as service_mod

    carpeta = Path(service_mod.__file__).parent
    for nombre in ("service.py", "exports.py", "queries.py", "detail.py"):
        archivo = carpeta / nombre
        if archivo.exists():
            assert "data_consent_at.is_(None)" not in archivo.read_text(encoding="utf-8"), nombre
    assert "data_consent_at.is_(None)" in (carpeta / "rules.py").read_text(encoding="utf-8")

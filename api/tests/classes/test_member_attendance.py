"""`GET /members/{id}/attendance` (S7-R1, US-162; S7-D15, N-20). Rojo R1.

Admin y coach; el socio recibe 403. Paginada, la más reciente primero, solo asistencias vivas del
socio pedido. Un socio dado de baja se ve; uno inexistente da 404 `member_not_found`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.modules.classes import service
from app.modules.members.exceptions import MemberNotFound
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.classes import make_attendance, make_session
from tests.factories.members import make_member, make_members, unique_document

BASE = datetime(2026, 10, 12, 11, 0, tzinfo=UTC)
CAMPOS_CIFRADOS = {"document", "phone", "email", "birth_date", "emergency_contact"}

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


def _ruta(member_id: object) -> str:
    return f"/api/v1/members/{member_id}/attendance"


async def test_solo_las_del_socio_vivas_y_recientes_primero(session: AsyncSession) -> None:
    uno, otro = await make_members(session, 2)
    for dia in range(3):
        clase = await make_session(session, starts_at=BASE + timedelta(days=dia))
        await make_attendance(session, clase, uno.id)
    ajena = await make_session(session, starts_at=BASE + timedelta(days=5))
    await make_attendance(session, ajena, otro.id)
    quitada = await make_session(session, starts_at=BASE + timedelta(days=6))
    await make_attendance(session, quitada, uno.id, removed_at=BASE, removed_reason="x")
    pagina = await service.member_attendance(session, uno.id, PageParams())
    assert pagina.total == 3 and len(pagina.items) == 3
    horas = [i.checked_in_at for i in pagina.items]
    assert horas == sorted(horas, reverse=True)
    assert {i.member_id for i in pagina.items} == {uno.id}
    assert pagina.items[0].first_name == uno.first_name


async def test_pagina(session: AsyncSession) -> None:
    (socio,) = await make_members(session, 1)
    for dia in range(3):
        clase = await make_session(session, starts_at=BASE + timedelta(days=dia))
        await make_attendance(session, clase, socio.id)
    pagina = await service.member_attendance(session, socio.id, PageParams(limit=2, offset=2))
    assert (pagina.total, len(pagina.items), pagina.limit, pagina.offset) == (3, 1, 2, 2)


async def test_baja_visible(session: AsyncSession) -> None:
    baja = await make_member(
        session,
        document=unique_document(),
        phone=None,
        email=None,
        deleted_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    clase = await make_session(session, starts_at=BASE)
    await make_attendance(session, clase, baja.id)
    pagina = await service.member_attendance(session, baja.id, PageParams())
    assert pagina.total == 1


async def test_404_inexistente(session: AsyncSession) -> None:
    with pytest.raises(MemberNotFound):
        await service.member_attendance(session, uuid4(), PageParams())


async def test_sin_asistencias_pagina_vacia(session: AsyncSession) -> None:
    (socio,) = await make_members(session, 1)
    pagina = await service.member_attendance(session, socio.id, PageParams())
    assert (pagina.total, pagina.items) == (0, [])


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_http_staff_200_sin_cifrados(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    rol: str,
) -> None:
    usuario = await usuario_real(rol)
    (socio,) = await make_members(session, 1)
    clase = await make_session(session, starts_at=BASE)
    await make_attendance(session, clase, socio.id, flags=["expired"])
    r = await app_http.get(_ruta(socio.id), headers=cabeceras(usuario))
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    cuerpo = r.json()
    assert cuerpo["total"] == 1 and cuerpo["limit"] == 25
    fila = cuerpo["items"][0]
    assert CAMPOS_CIFRADOS.isdisjoint(fila)
    assert fila["flagged"] is True and fila["flags"] == ["expired"]


async def test_http_404_y_roles(
    app_http: AsyncClient,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
) -> None:
    (socio,) = await make_members(session, 1)
    socio_id = socio.id
    coach = await usuario_real("coach")
    r = await app_http.get(_ruta(uuid4()), headers=cabeceras(coach))
    assert (r.status_code, r.json()["error"]["code"]) == (404, "member_not_found")
    assert (await app_http.get(_ruta(socio_id))).status_code == 401
    miembro = await usuario_real("member")
    assert (await app_http.get(_ruta(socio_id), headers=cabeceras(miembro))).status_code == 403
    r = await app_http.get(_ruta(socio_id), params={"limit": 0}, headers=cabeceras(coach))
    assert r.status_code == 422


async def test_acepta_q_como_toda_lista(session: AsyncSession) -> None:
    """Regla de datos 6: la lista acepta `q`; con otro nombre no devuelve nada."""
    (socio,) = await make_members(session, 1)
    clase = await make_session(session, starts_at=BASE)
    await make_attendance(session, clase, socio.id)
    assert (await service.member_attendance(session, socio.id, PageParams(), q="Lucía")).total == 1
    assert (await service.member_attendance(session, socio.id, PageParams(), q="Zzzzz")).total == 0

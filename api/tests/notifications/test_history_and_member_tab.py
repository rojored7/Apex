"""Historial y pestaña del socio (S5-B7, US-130; S5-D92, N-20). # Rojo B7

`service.list(session, filters, page)`: todos los avisos (cualquier estado) con filtros `status`,
`channel`, `rule_id`, `from_date`/`to_date` (sobre `target_date`, extremos incluidos) y `q` por
nombre del socio (`members.service.search_ids`, también dados de baja); orden `target_date`
descendente y luego `id`; `member_name` de `members.service.names_for`.

`service.get(session, id)`: un aviso o `NotificationNotFound` (404).

`service.list_for_member(session, member_id, page)`: la pestaña del socio, `target_date`
descendente; incluye a los socios dados de baja (N-20); un socio inexistente da `MemberNotFound`
(404). Ninguna salida lleva teléfono ni correo.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.modules.members.exceptions import MemberNotFound
from app.modules.notifications import service
from app.modules.notifications.exceptions import NotificationNotFound
from app.modules.notifications.schemas import NotificationFilters, NotificationOut
from tests.factories.notifications import make_notification, make_rule, make_template
from tests.notifications._apoyo_avisos import ANTES, HOY, socio

pytestmark = pytest.mark.usefixtures("listo")
PAGINA = PageParams(limit=50, offset=0)


def _dia(atras: int) -> Any:
    return HOY - timedelta(days=atras)


async def _historial(session: AsyncSession, **filtros: Any) -> list[NotificationOut]:
    pagina = await service.list(session, NotificationFilters(**filtros), PAGINA)
    return list(pagina.items)


async def test_sin_filtros_trae_todos_los_estados_de_mas_nuevo_a_mas_viejo(
    session: AsyncSession,
) -> None:
    regla = await make_rule(session)
    creados = [
        await make_notification(session, regla, status=estado, target_date=_dia(atras))
        for atras, estado in enumerate(["pending", "sent", "failed", "skipped"])
    ]

    pagina = await service.list(session, NotificationFilters(), PAGINA)

    assert [a.id for a in pagina.items] == [a.id for a in creados]
    assert [a.target_date for a in pagina.items] == sorted(
        (a.target_date for a in pagina.items), reverse=True
    )
    assert pagina.total == 4


@pytest.mark.parametrize("estado", ["pending", "sent", "failed", "skipped"])
async def test_filtra_por_estado(session: AsyncSession, estado: str) -> None:
    regla = await make_rule(session)
    for s in ("pending", "sent", "failed", "skipped"):
        await make_notification(session, regla, status=s)

    filas = await _historial(session, status=estado)

    assert [a.status for a in filas] == [estado]


async def test_filtra_por_canal_y_por_regla(session: AsyncSession) -> None:
    plantilla = await make_template(session)
    correo = await make_rule(session, plantilla, channel="email", name="Correo", offset_days=-3)
    wa = await make_rule(session, plantilla, name="WA", offset_days=0)
    de_correo = await make_notification(session, correo)
    de_wa = await make_notification(session, wa)

    assert [a.id for a in await _historial(session, channel="email")] == [de_correo.id]
    assert [a.id for a in await _historial(session, channel="whatsapp_link")] == [de_wa.id]
    assert [a.id for a in await _historial(session, rule_id=wa.id)] == [de_wa.id]
    assert await _historial(session, rule_id=uuid4()) == []


async def test_filtra_por_rango_de_fechas_con_los_extremos_incluidos(
    session: AsyncSession,
) -> None:
    regla = await make_rule(session)
    por_dia = {
        atras: await make_notification(session, regla, target_date=_dia(atras))
        for atras in (0, 3, 5, 9)
    }

    dentro = await _historial(session, from_date=_dia(5), to_date=_dia(3))
    desde = await _historial(session, from_date=_dia(3))
    hasta = await _historial(session, to_date=_dia(5))

    assert {a.id for a in dentro} == {por_dia[3].id, por_dia[5].id}
    assert {a.id for a in desde} == {por_dia[0].id, por_dia[3].id}
    assert {a.id for a in hasta} == {por_dia[5].id, por_dia[9].id}


async def test_q_busca_por_nombre_del_socio_incluso_dado_de_baja(session: AsyncSession) -> None:
    regla = await make_rule(session)
    lucia = await socio(session, nombre="Lucía", apellido="Gómez")
    de_baja = await socio(session, nombre="Lucero", apellido="Peña", deleted_at=ANTES)
    otra = await socio(session, nombre="Marta", apellido="Ríos")
    for miembro in (lucia, de_baja, otra):
        await make_notification(session, regla, member_id=miembro.id)

    por_prefijo = await _historial(session, q="luc")
    por_apellido = await _historial(session, q="PENA")

    assert {a.member_id for a in por_prefijo} == {lucia.id, de_baja.id}
    assert [a.member_id for a in por_apellido] == [de_baja.id]
    assert await _historial(session, q="zzz") == []


async def test_los_filtros_se_combinan(session: AsyncSession) -> None:
    regla = await make_rule(session)
    ana = await socio(session, nombre="Ana")
    objetivo = await make_notification(
        session, regla, member_id=ana.id, status="failed", target_date=_dia(2)
    )
    await make_notification(session, regla, member_id=ana.id, status="sent", target_date=_dia(2))
    await make_notification(session, regla, status="failed", target_date=_dia(2))
    await make_notification(session, regla, member_id=ana.id, status="failed", target_date=_dia(8))

    filas = await _historial(
        session, q="ana", status="failed", from_date=_dia(3), to_date=_dia(1), rule_id=regla.id
    )

    assert [a.id for a in filas] == [objetivo.id]


async def test_el_historial_pagina(session: AsyncSession) -> None:
    regla = await make_rule(session)
    for atras in range(5):
        await make_notification(session, regla, target_date=_dia(atras))

    primera = await service.list(session, NotificationFilters(), PageParams(limit=2, offset=0))
    segunda = await service.list(session, NotificationFilters(), PageParams(limit=2, offset=2))

    assert (primera.total, segunda.total) == (5, 5)
    assert [a.target_date for a in primera.items] == [_dia(0), _dia(1)]
    assert [a.target_date for a in segunda.items] == [_dia(2), _dia(3)]


async def test_get_devuelve_el_aviso_con_el_nombre_y_sin_contacto(session: AsyncSession) -> None:
    lucia = await socio(session, nombre="Lucía", apellido="Gómez", phone="3007654321")
    aviso = await make_notification(session, await make_rule(session), member_id=lucia.id)

    salida = await service.get(session, aviso.id)

    assert isinstance(salida, NotificationOut)
    assert (salida.id, salida.member_id, salida.member_name) == (aviso.id, lucia.id, "Lucía Gómez")
    assert "3007654321" not in salida.model_dump_json()


async def test_get_de_un_aviso_inexistente_es_404(session: AsyncSession) -> None:
    with pytest.raises(NotificationNotFound) as error:
        await service.get(session, uuid4())
    assert (error.value.status, error.value.code) == (404, "notification_not_found")


# Pestaña del socio ------------------------------------------------------------------------------


async def test_la_pestana_trae_solo_los_avisos_del_socio_del_mas_nuevo_al_mas_viejo(
    session: AsyncSession,
) -> None:
    regla = await make_rule(session)
    ana, otra = await socio(session, nombre="Ana"), await socio(session, nombre="Otra")
    viejo = await make_notification(session, regla, member_id=ana.id, target_date=_dia(9))
    nuevo = await make_notification(session, regla, member_id=ana.id, target_date=_dia(1))
    await make_notification(session, regla, member_id=otra.id)

    pagina = await service.list_for_member(session, ana.id, PAGINA)

    assert [a.id for a in pagina.items] == [nuevo.id, viejo.id] and pagina.total == 2
    assert {a.member_name for a in pagina.items} == {"Ana Gómez"}


async def test_la_pestana_incluye_a_un_socio_dado_de_baja(session: AsyncSession) -> None:
    baja = await socio(session, deleted_at=ANTES)
    aviso = await make_notification(session, await make_rule(session), member_id=baja.id)

    pagina = await service.list_for_member(session, baja.id, PAGINA)

    assert [a.id for a in pagina.items] == [aviso.id]


async def test_la_pestana_de_un_socio_sin_avisos_esta_vacia_y_pagina(session: AsyncSession) -> None:
    sin = await socio(session)
    regla = await make_rule(session)
    ana = await socio(session, nombre="Ana")
    for atras in range(3):
        await make_notification(session, regla, member_id=ana.id, target_date=_dia(atras))

    vacia = await service.list_for_member(session, sin.id, PAGINA)
    segunda = await service.list_for_member(session, ana.id, PageParams(limit=2, offset=2))

    assert (vacia.items, vacia.total) == ([], 0)
    assert (len(segunda.items), segunda.total) == (1, 3)


async def test_la_pestana_de_un_socio_inexistente_es_404(session: AsyncSession) -> None:
    with pytest.raises(MemberNotFound) as error:
        await service.list_for_member(session, uuid4(), PAGINA)
    assert (error.value.status, error.value.code) == (404, "member_not_found")


async def test_un_aviso_cuyo_socio_ya_no_existe_se_lista_con_el_nombre_vacio(
    session: AsyncSession,
) -> None:
    """No hay FK hacia `members`: si el socio desapareciera, el aviso sigue visible y la lista no
    falla (`member_name == ""`)."""
    aviso = await make_notification(session, await make_rule(session))

    salida = await service.get(session, aviso.id)

    assert salida.member_name == ""

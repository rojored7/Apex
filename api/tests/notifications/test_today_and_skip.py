"""`today_list`, `today_count` y `skip` (S5-B7, US-128, US-129; S5-D92, RN-14). # Rojo B7

Por avisar hoy:
- incluye los `pending` de hoy y de los 15 días anteriores (S5-D219: un WhatsApp no enviado ayer
  sigue por avisar) y los `failed` de hoy y de días anteriores; excluye los `sent`, los `skipped`
  y los `pending` más viejos que la ventana (los cubre el historial);
- `today_count` es el `total` de `today_list` sin filtro; `q` busca por nombre del socio (sin
  tildes ni mayúsculas, vía `members.service.search_ids`); pagina con `limit`/`offset`;
- cada fila lleva `member_name` (nombre y apellido) y nunca un teléfono ni un correo.

Omitir (`skip(session, id, reason, by)`):
- solo `pending` y `failed`; el motivo se guarda recortado; `sent`/`skipped` dan 409
  `notification_closed` sin cambiar la fila; un id inexistente, 404 `notification_not_found`;
- deja un `update` en `audit_log` (actor `by`, socio como sujeto) y emite `NotificationSkipped`
  con ids y canal, SIN el motivo.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.modules.notifications import service
from app.modules.notifications.exceptions import NotificationClosed, NotificationNotFound
from app.modules.notifications.schemas import NotificationOut
from tests.conftest import CrearUsuario
from tests.factories.notifications import make_notification, make_rule
from tests.notifications._apoyo import en_peticion
from tests.notifications._apoyo_avisos import HOY, eventos_de, socio

pytestmark = pytest.mark.usefixtures("listo")
PAGINA = PageParams(limit=50, offset=0)


async def _aviso(session: AsyncSession, regla: Any, miembro: Any = None, **cambios: Any) -> Any:
    miembro = miembro or await socio(session)
    return await make_notification(session, regla, member_id=miembro.id, **cambios)


async def _estado(session: AsyncSession, notification_id: Any) -> dict[str, Any]:
    consulta = text("SELECT * FROM notifications.notifications WHERE id = :id")
    return dict((await session.execute(consulta, {"id": notification_id})).mappings().one())


# Por avisar hoy ---------------------------------------------------------------------------------


async def test_hoy_incluye_pendientes_y_fallidos_de_hoy_y_fallidos_anteriores(
    session: AsyncSession,
) -> None:
    regla = await make_rule(session)
    ayer, hace_diez = HOY - timedelta(days=1), HOY - timedelta(days=10)
    incluidos = [
        await _aviso(session, regla, status="pending", target_date=ayer),
        await _aviso(session, regla, status="pending", target_date=HOY),
        await _aviso(session, regla, status="failed", target_date=HOY, attempts=3),
        await _aviso(session, regla, status="failed", target_date=ayer, attempts=3),
        await _aviso(session, regla, status="failed", target_date=hace_diez, attempts=3),
    ]
    await _aviso(session, regla, status="sent", target_date=HOY)
    await _aviso(session, regla, status="skipped", target_date=HOY)
    await _aviso(session, regla, status="pending", target_date=HOY - timedelta(days=16))

    pagina = await service.today_list(session, HOY, PAGINA, None)

    assert {a.id for a in pagina.items} == {a.id for a in incluidos}
    assert pagina.total == 5 and (pagina.limit, pagina.offset) == (50, 0)
    assert await service.today_count(session, HOY) == 5


async def test_un_aviso_de_manana_no_aparece_hoy(session: AsyncSession) -> None:
    regla = await make_rule(session)
    await _aviso(session, regla, status="pending", target_date=HOY + timedelta(days=1))
    assert (await service.today_list(session, HOY, PAGINA, None)).items == []
    assert await service.today_count(session, HOY) == 0


async def test_cada_fila_trae_el_nombre_del_socio_y_ningun_dato_de_contacto(
    session: AsyncSession,
) -> None:
    regla = await make_rule(session)
    lucia = await socio(session, nombre="Lucía", apellido="Gómez", phone="3007654321")
    aviso = await _aviso(session, regla, lucia)

    [fila] = (await service.today_list(session, HOY, PAGINA, None)).items

    assert isinstance(fila, NotificationOut)
    assert (fila.id, fila.member_id, fila.member_name) == (aviso.id, lucia.id, "Lucía Gómez")
    assert (fila.status, fila.channel, fila.target_date) == ("pending", "whatsapp_link", HOY)
    volcado = fila.model_dump_json()
    assert "3007654321" not in volcado and "@" not in volcado


async def test_q_filtra_por_nombre_sin_tildes_ni_mayusculas(session: AsyncSession) -> None:
    regla = await make_rule(session)
    lucia = await socio(session, nombre="Lucía", apellido="Gómez")
    otra = await socio(session, nombre="Marta", apellido="Ríos")
    await _aviso(session, regla, lucia)
    await _aviso(session, regla, otra)

    por_nombre = await service.today_list(session, HOY, PAGINA, "LUCIA")
    por_apellido = await service.today_list(session, HOY, PAGINA, "rios")
    ninguno = await service.today_list(session, HOY, PAGINA, "zzz")

    assert [a.member_id for a in por_nombre.items] == [lucia.id]
    assert [a.member_id for a in por_apellido.items] == [otra.id]
    assert (ninguno.items, ninguno.total) == ([], 0)


async def test_hoy_pagina_con_limit_y_offset(session: AsyncSession) -> None:
    regla = await make_rule(session)
    for _ in range(5):
        await _aviso(session, regla)

    primera = await service.today_list(session, HOY, PageParams(limit=2, offset=0), None)
    ultima = await service.today_list(session, HOY, PageParams(limit=2, offset=4), None)
    todas = await service.today_list(session, HOY, PageParams(limit=50, offset=0), None)

    assert (len(primera.items), primera.total) == (2, 5)
    assert (len(ultima.items), ultima.total) == (1, 5)
    ids = [a.id for a in primera.items] + [a.id for a in ultima.items]
    assert len(set(ids)) == 3 and set(ids) <= {a.id for a in todas.items}


# Omitir ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("estado", ["pending", "failed"])
async def test_omitir_un_aviso_pendiente_o_fallido_lo_deja_skipped_con_su_motivo(
    session: AsyncSession, usuario_real: CrearUsuario, estado: str
) -> None:
    admin = await usuario_real("admin")
    regla = await make_rule(session)
    aviso = await _aviso(session, regla, status=estado)

    salida = await en_peticion(
        session,
        admin.id,
        lambda: service.skip(session, aviso.id, "  El socio avisó que no viene  ", admin.id),
    )

    assert isinstance(salida, NotificationOut)
    assert (salida.status, salida.skip_reason) == ("skipped", "El socio avisó que no viene")
    fila = await _estado(session, aviso.id)
    assert fila["status"] == "skipped" and fila["skip_reason"] == "El socio avisó que no viene"
    assert fila["sent_at"] is None and fila["sent_by"] is None


@pytest.mark.parametrize("estado", ["sent", "skipped"])
async def test_un_aviso_cerrado_no_se_omite_y_no_cambia(
    session: AsyncSession, usuario_real: CrearUsuario, estado: str
) -> None:
    admin = await usuario_real("admin")
    regla = await make_rule(session)
    aviso = await _aviso(session, regla, status=estado)
    antes = await _estado(session, aviso.id)

    with pytest.raises(NotificationClosed) as error:
        await en_peticion(
            session, admin.id, lambda: service.skip(session, aviso.id, "Otro motivo", admin.id)
        )

    assert (error.value.status, error.value.code) == (409, "notification_closed")
    assert await _estado(session, aviso.id) == antes


async def test_omitir_dos_veces_conserva_el_primer_motivo(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    aviso = await _aviso(session, await make_rule(session))
    await en_peticion(
        session, admin.id, lambda: service.skip(session, aviso.id, "Primer motivo", admin.id)
    )

    with pytest.raises(NotificationClosed):
        await en_peticion(
            session, admin.id, lambda: service.skip(session, aviso.id, "Segundo motivo", admin.id)
        )

    assert (await _estado(session, aviso.id))["skip_reason"] == "Primer motivo"


async def test_omitir_un_aviso_inexistente_es_404(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    with pytest.raises(NotificationNotFound) as error:
        await service.skip(session, uuid4(), "No existe", admin.id)
    assert (error.value.status, error.value.code) == (404, "notification_not_found")


async def test_omitir_deja_un_update_auditado_a_nombre_de_quien_omite(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    miembro = await socio(session)
    aviso = await _aviso(session, await make_rule(session), miembro)

    await en_peticion(
        session, admin.id, lambda: service.skip(session, aviso.id, "Motivo auditado", admin.id)
    )

    consulta = text(
        "SELECT action, user_id, subject_member_id FROM audit.audit_log "
        "WHERE table_name = 'notifications.notifications' AND record_id = :id AND action = 'update'"
    )
    [fila] = (await session.execute(consulta, {"id": aviso.id})).mappings().all()
    assert (fila["user_id"], fila["subject_member_id"]) == (admin.id, miembro.id)


async def test_el_evento_de_omitir_lleva_ids_y_canal_pero_no_el_motivo(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    miembro = await socio(session)
    aviso = await _aviso(session, await make_rule(session), miembro)
    capturados = eventos_de(service.NotificationSkipped)
    motivo = "Motivo privado del socio"

    await en_peticion(session, admin.id, lambda: service.skip(session, aviso.id, motivo, admin.id))

    [evento] = capturados.vistos
    assert (evento.notification_id, evento.member_id, evento.channel) == (
        aviso.id,
        miembro.id,
        "whatsapp_link",
    )
    assert motivo not in repr(evento)
    assert "reason" not in {campo for campo in type(evento).__dataclass_fields__}


async def test_un_omitido_deja_de_aparecer_en_por_avisar_hoy(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    aviso = await _aviso(session, await make_rule(session))
    assert await service.today_count(session, HOY) == 1

    await en_peticion(
        session, admin.id, lambda: service.skip(session, aviso.id, "Ya no aplica", admin.id)
    )

    assert await service.today_count(session, HOY) == 0


async def test_hoy_no_incluye_avisos_de_socios_dados_de_baja_pero_el_historial_si(
    session: AsyncSession,
) -> None:
    """S5-D225: nadie avisa a quien se dio de baja; historial y pestaña lo conservan (N-20)."""
    from app.modules.notifications.schemas import NotificationFilters
    from tests.notifications._apoyo_avisos import ANTES

    regla = await make_rule(session)
    vivo = await socio(session, nombre="Vivo")
    baja = await socio(session, nombre="Baja", deleted_at=ANTES)
    aviso_vivo = await _aviso(session, regla, vivo)
    aviso_baja = await _aviso(session, regla, baja)

    hoy = await service.today_list(session, HOY, PAGINA, None)
    historial = await service.list(session, NotificationFilters(), PAGINA)
    pestana = await service.list_for_member(session, baja.id, PAGINA)

    assert [a.id for a in hoy.items] == [aviso_vivo.id] and hoy.total == 1
    assert await service.today_count(session, HOY) == 1
    assert {a.id for a in historial.items} == {aviso_vivo.id, aviso_baja.id}
    assert [a.id for a in pestana.items] == [aviso_baja.id]

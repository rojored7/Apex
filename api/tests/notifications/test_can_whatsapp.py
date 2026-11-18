"""`NotificationOut.can_whatsapp` (S9-X1, S9-D22, S9-D36 L-5). Rojo X1.

Verdadero solo si se cumplen las cinco condiciones REALES de `service.wa_link`:
(1) el aviso no está `skipped`; (2) su canal es `whatsapp_link`; (3) `channels.whatsapp.enabled`;
(4) el socio existe, no está dado de baja y tiene autorización de datos; (5) tiene teléfono.
No existe ningún opt-in en `wa_link`: no se prueba.

- Una prueba por condición: falso; con las cinco cumplidas: verdadero.
- Coherencia: para cada caso falso, `wa_link` responde el error que corresponde; con verdadero no
  responde ninguno de esos cinco.
- `get`, `list`, `today_list`, `list_for_member` y `skip` traen el campo correcto.
- Una sola llamada a `members.service.whatsapp_ready` y una sola lectura de la configuración de
  canales por página.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.modules.members import service as members_service
from app.modules.members.exceptions import MemberNotContactable
from app.modules.notifications import service
from app.modules.notifications.exceptions import (
    ChannelDisabled,
    MemberWithoutPhone,
    NotificationClosed,
    WrongChannel,
)
from app.modules.notifications.schemas import NotificationFilters
from app.modules.settings import service as settings_service
from tests.conftest import CrearUsuario
from tests.factories.notifications import make_notification, make_rule
from tests.notifications._apoyo import en_peticion
from tests.notifications._apoyo_avisos import ANTES, HOY, TELEFONO, ajustar_canales, socio

pytestmark = pytest.mark.usefixtures("listo")
PAGINA = PageParams(limit=50, offset=0)


async def _escenario(
    session: AsyncSession,
    *,
    estado: str = "pending",
    canal: str = "whatsapp_link",
    habilitado: bool = True,
    regla: Any = None,
    telefono: str | None = TELEFONO,
    **del_socio: Any,
) -> tuple[Any, Any]:
    await ajustar_canales(session, whatsapp=habilitado, email=True)
    miembro = await socio(session, phone=telefono, **del_socio)
    regla = regla or await make_rule(session, channel=canal)
    aviso = await make_notification(session, regla, member_id=miembro.id, status=estado)
    return miembro, aviso


# Una prueba por condición -----------------------------------------------------------------------


async def test_con_las_cinco_condiciones_es_verdadero(session: AsyncSession) -> None:
    _, aviso = await _escenario(session)

    assert (await service.get(session, aviso.id)).can_whatsapp is True


async def test_un_aviso_omitido_es_falso(session: AsyncSession) -> None:
    _, aviso = await _escenario(session, estado="skipped")

    assert (await service.get(session, aviso.id)).can_whatsapp is False


async def test_un_aviso_de_correo_es_falso(session: AsyncSession) -> None:
    _, aviso = await _escenario(session, canal="email")

    assert (await service.get(session, aviso.id)).can_whatsapp is False


async def test_con_el_canal_whatsapp_apagado_es_falso(session: AsyncSession) -> None:
    _, aviso = await _escenario(session, habilitado=False)

    assert (await service.get(session, aviso.id)).can_whatsapp is False


async def test_un_socio_sin_autorizacion_es_falso(session: AsyncSession) -> None:
    _, aviso = await _escenario(session, consentido=False)

    assert (await service.get(session, aviso.id)).can_whatsapp is False


async def test_un_socio_dado_de_baja_es_falso(session: AsyncSession) -> None:
    _, aviso = await _escenario(session, deleted_at=ANTES, status="inactive")

    assert (await service.get(session, aviso.id)).can_whatsapp is False


async def test_un_socio_sin_telefono_es_falso(session: AsyncSession) -> None:
    _, aviso = await _escenario(session, telefono=None)

    assert (await service.get(session, aviso.id)).can_whatsapp is False


# Coherencia con wa_link -------------------------------------------------------------------------

CASOS_FALSOS = [
    pytest.param({"estado": "skipped"}, NotificationClosed, "notification_closed", id="skipped"),
    pytest.param({"canal": "email"}, WrongChannel, "wrong_channel", id="canal"),
    pytest.param({"habilitado": False}, ChannelDisabled, "channel_disabled", id="apagado"),
    pytest.param({"consentido": False}, MemberNotContactable, None, id="sin_autorizacion"),
    pytest.param(
        {"deleted_at": ANTES, "status": "inactive"}, MemberNotContactable, None, id="baja"
    ),
    pytest.param({"telefono": None}, MemberWithoutPhone, "member_without_phone", id="sin_telefono"),
]


@pytest.mark.parametrize(("cambios", "excepcion", "codigo"), CASOS_FALSOS)
async def test_cada_caso_falso_coincide_con_el_error_de_wa_link(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    cambios: dict[str, Any],
    excepcion: type[Exception],
    codigo: str | None,
) -> None:
    admin = await usuario_real("admin")
    _, aviso = await _escenario(session, **cambios)
    assert (await service.get(session, aviso.id)).can_whatsapp is False

    with pytest.raises(excepcion) as error:
        await en_peticion(session, admin.id, lambda: service.wa_link(session, aviso.id, admin.id))

    if codigo is not None:
        assert getattr(error.value, "code", None) == codigo


async def test_con_verdadero_wa_link_no_responde_ninguno_de_los_cinco_errores(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    _, aviso = await _escenario(session)
    assert (await service.get(session, aviso.id)).can_whatsapp is True

    salida = await en_peticion(
        session, admin.id, lambda: service.wa_link(session, aviso.id, admin.id)
    )

    assert salida.url.startswith("https://wa.me/57")


# Todas las lecturas traen el campo --------------------------------------------------------------


async def test_list_trae_el_campo_correcto_por_aviso(session: AsyncSession) -> None:
    regla = await make_rule(session)
    _, bueno = await _escenario(session, regla=regla)
    _, sin_telefono = await _escenario(session, telefono=None, regla=regla)

    pagina = await service.list_(session, NotificationFilters(), PAGINA)

    assert {f.id: f.can_whatsapp for f in pagina.items} == {bueno.id: True, sin_telefono.id: False}


async def test_today_list_trae_el_campo_correcto_por_aviso(session: AsyncSession) -> None:
    regla = await make_rule(session)
    _, bueno = await _escenario(session, regla=regla)
    _, sin_telefono = await _escenario(session, telefono=None, regla=regla)

    pagina = await service.today_list(session, HOY, PAGINA, None)

    assert {f.id: f.can_whatsapp for f in pagina.items} == {bueno.id: True, sin_telefono.id: False}


async def test_list_for_member_trae_el_campo_correcto(session: AsyncSession) -> None:
    miembro, aviso = await _escenario(session)

    pagina = await service.list_for_member(session, miembro.id, PAGINA)

    assert [(f.id, f.can_whatsapp) for f in pagina.items] == [(aviso.id, True)]


async def test_skip_devuelve_can_whatsapp_falso_porque_ya_esta_omitido(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    _, aviso = await _escenario(session)

    salida = await en_peticion(
        session, admin.id, lambda: service.skip(session, aviso.id, "Motivo", admin.id)
    )

    assert (salida.status, salida.can_whatsapp) == ("skipped", False)


# Una lectura por página -------------------------------------------------------------------------


async def test_una_pagina_llama_una_vez_a_whatsapp_ready_y_lee_la_configuracion_una_vez(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    regla = await make_rule(session)
    await _escenario(session, regla=regla)
    await _escenario(session, telefono=None, regla=regla)
    await _escenario(session, consentido=False, regla=regla)
    llamadas_ready: list[set[Any]] = []
    lecturas_config: list[Any] = []
    real_ready = members_service.whatsapp_ready
    real_get = settings_service.get

    async def espia_ready(sesion: AsyncSession, ids: Any) -> Any:
        pedidos = set(ids)
        llamadas_ready.append(pedidos)
        return await real_ready(sesion, pedidos)

    async def espia_get(sesion: AsyncSession, key: Any) -> Any:
        lecturas_config.append(key)
        return await real_get(sesion, key)

    monkeypatch.setattr(members_service, "whatsapp_ready", espia_ready)
    monkeypatch.setattr(settings_service, "get", espia_get)

    pagina = await service.list_(session, NotificationFilters(), PAGINA)

    assert len(pagina.items) == 3
    assert len(llamadas_ready) == 1 and len(llamadas_ready[0]) == 3
    assert len(lecturas_config) == 1


async def test_en_una_pagina_mezclada_solo_el_aviso_con_las_cinco_condiciones_es_verdadero(
    session: AsyncSession,
) -> None:
    """Cada caso falso rompe UNA sola condicion y cumple las otras cuatro."""
    regla = await make_rule(session)
    _, bueno = await _escenario(session, regla=regla)
    _, omitido = await _escenario(session, regla=regla, estado="skipped")
    _, sin_telefono = await _escenario(session, regla=regla, telefono=None)
    _, sin_autorizacion = await _escenario(session, regla=regla, consentido=False)
    _, baja = await _escenario(session, regla=regla, deleted_at=ANTES, status="inactive")
    regla_correo = await make_rule(
        session, template=None, template_id=regla.template_id, channel="email", name="Correo"
    )
    _, de_correo = await _escenario(session, regla=regla_correo)

    pagina = await service.list_(session, NotificationFilters(), PAGINA)

    esperado = {bueno.id: True}
    esperado.update(
        {a.id: False for a in (omitido, sin_telefono, sin_autorizacion, baja, de_correo)}
    )
    assert {f.id: f.can_whatsapp for f in pagina.items} == esperado


async def test_con_el_canal_apagado_toda_la_pagina_es_falsa(session: AsyncSession) -> None:
    regla = await make_rule(session)
    _, aviso = await _escenario(session, regla=regla, habilitado=False)

    pagina = await service.list_(session, NotificationFilters(), PAGINA)

    assert [(f.id, f.can_whatsapp) for f in pagina.items] == [(aviso.id, False)]

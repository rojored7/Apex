"""Enlace de WhatsApp (S5-B7, US-127; S5-D27, S5-D59, M-9, S5-D216). # Rojo B7

`whatsapp.build_link(phone, text)` (pura): solo dígitos del teléfono, `57` delante si miden 10
(sin duplicarlo si ya empiezan por `57` y miden 12), `https://wa.me/57<digitos>?text=<texto>` con el
texto SIEMPRE por `urllib.parse.quote(text, safe="")`; sin dígitos, `ValueError`.

`service.wa_link(session, id, by) -> WaLinkOut`:
- descifra solo el teléfono con `members.service.contact_for_notification(..., "notify",
  fields={"phone"})` en CADA llamada: una fila `reveal` (`purpose=notify`, `field=phone`) y una
  fila `decrypt` en `crypto_ops` por llamada, nunca el correo;
- marca `sent`, `sent_at` y `sent_by` solo la primera vez (la segunda llamada devuelve la misma URL
  sin cambiar la fila ni emitir `NotificationSent`);
- 404 `notification_not_found`; 409 `notification_closed` si está `skipped`; 409 `wrong_channel`
  si el canal no es `whatsapp_link`; 422 `member_without_phone`; un socio dado de baja o sin
  `data_consent_at` da `MemberNotContactable`; en todos los rechazos la fila no cambia y no queda
  ninguna fila `reveal`/`decrypt`;
- el teléfono aparece solo dentro de la URL: ni en la salida aparte, ni en el evento, ni en logs.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote, unquote
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.modules.members.exceptions import MemberNotContactable
from app.modules.notifications import service, whatsapp
from app.modules.notifications.exceptions import (
    MemberWithoutPhone,
    NotificationClosed,
    NotificationNotFound,
    WrongChannel,
)
from app.modules.notifications.schemas import WaLinkOut
from tests.conftest import CrearUsuario
from tests.factories.notifications import make_notification, make_rule
from tests.members._apoyo import auditoria_del_socio, contar_crypto_ops
from tests.notifications._apoyo import en_peticion
from tests.notifications._apoyo_avisos import (
    ANTES,
    TELEFONO,
    TELEFONO_DIGITOS,
    eventos_de,
    socio,
)

TEXTO_DIFICIL = "Hola Ana & Co #1 100% ñandú\nsegunda línea ?x=1"


# build_link (pura) ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "telefono",
    ["3007654321", "300 765 4321", "(300) 765-4321", "+57 300 765 4321", "57 300 765 4321"],
)
def test_build_link_deja_solo_digitos_y_antepone_57_una_sola_vez(telefono: str) -> None:
    enlace = whatsapp.build_link(telefono, "Hola")
    assert enlace == "https://wa.me/573007654321?text=Hola"


def test_build_link_respeta_un_numero_que_ya_trae_el_prefijo() -> None:
    assert whatsapp.build_link("573007654321", "x") == "https://wa.me/573007654321?text=x"


def test_build_link_codifica_el_texto_con_quote_sin_caracteres_seguros() -> None:
    enlace = whatsapp.build_link(TELEFONO, TEXTO_DIFICIL)
    consulta = enlace.split("?text=", 1)[1]
    assert consulta == quote(TEXTO_DIFICIL, safe="")
    for crudo in (" ", "&", "#", "\n", "?", "="):
        assert crudo not in consulta, repr(crudo)
    assert unquote(consulta) == TEXTO_DIFICIL


def test_build_link_no_deja_pasar_inyeccion_de_parametros_en_el_texto() -> None:
    enlace = whatsapp.build_link(TELEFONO, "ok&phone=999999&text=otro#frag")
    assert enlace.count("?") == 1 and "&" not in enlace and "#" not in enlace


@pytest.mark.parametrize("telefono", ["", "   ", "abc", "+-()"])
def test_build_link_sin_digitos_es_un_error(telefono: str) -> None:
    with pytest.raises(ValueError):
        whatsapp.build_link(telefono, "Hola")


@pytest.mark.parametrize(
    "telefono",
    [
        "300765432",  # 9 dígitos
        "30076543210",  # 11 dígitos
        "123456789012",  # 12 dígitos que no empiezan por 57
        "+1 415 555 2671",  # extranjero
        "00 57 300 765 4321",  # prefijo de marcación internacional
        "6017654321",  # 10 dígitos que no empiezan por 3
        "573007654",  # 57 con muy pocos dígitos
        "5730076543210",  # 13 dígitos
    ],
)
def test_build_link_solo_acepta_celulares_colombianos(telefono: str) -> None:
    """S5-D224: 10 dígitos que empiezan por 3 o 12 que empiezan por 57; lo demás, ValueError."""
    with pytest.raises(ValueError):
        whatsapp.build_link(telefono, "Hola")


# wa_link ----------------------------------------------------------------------------------------


pytestmark = pytest.mark.usefixtures("listo")


async def _preparar(
    session: AsyncSession, *, telefono: str | None = TELEFONO, **cambios: Any
) -> tuple[Any, Any]:
    miembro = await socio(session, phone=telefono, email="lucia@correo.co")
    aviso = await make_notification(
        session,
        await make_rule(session),
        member_id=miembro.id,
        rendered_body=cambios.pop("rendered_body", TEXTO_DIFICIL),
        **cambios,
    )
    return miembro, aviso


async def _fila(session: AsyncSession, notification_id: UUID) -> dict[str, Any]:
    consulta = text("SELECT * FROM notifications.notifications WHERE id = :id")
    return dict((await session.execute(consulta, {"id": notification_id})).mappings().one())


async def _sin_rastro_de_contacto(session: AsyncSession, miembro_id: UUID) -> None:
    assert await auditoria_del_socio(session, miembro_id, "reveal") == []
    assert await contar_crypto_ops(session, miembro_id, "decrypt", "notify") == 0


async def test_devuelve_la_url_y_marca_sent_con_quien_y_cuando(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    _, aviso = await _preparar(session)

    salida = await en_peticion(
        session, admin.id, lambda: service.wa_link(session, aviso.id, admin.id)
    )

    assert isinstance(salida, WaLinkOut)
    assert salida.url == f"https://wa.me/57{TELEFONO_DIGITOS}?text={quote(TEXTO_DIFICIL, safe='')}"
    fila = await _fila(session, aviso.id)
    assert fila["status"] == "sent"
    assert (fila["sent_at"], fila["sent_by"]) == (reloj.now_utc(), admin.id)
    assert fila["attempts"] == 0 and fila["last_error"] is None


async def test_un_numero_con_prefijo_no_duplica_el_57(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    _, aviso = await _preparar(session, telefono="+57 300 765 4321")
    salida = await en_peticion(
        session, admin.id, lambda: service.wa_link(session, aviso.id, admin.id)
    )
    assert salida.url.startswith("https://wa.me/573007654321?text=")


async def test_la_segunda_llamada_devuelve_la_misma_url_sin_cambiar_la_marca(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    primero, segundo = await usuario_real("admin"), await usuario_real("coach")
    _, aviso = await _preparar(session)
    capturados = eventos_de(service.NotificationSent)
    uno = await en_peticion(
        session, primero.id, lambda: service.wa_link(session, aviso.id, primero.id)
    )
    marca = await _fila(session, aviso.id)
    reloj.advance(hours=1)

    dos = await en_peticion(
        session, segundo.id, lambda: service.wa_link(session, aviso.id, segundo.id)
    )

    assert dos.url == uno.url
    despues = await _fila(session, aviso.id)
    assert (despues["sent_at"], despues["sent_by"]) == (marca["sent_at"], primero.id)
    assert despues["updated_at"] == marca["updated_at"]
    assert len(capturados.vistos) == 1


async def test_un_aviso_fallido_tambien_pasa_a_sent(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    _, aviso = await _preparar(session, status="failed", attempts=3, last_error="timeout")
    await en_peticion(session, admin.id, lambda: service.wa_link(session, aviso.id, admin.id))
    assert (await _fila(session, aviso.id))["status"] == "sent"


async def test_cada_llamada_audita_reveal_y_escribe_crypto_ops_solo_del_telefono(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    miembro, aviso = await _preparar(session)

    for _ in range(2):
        await en_peticion(session, admin.id, lambda: service.wa_link(session, aviso.id, admin.id))

    reveals = await auditoria_del_socio(session, miembro.id, "reveal")
    assert [r["after"] for r in reveals] == [{"field": "phone", "purpose": "notify"}] * 2
    assert {(r["user_id"], r["subject_member_id"]) for r in reveals} == {(admin.id, miembro.id)}
    assert await contar_crypto_ops(session, miembro.id, "decrypt", "notify") == 2


async def test_el_telefono_solo_aparece_en_la_url(
    session: AsyncSession,
    usuario_real: CrearUsuario,
    caplog: pytest.LogCaptureFixture,
) -> None:
    admin = await usuario_real("admin")
    _, aviso = await _preparar(session, rendered_body="Hola Lucía")
    capturados = eventos_de(service.NotificationSent)
    caplog.set_level(logging.DEBUG)

    salida = await en_peticion(
        session, admin.id, lambda: service.wa_link(session, aviso.id, admin.id)
    )

    assert set(salida.model_dump()) == {"url"}
    assert TELEFONO_DIGITOS not in salida.model_dump_json().replace(salida.url, "")
    [evento] = capturados.vistos
    assert (evento.notification_id, evento.channel) == (aviso.id, "whatsapp_link")
    assert TELEFONO_DIGITOS not in repr(evento)
    assert TELEFONO_DIGITOS not in caplog.text
    ficha = await service.get(session, aviso.id)
    assert TELEFONO_DIGITOS not in ficha.model_dump_json() and "@" not in ficha.model_dump_json()


async def test_un_aviso_ya_enviado_devuelve_la_url_de_nuevo(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    _, aviso = await _preparar(session, status="sent", sent_by=admin.id)
    salida = await en_peticion(
        session, admin.id, lambda: service.wa_link(session, aviso.id, admin.id)
    )
    assert salida.url.startswith("https://wa.me/57")
    assert (await _fila(session, aviso.id))["sent_by"] == admin.id


# Rechazos ---------------------------------------------------------------------------------------


async def test_un_aviso_omitido_da_409_sin_descifrar_nada(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    miembro, aviso = await _preparar(session, status="skipped")

    with pytest.raises(NotificationClosed) as error:
        await en_peticion(session, admin.id, lambda: service.wa_link(session, aviso.id, admin.id))

    assert (error.value.status, error.value.code) == (409, "notification_closed")
    assert (await _fila(session, aviso.id))["status"] == "skipped"
    await _sin_rastro_de_contacto(session, miembro.id)


async def test_un_aviso_de_correo_da_409_sin_descifrar_nada(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    miembro = await socio(session, phone=TELEFONO)
    regla = await make_rule(session, channel="email")
    aviso = await make_notification(session, regla, member_id=miembro.id)

    with pytest.raises(WrongChannel) as error:
        await en_peticion(session, admin.id, lambda: service.wa_link(session, aviso.id, admin.id))

    assert (error.value.status, error.value.code) == (409, "wrong_channel")
    assert (await _fila(session, aviso.id))["status"] == "pending"
    await _sin_rastro_de_contacto(session, miembro.id)


async def test_un_socio_sin_telefono_da_422_y_el_aviso_sigue_pendiente(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    miembro, aviso = await _preparar(session, telefono=None)

    with pytest.raises(MemberWithoutPhone) as error:
        await en_peticion(session, admin.id, lambda: service.wa_link(session, aviso.id, admin.id))

    assert (error.value.status, error.value.code) == (422, "member_without_phone")
    fila = await _fila(session, aviso.id)
    assert (fila["status"], fila["sent_at"], fila["sent_by"]) == ("pending", None, None)
    assert await auditoria_del_socio(session, miembro.id, "reveal") == []


@pytest.mark.parametrize("motivo", ["baja", "sin_consentimiento"])
async def test_un_socio_de_baja_o_sin_consentimiento_no_es_contactable(
    session: AsyncSession, usuario_real: CrearUsuario, motivo: str
) -> None:
    admin = await usuario_real("admin")
    cambios = {"deleted_at": ANTES} if motivo == "baja" else {"consentido": False}
    miembro = await socio(session, phone=TELEFONO, **cambios)
    aviso = await make_notification(session, await make_rule(session), member_id=miembro.id)

    with pytest.raises(MemberNotContactable):
        await en_peticion(session, admin.id, lambda: service.wa_link(session, aviso.id, admin.id))

    assert (await _fila(session, aviso.id))["status"] == "pending"
    await _sin_rastro_de_contacto(session, miembro.id)


async def test_un_aviso_inexistente_es_404(
    session: AsyncSession, usuario_real: CrearUsuario
) -> None:
    admin = await usuario_real("admin")
    with pytest.raises(NotificationNotFound) as error:
        await service.wa_link(session, uuid4(), admin.id)
    assert (error.value.status, error.value.code) == (404, "notification_not_found")


# Teléfono inválido (S5-D224) ----------------------------------------------------------------------


@pytest.mark.parametrize("telefono", ["12345", "+1 415 555 2671", "6017654321"])
async def test_un_telefono_con_forma_invalida_da_422_y_conserva_el_rastro_del_descifrado(
    session: AsyncSession, usuario_real: CrearUsuario, telefono: str
) -> None:
    """El teléfono ya se descifró: el 422 `invalid_phone` no puede borrar el `reveal` ni dejar el
    aviso `sent`. Se confirma ANTES de lanzar."""
    from app.modules.notifications.exceptions import InvalidPhone

    admin = await usuario_real("admin")
    miembro, aviso = await _preparar(session, telefono=telefono)

    with pytest.raises(InvalidPhone) as error:
        await en_peticion(session, admin.id, lambda: service.wa_link(session, aviso.id, admin.id))
    await session.rollback()

    assert (error.value.status, error.value.code) == (422, "invalid_phone")
    assert telefono.strip() not in error.value.message
    fila = await _fila(session, aviso.id)
    assert (fila["status"], fila["sent_at"], fila["sent_by"]) == ("pending", None, None)
    assert len(await auditoria_del_socio(session, miembro.id, "reveal")) == 1
    assert await contar_crypto_ops(session, miembro.id, "decrypt", "notify") == 1

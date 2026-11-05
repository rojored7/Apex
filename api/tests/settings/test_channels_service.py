"""`channels_credentials_present` y el guardado de `channels` (US-122; S5-D30). Rojo B4.

La función es pura: recibe la `Settings`, devuelve `{"email": bool, "telegram": bool}` y nunca un
valor secreto. `update_section` guarda la sección con control de versión y la audita sin secretos.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.modules.settings.service import (
    channels_credentials_present,
    get_section,
    update_section,
)
from tests.core._canales_apoyo import CHAT_ID, SMTP_COMPLETO, TOKEN_BOT, settings_canales
from tests.settings._apoyo import ADMIN_ID, CHANNELS_OK, filas_de_auditoria


@pytest.fixture
async def db(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    with actor_scope(ADMIN_ID):
        yield session


def test_sin_ninguna_credencial_los_dos_canales_faltan() -> None:
    assert channels_credentials_present(settings_canales()) == {"email": False, "telegram": False}


def test_con_el_correo_completo_solo_el_correo_esta_listo() -> None:
    config = settings_canales(**SMTP_COMPLETO)

    assert channels_credentials_present(config) == {"email": True, "telegram": False}


def test_con_token_y_chat_solo_telegram_esta_listo() -> None:
    config = settings_canales(TELEGRAM_BOT_TOKEN=TOKEN_BOT, TELEGRAM_CHAT_ID=CHAT_ID)

    assert channels_credentials_present(config) == {"email": False, "telegram": True}


def test_con_todo_configurado_ambos_estan_listos() -> None:
    config = settings_canales(
        **SMTP_COMPLETO, TELEGRAM_BOT_TOKEN=TOKEN_BOT, TELEGRAM_CHAT_ID=CHAT_ID
    )

    assert channels_credentials_present(config) == {"email": True, "telegram": True}


@pytest.mark.parametrize("falta", ["SMTP_HOST", "SMTP_FROM"])
def test_el_correo_exige_servidor_y_remitente(falta: str) -> None:
    config = settings_canales(**SMTP_COMPLETO).model_copy(update={falta: None})

    assert channels_credentials_present(config)["email"] is False


@pytest.mark.parametrize("falta", ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"])
def test_telegram_exige_token_y_chat(falta: str) -> None:
    config = settings_canales(TELEGRAM_BOT_TOKEN=TOKEN_BOT, TELEGRAM_CHAT_ID=CHAT_ID).model_copy(
        update={falta: None}
    )

    assert channels_credentials_present(config)["telegram"] is False


def test_el_resultado_son_dos_booleanos_y_ningun_valor_secreto() -> None:
    config = settings_canales(
        **SMTP_COMPLETO, TELEGRAM_BOT_TOKEN=TOKEN_BOT, TELEGRAM_CHAT_ID=CHAT_ID
    )

    resultado = channels_credentials_present(config)

    assert set(resultado) == {"email", "telegram"}
    assert all(type(v) is bool for v in resultado.values())
    texto = json.dumps(resultado) + repr(resultado)
    for secreto in (
        "clave-smtp-no-real",
        "smtp.ejemplo.test",
        "apex@ejemplo.test",
        TOKEN_BOT,
        CHAT_ID,
    ):
        assert secreto not in texto


async def test_sin_fila_la_seccion_muestra_los_defaults_apagados(db: AsyncSession) -> None:
    salida = await get_section(db, "channels")

    assert salida.version == 0 and salida.key == "channels"
    assert salida.value["email"]["enabled"] is False
    assert salida.value["whatsapp"] == {"enabled": False, "country_code": "57"}
    assert salida.value["telegram"] == {"enabled": False}


async def test_guardar_audita_antes_y_despues_sin_ningun_secreto(db: AsyncSession) -> None:
    await update_section(db, "channels", CHANNELS_OK, 0, ADMIN_ID)
    cambiado = {**CHANNELS_OK, "telegram": {"enabled": True}}
    await update_section(db, "channels", cambiado, 1, ADMIN_ID)

    auditoria = await filas_de_auditoria(db)
    assert [f["action"] for f in auditoria] == ["insert", "update"]
    assert auditoria[1]["before"]["value"]["telegram"] == {"enabled": False}
    assert auditoria[1]["after"]["value"]["telegram"] == {"enabled": True}
    assert auditoria[1]["after"]["version"] == 2
    texto = json.dumps(auditoria, default=str)
    for secreto in ("clave-smtp-no-real", TOKEN_BOT, "password", "bot_token"):
        assert secreto not in texto

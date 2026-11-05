"""Esquema de `channels` (US-122; S5-D30). Rojo B4.

`email {enabled, sender_name, reply_to?}`, `whatsapp {enabled, country_code="57"}`,
`telegram {enabled}`; todo `enabled=false` por defecto y cerrado (`extra="forbid"`, también en cada
nivel): un secreto o una clave ajena da 422 con el campo. El nombre del remitente viaja a `From`
del correo: no admite saltos de línea (M-7 a).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from app.modules.settings.exceptions import SettingsValidationError
from app.modules.settings.schemas import (
    ENABLED_SECTIONS,
    SECTION_REGISTRY,
    SECTION_VIEWS,
    ChannelsSettings,
    SectionKey,
)
from app.modules.settings.service import defaults_for, validate_section
from tests.settings._apoyo import CHANNELS_OK


def _campo_invalido(valor: dict[str, Any]) -> str | None:
    with pytest.raises(SettingsValidationError) as excinfo:
        validate_section(SectionKey.channels, valor)
    assert excinfo.value.status == 422
    return excinfo.value.field


def _con(ruta: tuple[str, str], valor: object) -> dict[str, Any]:
    copia = copy.deepcopy(CHANNELS_OK)
    copia[ruta[0]][ruta[1]] = valor
    return copia


def test_channels_esta_habilitada_y_registrada_con_su_esquema() -> None:
    assert SectionKey.channels in ENABLED_SECTIONS
    assert SECTION_REGISTRY[SectionKey.channels] is ChannelsSettings
    assert SectionKey.channels in SECTION_VIEWS


def test_valor_valido() -> None:
    modelo = validate_section(SectionKey.channels, CHANNELS_OK)

    assert modelo.model_dump(mode="json") == CHANNELS_OK


def test_los_defaults_apagan_los_tres_canales_y_el_indicativo_es_57() -> None:
    defaults = defaults_for(SectionKey.channels)

    assert defaults["email"]["enabled"] is False
    assert defaults["email"]["reply_to"] is None
    assert defaults["whatsapp"] == {"enabled": False, "country_code": "57"}
    assert defaults["telegram"] == {"enabled": False}
    assert isinstance(defaults["email"]["sender_name"], str)
    assert set(defaults["email"]) == {"enabled", "sender_name", "reply_to"}


def test_los_defaults_son_un_valor_valido_de_la_seccion() -> None:
    defaults = defaults_for(SectionKey.channels)

    assert validate_section(SectionKey.channels, defaults).model_dump(mode="json") == defaults


def test_reply_to_es_opcional() -> None:
    sin_reply = _con(("email", "reply_to"), None)

    modelo = validate_section(SectionKey.channels, sin_reply)

    assert modelo.model_dump(mode="json")["email"]["reply_to"] is None


@pytest.mark.parametrize(
    "malo", ["sin-arroba", "a b@x.co", "ana@sinpunto", "ana@x.co\r\nBcc: z@y.co"]
)
def test_reply_to_invalido_da_422_en_su_campo(malo: str) -> None:
    assert _campo_invalido(_con(("email", "reply_to"), malo)) == "value.email.reply_to"


@pytest.mark.parametrize(
    "malo",
    ["", "Ana\r\nBcc: espia@malo.test", "Ana\nBcc: x", "x" * 81, "‮APEX"],
    ids=["vacio", "crlf", "lf", "de_81", "bidi"],
)
def test_sender_name_invalido_da_422_en_su_campo(malo: str) -> None:
    assert _campo_invalido(_con(("email", "sender_name"), malo)) == "value.email.sender_name"


@pytest.mark.parametrize("malo", ["", "abc", "5 7", "57\n"])
def test_country_code_invalido_da_422_en_su_campo(malo: str) -> None:
    assert (
        _campo_invalido(_con(("whatsapp", "country_code"), malo)) == "value.whatsapp.country_code"
    )


@pytest.mark.parametrize(
    ("clave", "campo"),
    [
        ("email.smtp_password", "value.email.smtp_password"),
        ("email.password", "value.email.password"),
        ("telegram.token", "value.telegram.token"),
        ("telegram.bot_token", "value.telegram.bot_token"),
        ("telegram.chat_id", "value.telegram.chat_id"),
        ("whatsapp.api_key", "value.whatsapp.api_key"),
        ("sms", "value.sms"),
        ("smtp_host", "value.smtp_host"),
    ],
)
def test_una_clave_ajena_o_un_secreto_da_422_con_su_ruta(clave: str, campo: str) -> None:
    valor = copy.deepcopy(CHANNELS_OK)
    if "." in clave:
        canal, nombre = clave.split(".")
        valor[canal][nombre] = "x"
    else:
        valor[clave] = {"enabled": True}

    assert _campo_invalido(valor) == campo


def test_una_clave_ajena_no_repite_el_valor_en_el_error() -> None:
    valor = copy.deepcopy(CHANNELS_OK)
    valor["telegram"]["token"] = "123456:AAH-no-debe-salir"  # noqa: S105

    with pytest.raises(SettingsValidationError) as excinfo:
        validate_section(SectionKey.channels, valor)

    assert "AAH-no-debe-salir" not in str(excinfo.value.message)


def test_no_acepta_credentials_present_como_entrada() -> None:
    valor = {**CHANNELS_OK, "credentials_present": {"email": True, "telegram": True}}

    assert _campo_invalido(valor) == "value.credentials_present"

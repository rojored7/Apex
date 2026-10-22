"""Enlaces de activación y restablecimiento (S2-B3; US-047; blueprint 7.2).

`activation_url(base_url, token)` arma `<FRONT_BASE_URL>/restablecer/<token>` (la única ruta
del front que consume tokens; no existe `/activar/`, E9). Los TTL son 72 h para `activate` y
1 h para `reset`.
"""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlsplit

import pytest

from app.core.security import new_opaque_token
from app.modules.auth.rules import ACTIVATE_TTL, RESET_TTL, activation_url


def test_los_ttl_son_72_horas_y_1_hora() -> None:
    assert timedelta(hours=72) == ACTIVATE_TTL
    assert timedelta(hours=1) == RESET_TTL


def test_la_url_es_la_base_mas_restablecer_y_el_token() -> None:
    token = new_opaque_token()
    assert activation_url("http://localhost:8180", token) == (
        f"http://localhost:8180/restablecer/{token}"
    )


@pytest.mark.parametrize(
    "base",
    ["http://localhost:8180/", "http://localhost:8180//"],
    ids=["una-barra", "dos-barras"],
)
def test_la_barra_final_de_la_base_no_duplica_la_barra(base: str) -> None:
    assert activation_url(base, "abc") == "http://localhost:8180/restablecer/abc"


def test_una_base_con_ruta_la_conserva() -> None:
    assert activation_url("https://apex.example/panel", "abc") == (
        "https://apex.example/panel/restablecer/abc"
    )


def test_el_token_opaco_viaja_sin_escapar_y_es_el_ultimo_segmento() -> None:
    """El token es base64url (32 bytes): no necesita codificarse ni lleva query."""
    token = new_opaque_token()
    partes = urlsplit(activation_url("http://localhost:8180", token))
    assert partes.path == f"/restablecer/{token}"
    assert partes.query == "" and partes.fragment == ""
    assert len(token) >= 43

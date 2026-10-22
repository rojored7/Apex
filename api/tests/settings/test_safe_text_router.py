"""Texto seguro en `PATCH /settings/gym` y `/settings/privacy` (revisión de seguridad V10, N-2).

JSONB rechaza `\u0000` y daba 500; un U+202E en el nombre del gimnasio se mostraría en todas
las pantallas. Los textos de una línea usan `SafeText`; la política (`policy_text`) usa
`SafeMultilineText`, que admite saltos de línea.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from tests.conftest import Cabeceras, CrearUsuario
from tests.settings._apoyo import API, GYM_OK, PRIVACY_OK

GYM = f"{API}/settings/gym"
PRIVACY = f"{API}/settings/privacy"


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("name", "Apex\x00"),
        ("name", "\u200b"),
        ("city", "Envi\u202egado"),
        ("address", "Cra 1\x00"),
        ("email", "hola\x00@apex.co"),
        ("phone", "604\x00"),
    ],
    ids=["nombre-nul", "nombre-zwsp", "ciudad-rlo", "direccion-nul", "correo-nul", "telefono-nul"],
)
async def test_gym_con_control_o_formato_da_422(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    campo: str,
    valor: str,
) -> None:
    admin = await usuario_real("admin")
    valor_json: dict[str, Any] = {**GYM_OK, campo: valor}
    r = await app_http.patch(
        GYM, headers=cabeceras(admin), json={"value": valor_json, "version": 0}
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == f"value.{campo}"


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("policy_text", "Texto\x00"), ("policy_text", "Texto\u202e"), ("policy_version", "v1\x00")],
    ids=["texto-nul", "texto-rlo", "version-nul"],
)
async def test_privacy_con_nul_o_bidi_da_422(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    campo: str,
    valor: str,
) -> None:
    admin = await usuario_real("admin")
    valor_json: dict[str, Any] = {**PRIVACY_OK, campo: valor}
    r = await app_http.patch(
        PRIVACY, headers=cabeceras(admin), json={"value": valor_json, "version": 0}
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == f"value.{campo}"


async def test_privacy_admite_saltos_de_linea(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    texto = "Política de datos\n\n1. Finalidad.\r\n\t2. Derechos."
    r = await app_http.patch(
        PRIVACY,
        headers=cabeceras(admin),
        json={"value": {**PRIVACY_OK, "policy_text": texto}, "version": 0},
    )
    assert r.status_code == 200, r.text
    assert r.json()["value"]["policy_text"] == texto


async def test_una_seccion_guardada_antes_del_texto_seguro_se_sigue_leyendo(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras, session: Any
) -> None:
    """Las salidas (`GymView`, `PrivacyView`) no aplican `SafeText`: un valor guardado antes de
    N-2 con un U+200B no rompe `GET /settings/gym` ni `/settings/privacy` (revisión del cierre)."""
    import json

    from sqlalchemy import text

    from app.core.context import SYSTEM_USER_ID

    zwsp = chr(0x200B)
    for clave, valor in (
        ("gym", {**GYM_OK, "city": "Envi" + zwsp + "gado"}),
        ("privacy", {**PRIVACY_OK, "policy_version": "v1" + zwsp}),
    ):
        await session.execute(
            text(
                "INSERT INTO settings.settings_sections (id, key, value, version, updated_by,"
                " created_by) VALUES (gen_random_uuid(), :k, CAST(:v AS jsonb), 1, :u, :u)"
            ),
            {"k": clave, "v": json.dumps(valor), "u": SYSTEM_USER_ID},
        )
    admin = await usuario_real("admin")
    for ruta in (GYM, PRIVACY):
        r = await app_http.get(ruta, headers=cabeceras(admin))
        assert r.status_code == 200, (ruta, r.text)

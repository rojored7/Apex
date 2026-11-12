"""El CBOM nunca lleva material ni referencias de llaves (S6-B3, US-146; S6-D17, S6-D57, L-5).

Recorre un CBOM real armado con `llaves_mixtas` (filas `local` y `openbao` de los tres propositos,
incluida la `sign` y la `decrypt_only`) y falla ante: `bytes`, una cadena base64 de 40 o mas
caracteres, la palabra `wrapped`, `vault:`, `apex-sign-audit` o `local:`. Los controles prueban el
recorrido con estructuras que si deben fallar. Rojo B3.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID
from app.core.crypto import inventory
from app.core.crypto.cbom import build_cbom
from app.core.crypto.models import CryptoKey
from app.core.crypto.schemas import KeysFilters, ProviderSummary
from app.core.pagination import PageParams
from tests.crypto.conftest import llaves_mixtas

BASE64_LARGO = re.compile(r"[A-Za-z0-9+/_=-]{40,}")
FRAGMENTOS_PROHIBIDOS = ("wrapped", "vault:", "apex-sign-audit", "local:")
CLAVES_PROHIBIDAS = frozenset(
    {"wrapped_material", "public_key", "key_ref", "material", "reference", "records_count"}
)


async def sumar_filas_openbao(session: AsyncSession) -> None:
    """Tres filas `openbao` (encrypt, index, sign) con referencias y material de aspecto real."""
    material = b"vault:v1:" + b"QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo0123456789+/=="
    for proposito, clase, algoritmo, referencia, publica in (
        ("encrypt", "member.phone", "A256GCM", material, None),
        ("index", "member.phone", "HMAC-SHA256", material, None),
        ("sign", "audit.signature", "Ed25519", b"apex-sign-audit", "A" * 43 + "="),
    ):
        session.add(
            CryptoKey(
                purpose=proposito,
                data_class=clase,
                algorithm=algoritmo,
                provider="openbao",
                version=7,
                state="decrypt_only",
                wrapped_material=referencia,
                public_key=publica,
                created_by=SYSTEM_USER_ID,
            )
        )
    await session.flush()


def problemas_en_cbom(valor: Any, ruta: str = "$") -> list[str]:
    """Hallazgos de material o referencias en un CBOM ya armado (dict/list/str/bytes)."""
    problemas: list[str] = []
    if isinstance(valor, bytes | bytearray | memoryview):
        problemas.append(f"{ruta}: bytes")
    elif isinstance(valor, dict):
        for clave, hijo in valor.items():
            if clave in CLAVES_PROHIBIDAS:
                problemas.append(f"{ruta}.{clave}: clave prohibida")
            problemas += problemas_en_cbom(hijo, f"{ruta}.{clave}")
    elif isinstance(valor, list | tuple):
        for n, hijo in enumerate(valor):
            problemas += problemas_en_cbom(hijo, f"{ruta}[{n}]")
    elif isinstance(valor, str):
        if BASE64_LARGO.fullmatch(valor) or BASE64_LARGO.search(valor):
            problemas.append(f"{ruta}: base64 de 40 o mas caracteres")
        minusculas = valor.lower()
        for fragmento in FRAGMENTOS_PROHIBIDOS:
            if fragmento in minusculas:
                problemas.append(f"{ruta}: contiene {fragmento!r}")
    return problemas


async def test_un_cbom_real_con_llaves_local_y_openbao_no_trae_material(
    session: AsyncSession, bus_listo: object, proveedor_local: object
) -> None:
    await llaves_mixtas(session, proveedor_local)  # type: ignore[arg-type]
    await sumar_filas_openbao(session)
    pagina = await inventory.list_keys(session, KeysFilters(), PageParams(limit=200, offset=0))
    assert {k.purpose for k in pagina.items} == {"encrypt", "index", "sign"}
    assert {k.provider for k in pagina.items} == {"local", "openbao"}

    cbom = build_cbom(
        pagina.items,
        app_version="abc1234",
        generated_at=datetime(2026, 11, 12, 15, 0, tzinfo=UTC),
        provider=ProviderSummary(names=["local", "openbao"], state="ok"),
        tls_declared=False,
    )

    assert len(cbom["keys"]) == 13
    assert problemas_en_cbom(cbom) == []


def test_control_bytes_se_detectan() -> None:
    assert problemas_en_cbom({"keys": [{"id": b"\x00\x01"}]}) == ["$.keys[0].id: bytes"]


def test_control_base64_de_40_o_mas_caracteres_se_detecta() -> None:
    assert problemas_en_cbom({"x": "A" * 40}) != []
    assert problemas_en_cbom({"x": "QUJD" * 12 + "=="}) != []
    assert problemas_en_cbom({"x": "A" * 39}) == []


def test_control_las_palabras_prohibidas_se_detectan() -> None:
    for texto in ("wrapped", "apxw1.wrapped.x", "vault:v1:abc", "apex-sign-audit", "local:/k"):
        assert problemas_en_cbom({"x": texto}) != [], texto


def test_control_un_proveedor_llamado_local_o_openbao_es_valido() -> None:
    assert problemas_en_cbom({"provider": "local", "names": ["local", "openbao"]}) == []
    assert problemas_en_cbom({"id": "6f0c2d3e-1b2a-4c5d-8e9f-0a1b2c3d4e5f"}) == []


def test_control_las_claves_de_material_se_detectan() -> None:
    assert problemas_en_cbom({"wrapped_material": "x"}) == ["$.wrapped_material: clave prohibida"]
    assert problemas_en_cbom({"k": {"public_key": "x"}}) == ["$.k.public_key: clave prohibida"]

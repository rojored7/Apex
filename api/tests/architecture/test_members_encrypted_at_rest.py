"""Los datos sensibles del socio están cifrados en reposo (S2-B7; US-069 criterio 3, US-031 criterio
4; CLAUDE.md, bus 4, 5 y 9; N-02).

Con un socio de la fábrica (valores de `KNOWN`) y SQL crudo, sin pasar por el ORM:
- ninguna columna de la fila (`row_to_json(t)::text`) contiene un valor de `KNOWN` en claro ni en
  su forma normalizada;
- cada uno de los cinco campos es un blob `apx1.<uuid>.A256GCM.<nonce>.<ct>` cuya llave es la
  `encrypt` activa de su clase;
- `document_idx`, `phone_idx` y `email_idx` son el índice ciego del bus sobre el valor (la
  comparación usa `bus.blind_index`, nunca `hmac` en la prueba);
- no hay columnas `*_hint` ni `notes`.
Bloquea el checkpoint: `tests/architecture` corre en todos los gates (A-5).
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import bus
from app.core.crypto.keyring import Keyring
from tests.factories.members import KNOWN, KNOWN_NORMALIZED, make_member

BLOB = re.compile(
    r"^apx1\.(?P<key_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"\.A256GCM\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$"
)
CLASES = {
    "document": "member.document",
    "phone": "member.phone",
    "email": "member.email",
    "birth_date": "member.birth_date",
    "emergency_contact": "member.emergency_contact",
}


async def _fila_cruda(session: AsyncSession, member_id: Any) -> tuple[str, dict[str, Any]]:
    json_texto = await session.scalar(
        text("SELECT row_to_json(t)::text FROM members.members t WHERE t.id = :id"),
        {"id": member_id},
    )
    fila = (
        (
            await session.execute(
                text(
                    "SELECT document, phone, email, birth_date, emergency_contact, "
                    "document_idx, phone_idx, email_idx FROM members.members WHERE id = :id"
                ),
                {"id": member_id},
            )
        )
        .mappings()
        .one()
    )
    assert json_texto is not None
    return json_texto, dict(fila)


async def test_ninguna_columna_contiene_un_valor_conocido_ni_su_forma_normalizada(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    socio = await make_member(session)
    json_texto, _ = await _fila_cruda(session, socio.id)
    for valor in KNOWN_NORMALIZED:
        assert valor not in json_texto, valor


async def test_los_cinco_campos_son_blobs_apx1_con_la_llave_activa_de_su_clase(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    socio = await make_member(session)
    _, fila = await _fila_cruda(session, socio.id)
    for columna, clase in CLASES.items():
        valor = fila[columna]
        assert isinstance(valor, str), columna
        coincide = BLOB.match(valor)
        assert coincide is not None, (columna, valor[:24])
        assert coincide["key_id"] == str(bus_listo.active_for("encrypt", clase).key_id), columna


async def test_los_indices_son_el_indice_ciego_del_bus(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    socio = await make_member(session)
    _, fila = await _fila_cruda(session, socio.id)
    assert fila["document_idx"] == bus.blind_index("member.document", KNOWN["document"])
    assert fila["phone_idx"] == bus.blind_index("member.phone", KNOWN["phone"])
    assert fila["phone_idx"] == bus.blind_index("member.phone", "3007654321")
    assert fila["email_idx"] == bus.blind_index("member.email", KNOWN["email"])
    assert fila["email_idx"] == bus.blind_index("member.email", "lucia.gomez@correo.co")
    for columna in ("document_idx", "phone_idx", "email_idx"):
        assert fila[columna] not in KNOWN_NORMALIZED


async def test_sin_columnas_hint_ni_notes(session: AsyncSession) -> None:
    columnas = {
        fila[0]
        for fila in await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'members' AND table_name = 'members'"
            )
        )
    }
    assert "document" in columnas, "members.members no existe todavía (0006_members)"
    assert [c for c in columnas if c.endswith("_hint")] == []
    assert "notes" not in columnas

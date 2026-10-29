"""Detalle de una entrada de auditoría con datos reales (S4A-B4, US-103; S4A-D17, S4A-D52).

`audit_service.get_entry(session, seq)` sobre la cadena de `sembrar_actividad` (ver
`test_list.py`): la fila 4 es el `insert` de la socia (cinco blobs y tres `***`), la 5 el
`update` de Juan (teléfono y correo, con sus índices) y la 6 el `reveal` del teléfono.
- `changes` de la 5: solo `email` y `phone`, `changed`, con `encrypted = True` y el marcador
  `{"encrypted": True, "key_id", "alg": "A256GCM"}` a cada lado (el `key_id` es la segunda parte
  del blob guardado); `email_idx` y `phone_idx` valen `***` antes y después (la auditoría guarda
  el índice redactado), así que no son un cambio, pero salen como `***` en `before`/`after`;
- la respuesta serializada completa no contiene `apx1.` ni el teléfono o el correo en claro
  (los de `KNOWN` ni los nuevos);
- el servicio nunca descifra: espías sobre `types.reveal` y `bus.decrypt` sin llamadas;
- `seq` inexistente da `AuditEntryNotFound` (404 `audit_entry_not_found`); la lectura no cambia
  `audit.audit_log`.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto import bus
from app.core.crypto import types as crypto_types
from app.core.crypto.keyring import Keyring
from app.modules.audit.exceptions import AuditEntryNotFound
from app.modules.audit.schemas import AuditDetail
from tests.audit._apoyo import (
    CAMPOS_CHANGE,
    CAMPOS_DETAIL,
    CORREO_NUEVO,
    IP_REVELAR,
    JUAN_EMAIL,
    JUAN_NOMBRE,
    MOTIVO_ANULACION,
    TELEFONO_NUEVO,
    Actividad,
    leer_entrada,
    sembrar_actividad,
)
from tests.audit.conftest import CadenaDePrueba, audit_service
from tests.conftest import UsuarioPrueba
from tests.factories.members import KNOWN_NORMALIZED

CIFRADOS = ("document", "phone", "email", "birth_date", "emergency_contact")
INDICES = ("document_idx", "phone_idx", "email_idx")


@pytest.fixture
async def actividad(
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    ana: UsuarioPrueba,
    juan: UsuarioPrueba,
) -> Actividad:
    return await sembrar_actividad(session, ana=ana, juan=juan)


def _marcador(blob: str) -> dict[str, Any]:
    return {"encrypted": True, "key_id": blob.split(".")[1], "alg": "A256GCM"}


async def test_update_de_telefono_y_correo_trae_changes_marcados(
    session: AsyncSession, actividad: Actividad, juan: UsuarioPrueba
) -> None:
    cruda = await leer_entrada(session, 5)
    assert cruda is not None

    detalle = await audit_service.get_entry(session, 5)

    assert set(detalle.model_dump()) == CAMPOS_DETAIL
    assert (detalle.seq, detalle.action, detalle.table_name) == (5, "update", "members.members")
    assert (detalle.user_id, detalle.user_email, detalle.user_name) == (
        juan.id,
        JUAN_EMAIL,
        JUAN_NOMBRE,
    )
    assert (detalle.record_id, detalle.subject_member_id) == (
        actividad.member_id,
        actividad.member_id,
    )
    assert (detalle.prev_hash, detalle.hash) == (cruda["prev_hash"], cruda["hash"])
    cambios = {c.field: c for c in detalle.changes}
    assert [c.field for c in detalle.changes] == ["email", "phone"]
    assert all(set(c.model_dump()) == CAMPOS_CHANGE for c in detalle.changes)
    for campo in ("phone", "email"):
        assert (cambios[campo].kind, cambios[campo].encrypted) == ("changed", True)
        assert cambios[campo].before == _marcador(cruda["before"][campo])
        assert cambios[campo].after == _marcador(cruda["after"][campo])
    assert (cruda["before"]["phone_idx"], cruda["after"]["phone_idx"]) == ("***", "***")


async def test_before_y_after_llevan_el_marcador_y_los_idx_como_asteriscos(
    session: AsyncSession, actividad: Actividad
) -> None:
    cruda = await leer_entrada(session, 5)
    assert cruda is not None

    detalle = await audit_service.get_entry(session, 5)

    assert detalle.before is not None and detalle.after is not None
    assert detalle.before["phone"] == _marcador(cruda["before"]["phone"])
    assert detalle.before["phone"]["key_id"] == cruda["before"]["phone"].split(".")[1]
    assert detalle.after["email"] == _marcador(cruda["after"]["email"])
    assert detalle.before["phone_idx"] == "***" and detalle.after["email_idx"] == "***"


async def test_la_respuesta_serializada_no_lleva_blobs_ni_datos_en_claro(
    session: AsyncSession, actividad: Actividad
) -> None:
    for seq in (4, 5, 6):
        volcado = (await audit_service.get_entry(session, seq)).model_dump_json()
        assert "apx1." not in volcado, seq
        for valor in (*KNOWN_NORMALIZED, TELEFONO_NUEVO, "573015550101", CORREO_NUEVO):
            assert valor not in volcado, (seq, valor)


async def test_insert_de_la_socia_todo_added_con_los_cinco_cifrados(
    session: AsyncSession, actividad: Actividad
) -> None:
    detalle = await audit_service.get_entry(session, 4)

    assert detalle.before is None and detalle.after is not None
    assert all(c.kind == "added" and c.before is None for c in detalle.changes)
    cifrados = {c.field for c in detalle.changes if c.encrypted}
    assert cifrados == set(CIFRADOS)
    assert all(detalle.after[campo]["encrypted"] is True for campo in CIFRADOS)
    assert all(detalle.after[campo] == "***" for campo in INDICES)
    nombres = [c.field for c in detalle.changes]
    assert nombres == sorted(nombres)
    assert {"first_name": "Lucía"}.items() <= detalle.after.items()


async def test_reveal_muestra_campo_e_ip_sobre_after(
    session: AsyncSession, actividad: Actividad
) -> None:
    detalle = await audit_service.get_entry(session, 6)
    assert detalle.before is None
    assert detalle.after == {"field": "phone", "ip": IP_REVELAR}
    assert [(c.field, c.kind, c.after, c.encrypted) for c in detalle.changes] == [
        ("field", "added", "phone", False),
        ("ip", "added", IP_REVELAR, False),
    ]


async def test_la_anulacion_del_pago_muestra_el_motivo_al_admin(
    session: AsyncSession, actividad: Actividad
) -> None:
    detalle = await audit_service.get_entry(session, 10)
    cambios = {c.field: c for c in detalle.changes}
    assert (cambios["voided"].before, cambios["voided"].after) == (False, True)
    assert cambios["void_reason"].after == MOTIVO_ANULACION
    assert detalle.record_id == actividad.payment_id


async def test_el_servicio_no_descifra_nunca(
    session: AsyncSession, actividad: Actividad, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamadas: list[str] = []

    def reveal_espia(*args: Any, **kwargs: Any) -> Any:
        llamadas.append("types.reveal")
        raise AssertionError("el detalle de auditoría no revela")

    def decrypt_espia(*args: Any, **kwargs: Any) -> Any:
        llamadas.append("bus.decrypt")
        raise AssertionError("el detalle de auditoría no descifra")

    monkeypatch.setattr(crypto_types, "reveal", reveal_espia)
    monkeypatch.setattr(bus, "decrypt", decrypt_espia)

    for seq in range(1, 12):
        detalle = await audit_service.get_entry(session, seq)
        assert isinstance(detalle, AuditDetail)

    assert llamadas == []


async def test_seq_inexistente_da_audit_entry_not_found(
    session: AsyncSession, actividad: Actividad
) -> None:
    with pytest.raises(AuditEntryNotFound) as capturado:
        await audit_service.get_entry(session, 12)
    assert (capturado.value.status, capturado.value.code) == (404, "audit_entry_not_found")


async def test_el_detalle_no_modifica_audit_log(
    audit_chain_factory: CadenaDePrueba, actividad: Actividad
) -> None:
    antes = (await audit_chain_factory.digest(), await audit_chain_factory.last_seq())
    for seq in (1, 5, 11):
        await audit_service.get_entry(audit_chain_factory.session, seq)
    assert (await audit_chain_factory.digest(), await audit_chain_factory.last_seq()) == antes

"""Puras del historial del socio (S4A-B5, US-106; S4A-D20, S4A-D50, M-6.3).

`diff.history_fields(entry)`: nombres de campo, nunca valores. `insert` y `delete` -> `[]`;
`update` -> las columnas que cambiaron, ordenadas, sin `*_idx`, sin las técnicas
(`created_at`, `updated_at`) y sin `reference` ni `void_reason` (S4A-D20); `reveal` ->
`[after["field"]]`, nunca `ip` ni `purpose`.
`diff.history_purpose(entry)`: `after["purpose"]` de un `reveal` automático (`notify` o
`auth_link`); `None` en el interactivo (`field` + `ip`), en otra acción o fuera del conjunto.
`canonical`/`chain_hash` con y sin `subject_member_id`: sin la clave cuando es nula, el hash es el
de US-015 (G-05).
Las entradas son `AuditEntry` sin sesión, con las formas reales de la cadena (filas 4 a 11 de
`sembrar_actividad`, ver `test_list.py`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.audit import HASHED_KEYS, SUBJECT_KEY, ZERO_HASH, AuditEntry, canonical, chain_hash
from app.core.crypto.digest import sha256_hex
from app.modules.audit import diff

BLOB = "apx1.61c93652-fc35-41e2-bc29-5a310ee09c0e.A256GCM.BEj5fzlyJg0RcTe8.H955oIt2zz95jP6C"
OTRO_BLOB = "apx1.61c93652-fc35-41e2-bc29-5a310ee09c0e.A256GCM.37urnq1v3xALXmww.YG11un8HcA_9Aff3"
SOCIA = UUID("0000000a-0000-4000-8000-0000000b0001")


def _entrada(
    action: str, before: dict[str, Any] | None = None, after: dict[str, Any] | None = None
) -> AuditEntry:
    return AuditEntry(action=action, table_name="members.members", before=before, after=after)


# history_fields ------------------------------------------------------------------------------


def test_insert_da_lista_vacia_aunque_after_traiga_todo() -> None:
    entrada = _entrada(
        "insert",
        after={"id": str(SOCIA), "first_name": "Lucía", "phone": BLOB, "phone_idx": "***"},
    )
    assert diff.history_fields(entrada) == []


def test_delete_da_lista_vacia() -> None:
    entrada = _entrada("delete", before={"id": str(SOCIA), "status": "active"})
    assert diff.history_fields(entrada) == []


def test_update_de_telefono_y_correo_da_sus_nombres_sin_idx_ni_tecnicas() -> None:
    """Forma real de la fila 5: los `_idx` llegan con `***` a los dos lados."""
    entrada = _entrada(
        "update",
        before={"email": BLOB, "email_idx": "***", "phone": OTRO_BLOB, "phone_idx": "***"},
        after={
            "phone": OTRO_BLOB + "x",
            "phone_idx": "***",
            "email": BLOB + "x",
            "email_idx": "***",
            "updated_at": "2026-10-21T15:00:00.000000Z",
            "created_at": "2026-10-21T15:00:00.000000Z",
        },
    )
    assert diff.history_fields(entrada) == ["email", "phone"]


def test_update_con_notas_y_estado_ordena_por_nombre() -> None:
    entrada = _entrada(
        "update",
        before={"status": "active", "notes": None, "deleted_at": None},
        after={"status": "inactive", "notes": "texto", "deleted_at": "2026-10-21"},
    )
    assert diff.history_fields(entrada) == ["deleted_at", "notes", "status"]


def test_update_de_membresia_por_congelacion_da_fin_y_estado() -> None:
    entrada = AuditEntry(
        action="update",
        table_name="memberships.memberships",
        before={"end_date": "2026-11-20", "status": "active"},
        after={"end_date": "2026-11-27", "status": "frozen"},
    )
    assert diff.history_fields(entrada) == ["end_date", "status"]


def test_anulacion_de_pago_nunca_nombra_void_reason_ni_reference() -> None:
    """Forma real de la fila 10 (S4A-D20): ni el valor ni el nombre de `void_reason`."""
    entrada = AuditEntry(
        action="update",
        table_name="payments.payments",
        before={"void_reason": None, "voided": False, "voided_at": None, "voided_by": None},
        after={
            "void_reason": "Pago duplicado de prueba",
            "voided": True,
            "voided_at": "2026-10-21T15:00:00.000000Z",
            "voided_by": str(uuid4()),
            "reference": "REF-1",
        },
    )
    assert diff.history_fields(entrada) == ["voided", "voided_at", "voided_by"]


def test_update_sin_before_usa_las_claves_de_after() -> None:
    """Los eventos de `auth` (`UserLocked`, ...) son `update` con `before = None`."""
    entrada = _entrada("update", before=None, after={"status": "inactive"})
    assert diff.history_fields(entrada) == ["status"]


def test_reveal_interactivo_da_el_campo_y_nunca_ip() -> None:
    entrada = _entrada("reveal", after={"field": "document", "ip": "198.51.100.40"})
    assert diff.history_fields(entrada) == ["document"]


def test_reveal_automatico_da_el_campo_y_nunca_purpose() -> None:
    entrada = _entrada("reveal", after={"field": "phone", "purpose": "notify"})
    assert diff.history_fields(entrada) == ["phone"]


@pytest.mark.parametrize("after", [None, {}, {"ip": "198.51.100.40"}])
def test_reveal_sin_campo_da_lista_vacia(after: dict[str, Any] | None) -> None:
    assert diff.history_fields(_entrada("reveal", after=after)) == []


def test_no_muta_la_entrada() -> None:
    antes = {"phone": BLOB, "phone_idx": "***"}
    despues = {"phone": OTRO_BLOB, "phone_idx": "***"}
    entrada = _entrada("update", before=dict(antes), after=dict(despues))
    diff.history_fields(entrada)
    assert (entrada.before, entrada.after) == (antes, despues)


def test_ningun_valor_sale_en_los_nombres() -> None:
    entrada = _entrada(
        "update",
        before={"phone": BLOB, "notes": "secreto viejo"},
        after={"phone": OTRO_BLOB, "notes": "secreto nuevo"},
    )
    salida = " ".join(diff.history_fields(entrada))
    assert "apx1." not in salida and "secreto" not in salida


# history_purpose -----------------------------------------------------------------------------


@pytest.mark.parametrize("proposito", ["notify", "auth_link"])
def test_reveal_con_purpose_devuelve_el_proposito(proposito: str) -> None:
    entrada = _entrada("reveal", after={"field": "phone", "purpose": proposito})
    assert diff.history_purpose(entrada) == proposito


def test_reveal_interactivo_no_tiene_purpose() -> None:
    entrada = _entrada("reveal", after={"field": "phone", "ip": "198.51.100.40"})
    assert diff.history_purpose(entrada) is None


@pytest.mark.parametrize("proposito", ["marketing", "mask", "reveal", "", 1, None])
def test_purpose_fuera_del_conjunto_cerrado_es_none(proposito: object) -> None:
    entrada = _entrada("reveal", after={"field": "phone", "purpose": proposito})
    assert diff.history_purpose(entrada) is None


@pytest.mark.parametrize("accion", ["insert", "update", "delete"])
def test_otra_accion_no_tiene_purpose(accion: str) -> None:
    entrada = _entrada(accion, before=None, after={"purpose": "notify"})
    assert diff.history_purpose(entrada) is None


def test_reveal_sin_after_no_tiene_purpose() -> None:
    assert diff.history_purpose(_entrada("reveal", after=None)) is None


# canonical con y sin subject_member_id (G-05) ------------------------------------------------


def _fila(**extra: object) -> dict[str, object]:
    return {
        "id": UUID("00000000-0000-4000-8000-0000000000aa"),
        "seq": 7,
        "at": datetime(2026, 10, 21, 15, 0, tzinfo=UTC),
        "user_id": UUID("00000000-0000-4000-8000-0000000000bb"),
        "action": "update",
        "table_name": "memberships.memberships",
        "record_id": UUID("00000000-0000-4000-8000-0000000000cc"),
        "before": {"status": "active"},
        "after": {"status": "frozen"},
        **extra,
    }


def test_sin_sujeto_el_hash_es_el_de_us_015() -> None:
    """Sujeto nulo o ausente: `canonical` de las claves de `HASHED_KEYS` solamente."""
    fila = _fila()
    esperado = sha256_hex(ZERO_HASH.encode("ascii") + canonical({k: fila[k] for k in HASHED_KEYS}))
    assert chain_hash(ZERO_HASH, fila) == esperado
    assert chain_hash(ZERO_HASH, _fila(subject_member_id=None)) == esperado
    assert b"subject_member_id" not in canonical({k: fila[k] for k in HASHED_KEYS})


def test_con_sujeto_la_clave_entra_al_hash() -> None:
    fila = _fila(subject_member_id=SOCIA)
    con_clave = {**{k: fila[k] for k in HASHED_KEYS}, SUBJECT_KEY: SOCIA}
    esperado = sha256_hex(ZERO_HASH.encode("ascii") + canonical(con_clave))
    assert chain_hash(ZERO_HASH, fila) == esperado
    assert chain_hash(ZERO_HASH, fila) != chain_hash(ZERO_HASH, _fila())
    assert f'"subject_member_id":"{SOCIA}"'.encode() in canonical(con_clave)

"""`diff(before, after, action)` del detalle de auditoría: pruebas puras (S4A-B4, US-103; S4A-D17,
S4A-D52).

Contrato: lista de `FieldChange(field, kind, before, after, encrypted)` ordenada por nombre de
campo. `insert`: todo `added` (antes `None`); `delete`: todo `removed` (después `None`); `update`:
solo los campos distintos (`changed`; `added` o `removed` si falta de un lado); un `update` sin
cambios da `[]`; en `reveal`, `login`, `verify`, `download` y `export` se ignora `before` y todo
`after` es `added`. Un blob `apx1.` (antes o después) marca `encrypted = True` y sale sustituido
por el marcador `{"encrypted": True, "key_id", "alg"}`; `***` (índice ciego) no es un blob.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.core.audit import AuditEntry
from app.modules.audit.diff import REDUCED_FIELDS, diff, reduce_entry
from app.modules.audit.schemas import AuditEntryView, FieldChange

K1 = "328c1948-e343-48a1-9ef4-1b9dab140c4f"
K2 = "83bce44d-f4a9-4c49-9e3f-15c82fa8616a"
VIEJO = f"apx1.{K1}.A256GCM.bm9uY2U.Y3Q"
NUEVO = f"apx1.{K2}.A256GCM.b3Rybw.b3Rybw"
M_VIEJO = {"encrypted": True, "key_id": K1, "alg": "A256GCM"}
M_NUEVO = {"encrypted": True, "key_id": K2, "alg": "A256GCM"}


def _c(
    field: str, kind: str, before: Any = None, after: Any = None, *, enc: bool = False
) -> FieldChange:
    return FieldChange(field=field, kind=kind, before=before, after=after, encrypted=enc)  # type: ignore[arg-type]


def test_insert_todo_added_y_ordenado() -> None:
    cambios = diff(None, {"name": "Mensual", "price_cop": 120000, "is_active": True}, "insert")
    assert cambios == [
        _c("is_active", "added", None, True),
        _c("name", "added", None, "Mensual"),
        _c("price_cop", "added", None, 120000),
    ]


def test_insert_de_socio_marca_los_blobs_y_no_los_indices() -> None:
    cambios = diff(None, {"phone": VIEJO, "phone_idx": "***", "first_name": "Lucía"}, "insert")
    assert cambios == [
        _c("first_name", "added", None, "Lucía"),
        _c("phone", "added", None, M_VIEJO, enc=True),
        _c("phone_idx", "added", None, "***"),
    ]


def test_update_sin_cambios_da_lista_vacia() -> None:
    assert diff({"status": "active"}, {"status": "active"}, "update") == []
    assert diff({}, {}, "update") == []


def test_update_con_dos_campos_solo_trae_los_distintos() -> None:
    antes = {"name": "Mensual", "price_cop": 120000, "is_active": True}
    despues = {"name": "Mensual Plus", "price_cop": 150000, "is_active": True}
    assert diff(antes, despues, "update") == [
        _c("name", "changed", "Mensual", "Mensual Plus"),
        _c("price_cop", "changed", 120000, 150000),
    ]


def test_update_de_telefono_cifrado_marca_y_sustituye_ambos_lados() -> None:
    cambios = diff(
        {"phone": VIEJO, "phone_idx": "***"}, {"phone": NUEVO, "phone_idx": "***"}, "update"
    )
    assert cambios == [_c("phone", "changed", M_VIEJO, M_NUEVO, enc=True)]
    assert "apx1." not in repr(cambios)


def test_update_de_un_campo_que_pasa_a_null() -> None:
    assert diff({"phone": VIEJO}, {"phone": None}, "update") == [
        _c("phone", "changed", M_VIEJO, None, enc=True)
    ]
    assert diff({"reference": "R-1"}, {"reference": None}, "update") == [
        _c("reference", "changed", "R-1", None)
    ]


def test_update_con_campo_solo_de_un_lado() -> None:
    assert diff({"a": 1}, {"b": 2}, "update") == [
        _c("a", "removed", 1, None),
        _c("b", "added", None, 2),
    ]


def test_update_de_evento_de_auth_sin_before_es_added() -> None:
    """Las filas `update` de `UserLocked` y compañía tienen `before = None`."""
    assert diff(None, {"event": "UserLocked", "reason": "manual"}, "update") == [
        _c("event", "added", None, "UserLocked"),
        _c("reason", "added", None, "manual"),
    ]


def test_delete_todo_removed() -> None:
    assert diff({"name": "Mensual", "phone": VIEJO}, None, "delete") == [
        _c("name", "removed", "Mensual", None),
        _c("phone", "removed", M_VIEJO, None, enc=True),
    ]


def test_reveal_se_aplica_sobre_after() -> None:
    cambios = diff(None, {"field": "phone", "ip": "198.51.100.40"}, "reveal")
    assert cambios == [
        _c("field", "added", None, "phone"),
        _c("ip", "added", None, "198.51.100.40"),
    ]


@pytest.mark.parametrize("accion", ["reveal", "login", "verify", "download", "export"])
def test_las_lecturas_ignoran_before(accion: str) -> None:
    cambios = diff({"ignorado": 1}, {"result": "ok"}, accion)
    assert cambios == [_c("result", "added", None, "ok")]


def test_login_y_verify_sobre_after() -> None:
    assert [c.field for c in diff(None, {"result": "ok", "reason": None, "ip": "x"}, "login")] == [
        "ip",
        "reason",
        "result",
    ]
    verify = diff(None, {"ok": True, "through_seq": 50, "rows_checked": 50}, "verify")
    assert [(c.field, c.kind, c.after) for c in verify] == [
        ("ok", "added", True),
        ("rows_checked", "added", 50),
        ("through_seq", "added", 50),
    ]


def test_el_orden_es_estable_por_nombre() -> None:
    antes = {"z": 1, "a": 1, "m": 1}
    despues = {"m": 2, "z": 2, "a": 2}
    assert [c.field for c in diff(antes, despues, "update")] == ["a", "m", "z"]


def test_diff_no_muta_la_entrada() -> None:
    antes = {"phone": VIEJO}
    despues = {"phone": NUEVO}
    diff(antes, despues, "update")
    assert (antes, despues) == ({"phone": VIEJO}, {"phone": NUEVO})


# `reduce_entry` (S4A-B8, US-110; S4A-D28): la vista reducida del tablero ---------------------


def _fila(
    action: str, table_name: str, before: dict[str, Any] | None, after: dict[str, Any] | None
) -> AuditEntry:
    return AuditEntry(
        id=uuid4(),
        seq=42,
        at=datetime(2026, 10, 20, 15, 0, tzinfo=UTC),
        user_id=uuid4(),
        action=action,
        table_name=table_name,
        record_id=uuid4(),
        subject_member_id=uuid4(),
        before=before,
        after=after,
        prev_hash="0" * 64,
        hash="1" * 64,
    )


def test_reduced_fields_es_la_lista_blanca_de_s4a_d28() -> None:
    assert (
        frozenset(
            {
                "member_id",
                "plan_id",
                "membership_id",
                "amount_cop",
                "voided",
                "deleted_at",
                "status",
            }
        )
        == REDUCED_FIELDS
    )


def test_reduce_entry_copia_la_cabecera_y_filtra_before_y_after() -> None:
    fila = _fila(
        "insert",
        "payments.payments",
        None,
        {
            "amount_cop": 120_000,
            "member_id": "m",
            "membership_id": "x",
            "method": "cash",
            "reference": "NEQ-778812",
            "void_reason": None,
            "voided": False,
            "registered_by": "u",
        },
    )
    vista = reduce_entry(fila)
    assert isinstance(vista, AuditEntryView)
    assert (vista.seq, vista.at, vista.user_id, vista.action) == (
        fila.seq,
        fila.at,
        fila.user_id,
        "insert",
    )
    assert (vista.table_name, vista.record_id, vista.subject_member_id) == (
        "payments.payments",
        fila.record_id,
        fila.subject_member_id,
    )
    assert vista.before is None
    assert dict(vista.after or {}) == {
        "amount_cop": 120_000,
        "member_id": "m",
        "membership_id": "x",
        "voided": False,
    }


def test_reduce_entry_descarta_blobs_reference_y_void_reason_del_update() -> None:
    fila = _fila(
        "update",
        "payments.payments",
        {"voided": False, "void_reason": None, "voided_at": None},
        {"voided": True, "void_reason": "Pago duplicado", "voided_at": "2026-10-20"},
    )
    vista = reduce_entry(fila)
    assert dict(vista.before or {}) == {"voided": False}
    assert dict(vista.after or {}) == {"voided": True}
    socio = reduce_entry(
        _fila("update", "members.members", {"phone": VIEJO, "phone_idx": "***"}, {"phone": NUEVO})
    )
    assert (dict(socio.before or {}), dict(socio.after or {})) == ({}, {})
    assert "apx1." not in repr(socio)


def test_reduce_entry_no_muta_la_fila_y_la_vista_es_inmutable() -> None:
    after = {"status": "active", "end_date": "2026-11-19"}
    fila = _fila("update", "memberships.memberships", {"status": "pending_payment"}, after)
    vista = reduce_entry(fila)
    assert fila.after == {"status": "active", "end_date": "2026-11-19"}
    with pytest.raises(FrozenInstanceError):
        vista.seq = 1  # type: ignore[misc]

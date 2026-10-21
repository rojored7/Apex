"""Funciones puras del hook de auditoría y el actor del contexto (US-016 T8)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID

import pytest

from app.core.audit import (
    AuditSerializationError,
    PlaintextInAuditError,
    diff_row,
    serialize_row,
    serialize_value,
)
from app.core.context import (
    SYSTEM_USER_ID,
    MissingActorError,
    actor_scope,
    current_actor,
    get_actor,
)


class Estado(Enum):
    ACTIVA = "active"


# diff_row -------------------------------------------------------------------------


def test_diff_row_sin_cambios() -> None:
    assert diff_row({"a": 1, "b": "x"}, {"a": 1, "b": "x"}) == ({}, {})


def test_diff_row_un_cambio_y_cambio_a_nulo() -> None:
    assert diff_row({"a": 1, "b": "x"}, {"a": 2, "b": "x"}) == ({"a": 1}, {"a": 2})
    assert diff_row({"a": 1, "b": "x"}, {"a": 1, "b": None}) == ({"b": "x"}, {"b": None})


def test_diff_row_dos_columnas_y_clave_nueva() -> None:
    antes, despues = diff_row({"a": 1, "b": "x", "c": 0}, {"a": 2, "b": "y", "c": 0})
    assert antes == {"a": 1, "b": "x"} and despues == {"a": 2, "b": "y"}
    assert diff_row({"a": 1}, {"a": 1, "d": 4}) == ({"d": None}, {"d": 4})


# serialize_value --------------------------------------------------------------------


def test_serialize_value_tipos_admitidos() -> None:
    assert serialize_value(UUID("ABCDEF01-0000-0000-0000-000000000000")) == (
        "abcdef01-0000-0000-0000-000000000000"
    )
    bogota = datetime(2026, 10, 21, 10, 4, 5, 123456, tzinfo=timezone(timedelta(hours=-5)))
    assert serialize_value(bogota) == "2026-10-21T15:04:05.123456Z"
    assert serialize_value(datetime(2026, 1, 1, tzinfo=UTC)) == "2026-01-01T00:00:00.000000Z"
    assert serialize_value(date(2026, 2, 3)) == "2026-02-03"
    assert serialize_value(Estado.ACTIVA) == "active"
    assert serialize_value({"k": [1, None, True, "ñ"]}) == {"k": [1, None, True, "ñ"]}
    assert serialize_value(None) is None


@pytest.mark.parametrize(
    "valor",
    [datetime(2026, 1, 1), 1.5, Decimal("1"), b"x"],
    ids=["ingenuo", "float", "decimal", "bytes"],
)
def test_serialize_value_rechaza(valor: object) -> None:
    with pytest.raises(AuditSerializationError):
        serialize_value(valor)


# serialize_row --------------------------------------------------------------------


def test_serialize_row_excluye_tecnicas_y_redacta() -> None:
    fila = {
        "id": UUID(int=1),
        "email": "A@b.co",
        "password_hash": "$argon2id$...",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "created_by": SYSTEM_USER_ID,
    }
    salida = serialize_row(fila, encrypted=frozenset(), redacted=frozenset({"password_hash"}))
    assert salida == {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "A@b.co",
        "password_hash": "***",
        "created_by": "00000000-0000-0000-0000-000000000001",
    }


def test_serialize_row_acepta_blob_y_nulo_en_columna_cifrada() -> None:
    fila = {"document": "apx1.k1.A256GCM.bm9uY2U.Y3Q", "phone": None}
    salida = serialize_row(fila, encrypted=frozenset({"document", "phone"}), redacted=frozenset())
    assert salida == {"document": "apx1.k1.A256GCM.bm9uY2U.Y3Q", "phone": None}


def test_serialize_row_rechaza_texto_en_claro_en_columna_cifrada() -> None:
    with pytest.raises(PlaintextInAuditError) as excinfo:
        serialize_row(
            {"document": "1020304"}, encrypted=frozenset({"document"}), redacted=frozenset()
        )
    assert "1020304" not in str(excinfo.value)
    assert "document" in str(excinfo.value)


# actor ------------------------------------------------------------------------------


def test_get_actor_sin_actor_lanza_missing_actor() -> None:
    token = current_actor.set(None)
    try:
        with pytest.raises(MissingActorError) as excinfo:
            get_actor()
        assert "actor_scope" in str(excinfo.value) and "--as" in str(excinfo.value)
    finally:
        current_actor.reset(token)


def test_actor_scope_fija_y_restaura() -> None:
    token = current_actor.set(None)
    try:
        persona = UUID(int=7)
        with actor_scope(persona):
            assert get_actor() == persona
            with actor_scope(SYSTEM_USER_ID):
                assert get_actor() == SYSTEM_USER_ID
            assert get_actor() == persona
        assert current_actor.get() is None
    finally:
        current_actor.reset(token)


def test_system_user_id_es_la_constante_de_n15() -> None:
    assert SYSTEM_USER_ID == UUID("00000000-0000-0000-0000-000000000001")

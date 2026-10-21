"""Funciones puras de la cadena de auditoría (US-015 T8): `canonical`, `chain_hash`, `verify_chain`."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID

import pytest

from app.core.audit import (
    HASHED_KEYS,
    ZERO_HASH,
    CanonicalError,
    VerifyResult,
    canonical,
    chain_hash,
    verify_chain,
)

ID1 = UUID("11111111-1111-1111-1111-111111111111")
USER = UUID("00000000-0000-0000-0000-000000000001")
AT = datetime(2026, 10, 21, 15, 4, 5, 123456, tzinfo=UTC)


class Accion(Enum):
    INSERT = "insert"


def _fila(seq: int, prev_hash: str, **cambios: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": UUID(int=seq),
        "seq": seq,
        "at": AT + timedelta(seconds=seq),
        "user_id": USER,
        "action": "insert",
        "table_name": "members.members",
        "record_id": ID1,
        "before": None,
        "after": {"n": seq},
        "prev_hash": prev_hash,
    }
    base.update(cambios)
    base["hash"] = chain_hash(prev_hash, base)
    base["created_at"] = base["at"]
    base["updated_at"] = base["at"]
    base["created_by"] = base["user_id"]
    return base


def _cadena(n: int) -> list[dict[str, object]]:
    filas: list[dict[str, object]] = []
    prev = ZERO_HASH
    for seq in range(1, n + 1):
        fila = _fila(seq, prev)
        filas.append(fila)
        prev = str(fila["hash"])
    return filas


# canonical ---------------------------------------------------------------------


def test_canonical_es_independiente_del_orden_de_claves() -> None:
    a = canonical({"b": 1, "a": {"y": 2, "x": 1}})
    b = canonical({"a": {"x": 1, "y": 2}, "b": 1})
    assert a == b == b'{"a":{"x":1,"y":2},"b":1}'


def test_canonical_fechas_en_utc_con_z_y_seis_decimales() -> None:
    bogota = datetime(2026, 10, 21, 10, 4, 5, 123456, tzinfo=timezone(timedelta(hours=-5)))
    assert canonical({"at": bogota}) == b'{"at":"2026-10-21T15:04:05.123456Z"}'
    assert canonical({"at": datetime(2026, 1, 1, tzinfo=UTC)}) == b'{"at":"2026-01-01T00:00:00.000000Z"}'
    assert canonical({"d": date(2026, 2, 3)}) == b'{"d":"2026-02-03"}'


def test_canonical_uuid_none_bool_y_unicode() -> None:
    assert canonical({"id": UUID("ABCDEF01-0000-0000-0000-000000000000")}) == (
        b'{"id":"abcdef01-0000-0000-0000-000000000000"}'
    )
    assert canonical({"x": None, "y": True, "z": "ñandú á"}) == (
        '{"x":null,"y":true,"z":"ñandú á"}'.encode()
    )
    assert canonical({"e": Accion.INSERT, "l": [1, "a", None]}) == b'{"e":"insert","l":[1,"a",null]}'


@pytest.mark.parametrize(
    "valor",
    [datetime(2026, 1, 1), 1.5, Decimal("1.5"), b"bytes", object()],
    ids=["datetime-ingenuo", "float", "decimal", "bytes", "objeto"],
)
def test_canonical_rechaza_tipos_sin_representacion(valor: object) -> None:
    with pytest.raises(CanonicalError):
        canonical({"v": valor})


# chain_hash ---------------------------------------------------------------------


def test_chain_hash_determinista_y_solo_sobre_las_claves_del_hash() -> None:
    fila = _fila(1, ZERO_HASH)
    assert chain_hash(ZERO_HASH, fila) == chain_hash(ZERO_HASH, dict(reversed(list(fila.items()))))
    assert len(chain_hash(ZERO_HASH, fila)) == 64
    sin_espejo = {k: fila[k] for k in HASHED_KEYS}
    assert chain_hash(ZERO_HASH, sin_espejo) == chain_hash(ZERO_HASH, fila)
    assert chain_hash(ZERO_HASH, {**fila, "after": {"n": 2}}) != chain_hash(ZERO_HASH, fila)
    assert chain_hash("1" * 64, fila) != chain_hash(ZERO_HASH, fila)


# verify_chain -------------------------------------------------------------------


def test_verify_chain_vacia_y_de_una_fila() -> None:
    assert verify_chain([]) == VerifyResult(ok=True, rows_checked=0, broken_at_seq=None)
    assert verify_chain(_cadena(1)) == VerifyResult(ok=True, rows_checked=1, broken_at_seq=None)


def test_verify_chain_valida_cinco_filas() -> None:
    assert verify_chain(_cadena(5)) == VerifyResult(ok=True, rows_checked=5, broken_at_seq=None)


@pytest.mark.parametrize("seq_alterado", [1, 3, 5], ids=["inicio", "medio", "final"])
def test_verify_chain_detecta_after_alterado(seq_alterado: int) -> None:
    filas = _cadena(5)
    filas[seq_alterado - 1] = {**filas[seq_alterado - 1], "after": {"n": 99}}
    resultado = verify_chain(filas)
    assert resultado.ok is False
    assert resultado.broken_at_seq == seq_alterado


def test_verify_chain_detecta_salto_de_seq() -> None:
    filas = _cadena(4)
    del filas[1]  # faltan la 2: la 3 no sigue a la 1 (N-30)
    assert verify_chain(filas).broken_at_seq == 3
    assert verify_chain(_cadena(2)[1:]).broken_at_seq == 2  # empieza en 2, no en 1


def test_verify_chain_detecta_prev_hash_cambiado() -> None:
    filas = _cadena(3)
    filas[2] = {**filas[2], "prev_hash": "a" * 64}
    assert verify_chain(filas) == VerifyResult(ok=False, rows_checked=3, broken_at_seq=3)


def test_verify_chain_detecta_columna_espejo_alterada() -> None:
    filas = _cadena(3)
    filas[1] = {**filas[1], "created_by": UUID(int=99)}
    assert verify_chain(filas).broken_at_seq == 2
    filas = _cadena(3)
    filas[1] = {**filas[1], "updated_at": AT + timedelta(days=1)}
    assert verify_chain(filas).broken_at_seq == 2

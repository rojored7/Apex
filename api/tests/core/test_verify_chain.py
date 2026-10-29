"""`verify_chain` ampliada con continuación (S4A-B3, US-104; S4A-D11).

Puras, sin base. Firma: `verify_chain(rows, *, start_prev_hash=ZERO_HASH, start_seq=1)`;
`VerifyResult(ok, rows_checked, broken_at_seq, last_seq=None, last_hash=None)`. `broken_at_seq` es
el `seq` de la PRIMERA fila que no encaja (si falta la 3, es la 4); `rows_checked` cuenta hasta la
ruptura, incluida; `last_seq`/`last_hash` son los de la última fila verificada en orden (la que
rompe incluida) o `None` sin filas. Los valores esperados se calculan con la misma `chain_hash` de
`core/audit.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.core.audit import ZERO_HASH, VerifyResult, chain_hash, verify_chain

USER = UUID("00000000-0000-0000-0000-000000000001")
OTRO = UUID("00000000-0000-0000-0000-0000000000aa")
AT = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)


def _fila(seq: int, prev_hash: str) -> dict[str, object]:
    fila: dict[str, object] = {
        "id": UUID(int=seq),
        "seq": seq,
        "at": AT + timedelta(seconds=seq),
        "user_id": USER,
        "action": "insert",
        "table_name": "members.members",
        "record_id": UUID(int=10_000 + seq),
        "before": None,
        "after": {"n": seq},
        "prev_hash": prev_hash,
    }
    fila["hash"] = chain_hash(prev_hash, fila)
    fila["created_at"] = fila["at"]
    fila["updated_at"] = fila["at"]
    fila["created_by"] = fila["user_id"]
    return fila


def _cadena(n: int) -> list[dict[str, object]]:
    filas: list[dict[str, object]] = []
    prev = ZERO_HASH
    for seq in range(1, n + 1):
        filas.append(_fila(seq, prev))
        prev = str(filas[-1]["hash"])
    return filas


def test_la_firma_conserva_la_construccion_posicional() -> None:
    assert VerifyResult(True, 0, None) == VerifyResult(
        ok=True, rows_checked=0, broken_at_seq=None, last_seq=None, last_hash=None
    )


def test_cadena_vacia_sin_ultima_fila() -> None:
    assert verify_chain([]) == VerifyResult(True, 0, None, None, None)


def test_una_fila_da_su_seq_y_su_hash() -> None:
    filas = _cadena(1)
    assert verify_chain(filas) == VerifyResult(True, 1, None, 1, str(filas[0]["hash"]))


def test_integra_de_50() -> None:
    filas = _cadena(50)
    assert verify_chain(filas) == VerifyResult(True, 50, None, 50, str(filas[-1]["hash"]))


@pytest.mark.parametrize("seq", [1, 25, 50], ids=["primera", "del_medio", "ultima"])
def test_fila_alterada_rompe_en_esa_fila(seq: int) -> None:
    filas = _cadena(50)
    filas[seq - 1]["after"] = {"n": -1}
    resultado = verify_chain(filas)
    assert (resultado.ok, resultado.broken_at_seq, resultado.rows_checked) == (False, seq, seq)
    assert resultado.last_seq == seq


def test_fila_borrada_reporta_el_seq_siguiente() -> None:
    filas = _cadena(10)
    del filas[2]  # falta la 3
    resultado = verify_chain(filas)
    assert (resultado.ok, resultado.broken_at_seq, resultado.rows_checked) == (False, 4, 3)


def test_prev_hash_manipulado() -> None:
    filas = _cadena(5)
    filas[3]["prev_hash"] = "f" * 64
    assert verify_chain(filas).broken_at_seq == 4


def test_columna_espejo_distinta() -> None:
    filas = _cadena(5)
    filas[1]["created_by"] = OTRO
    assert verify_chain(filas).broken_at_seq == 2


def test_dos_lotes_con_continuacion_dan_lo_mismo_que_una_vez() -> None:
    filas = _cadena(30)
    entera = verify_chain(filas)
    primero = verify_chain(filas[:12])
    assert primero == VerifyResult(True, 12, None, 12, str(filas[11]["hash"]))
    assert primero.last_hash is not None and primero.last_seq is not None
    segundo = verify_chain(
        filas[12:], start_prev_hash=primero.last_hash, start_seq=primero.last_seq + 1
    )
    assert segundo == VerifyResult(True, 18, None, 30, str(filas[-1]["hash"]))
    assert (entera.last_seq, entera.last_hash) == (segundo.last_seq, segundo.last_hash)


def test_la_continuacion_detecta_la_ruptura_en_el_borde_del_lote() -> None:
    """Si falta la primera fila del lote siguiente (la 13), la ruptura es la 14."""
    filas = _cadena(20)
    primero = verify_chain(filas[:12])
    assert primero.last_hash is not None
    resultado = verify_chain(filas[13:], start_prev_hash=primero.last_hash, start_seq=13)
    assert (resultado.ok, resultado.broken_at_seq, resultado.rows_checked) == (False, 14, 1)


def test_la_continuacion_con_prev_hash_equivocado_rompe_en_la_primera() -> None:
    filas = _cadena(20)
    resultado = verify_chain(filas[10:], start_prev_hash=ZERO_HASH, start_seq=11)
    assert (resultado.ok, resultado.broken_at_seq) == (False, 11)


def test_sin_continuacion_un_lote_que_no_empieza_en_1_rompe() -> None:
    """Los valores por defecto exigen empezar en 1 con `ZERO_HASH` (la semántica de US-015)."""
    assert verify_chain(_cadena(20)[10:]).broken_at_seq == 11

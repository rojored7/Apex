"""`aggregate_ops`: agrupa las `ok` por llave de agregación y conserva los errores (US-029 T9)."""

from __future__ import annotations

from uuid import UUID, uuid4

from app.core.crypto.oplog import OpRow, aggregate_ops

USER = UUID(int=1)
LOTE = UUID(int=9)
K1, K2 = UUID(int=11), UUID(int=12)


def _op(**cambios: object) -> OpRow:
    base: dict[str, object] = {
        "verb": "decrypt",
        "data_class": "member.document",
        "key_id": K1,
        "key_version": 1,
        "record_id": uuid4(),
        "purpose": "mask",
        "result": "ok",
        "user_id": USER,
        "batch_id": LOTE,
    }
    base.update(cambios)
    return OpRow(**base)  # type: ignore[arg-type]


def test_500_descifrados_de_la_misma_llave_dan_una_fila() -> None:
    [fila] = aggregate_ops(_op() for _ in range(500))
    assert fila.count == 500 and fila.record_id is None
    assert (fila.verb, fila.data_class, fila.key_id, fila.key_version, fila.purpose) == (
        "decrypt",
        "member.document",
        K1,
        1,
        "mask",
    )
    assert fila.user_id == USER and fila.batch_id == LOTE


def test_dos_llaves_y_dos_propositos_separan_filas() -> None:
    filas = aggregate_ops([_op(), _op(key_id=K2), _op(), _op(purpose="reveal"), _op(key_id=K2)])
    assert sorted((f.key_id, f.purpose, f.count) for f in filas) == [
        (K1, "mask", 2),
        (K1, "reveal", 1),
        (K2, "mask", 2),
    ]


def test_los_errores_quedan_en_fila_propia_con_su_record_id() -> None:
    r1, r2 = uuid4(), uuid4()
    filas = aggregate_ops(
        [_op(), _op(result="error", record_id=r1), _op(result="error", record_id=r2), _op()]
    )
    errores = [f for f in filas if f.result == "error"]
    assert {f.record_id for f in errores} == {r1, r2} and all(f.count == 1 for f in errores)
    [ok] = [f for f in filas if f.result == "ok"]
    assert ok.count == 2


def test_vacio() -> None:
    assert aggregate_ops([]) == []

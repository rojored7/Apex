"""`Secret` nunca muestra su valor; `canonical_json` es estable (US-028 T9)."""

from __future__ import annotations

import json
import pickle
from datetime import date
from typing import Any

import pytest
from pydantic import BaseModel

from app.core.crypto.secret import Secret, canonical_json

VALOR = "1020304-muy-secreto"


def test_repr_str_y_json_no_muestran_el_valor() -> None:
    pendiente = Secret.from_plain(VALOR)
    sellado = Secret.from_blob("apx1.k.A256GCM.n.c")
    for s in (pendiente, sellado):
        assert repr(s) == str(s) == "Secret(•••)"
        assert VALOR not in repr(s) and "apx1" not in repr(s)
        with pytest.raises(TypeError):
            json.dumps(s)
        with pytest.raises(TypeError):
            json.dumps({"x": s})
        with pytest.raises(TypeError):
            pickle.dumps(s)


def test_pydantic_no_lo_serializa() -> None:
    class Salida(BaseModel):
        model_config = {"arbitrary_types_allowed": True}
        dato: Any

    modelo = Salida(dato=Secret.from_plain(VALOR))
    assert VALOR not in repr(modelo.model_dump())
    with pytest.raises(Exception, match="Secret"):
        modelo.model_dump_json()


def test_estados_e_igualdad() -> None:
    pendiente = Secret.from_plain(VALOR)
    assert pendiente.is_sealed is False
    with pytest.raises(ValueError, match="sellado"):
        _ = pendiente.blob
    sellado = Secret.from_blob("apx1.k.A256GCM.n.c")
    assert sellado.is_sealed is True and sellado.blob == "apx1.k.A256GCM.n.c"
    assert sellado == Secret.from_blob("apx1.k.A256GCM.n.c")
    assert sellado != Secret.from_blob("apx1.k.A256GCM.n.d")
    assert pendiente != Secret.from_plain(VALOR)  # los pendientes nunca se comparan
    assert pendiente != sellado
    assert hash(sellado) == hash(Secret.from_blob("apx1.k.A256GCM.n.c"))


def test_from_plain_acepta_str_date_y_dict() -> None:
    for valor in (VALOR, date(2000, 1, 2), {"name": "Ana", "phone": "300"}):
        assert Secret.from_plain(valor).is_sealed is False
    with pytest.raises(TypeError):
        Secret.from_plain(123)  # type: ignore[arg-type]


def test_canonical_json_ordena_y_es_estable() -> None:
    a = canonical_json({"phone": "300", "name": "Ñandú"})
    b = canonical_json({"name": "Ñandú", "phone": "300"})
    assert a == b == '{"name":"Ñandú","phone":"300"}'

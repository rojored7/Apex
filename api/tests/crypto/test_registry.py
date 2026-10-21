"""Registro de clases de dato de v0.1 (US-025 T9; N-04, N-02)."""

from __future__ import annotations

import pytest

from app.core.crypto.errors import CryptoError
from app.core.crypto.registry import REGISTRY, DataClassSpec, get_spec, override_registry

ESPERADAS = {
    "member.document": ("str", "generic"),
    "member.phone": ("str", "phone"),
    "member.email": ("str", "email"),
    "member.birth_date": ("date", None),
    "member.emergency_contact": ("json", None),
}


def test_las_cinco_clases_de_v01() -> None:
    assert set(REGISTRY) == set(ESPERADAS)
    for nombre, (tipo, indice) in ESPERADAS.items():
        spec = get_spec(nombre)
        assert spec.name == nombre and spec.encrypt is True and spec.sign is False
        assert (spec.value_type, spec.index_kind) == (tipo, indice)
        assert spec.columns and all(c.count(".") == 2 for c in spec.columns)
        assert all(c.startswith("members.members.") for c in spec.columns)


def test_clase_desconocida() -> None:
    with pytest.raises(CryptoError) as excinfo:
        get_spec("member.foo")
    assert excinfo.value.code == "unknown_data_class"
    assert "data_class desconocida" in str(excinfo.value)


def test_override_solo_para_pruebas() -> None:
    extra = DataClassSpec("test.secret", True, None, False, "str", ("worker.t.secret",))
    with override_registry({**REGISTRY, "test.secret": extra}):
        assert get_spec("test.secret") is extra
    with pytest.raises(CryptoError):
        get_spec("test.secret")

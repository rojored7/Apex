"""Registro de clases de dato de v0.1 (US-025 T9; N-04, N-02)."""

from __future__ import annotations

import pytest

from app.core.crypto.errors import CryptoError
from app.core.crypto.registry import (
    REGISTRY,
    DataClassSpec,
    encrypting_specs,
    get_spec,
    indexing_specs,
    override_registry,
    signing_specs,
)

ESPERADAS = {
    "member.document": ("str", "generic"),
    "member.phone": ("str", "phone"),
    "member.email": ("str", "email"),
    "member.birth_date": ("date", None),
    "member.emergency_contact": ("json", None),
}


SIN_LLAVE = {"kek.backup"}
"""Clases sin llave (S4B-D85): nombran las filas de `crypto_ops` del respaldo de la KEK."""
DE_FIRMA = {"audit.signature"}
"""S6-D40: clase de firma de la cadena; su fila `sign` la crea `init-keys` (D72)."""
DE_ADJUNTOS = {"attachment.sensitive"}
DE_MEDIDAS = {"athlete.metric"}
"""S6-C1 (S6-D25): cifrado de los adjuntos sensibles; el blob vive en el objeto, sin columnas."""


def test_las_cinco_clases_de_v01() -> None:
    assert set(REGISTRY) == set(ESPERADAS) | SIN_LLAVE | DE_FIRMA | DE_ADJUNTOS | DE_MEDIDAS
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


def test_kek_backup_es_una_clase_sin_llave() -> None:
    spec = get_spec("kek.backup")
    assert spec.name == "kek.backup"
    assert (spec.encrypt, spec.index_kind, spec.sign) == (False, None, False)
    assert spec.columns == ()


def test_kek_backup_no_entra_en_las_listas_que_crean_llaves() -> None:
    for lista in (encrypting_specs(), indexing_specs(), signing_specs()):
        assert "kek.backup" not in {s.name for s in lista}
    assert {s.name for s in encrypting_specs()} == set(ESPERADAS) | DE_ADJUNTOS | DE_MEDIDAS


def test_audit_signature_es_una_clase_de_firma_sin_columnas_ni_cifrado() -> None:
    """S6-D40: sin cifrado, índice ni columnas; `sign=True`; solo entra a `signing_specs`."""
    spec = get_spec("audit.signature")
    assert (spec.encrypt, spec.index_kind, spec.sign) == (False, None, True)
    assert spec.columns == ()
    assert "audit.signature" in {s.name for s in signing_specs()}
    assert "audit.signature" not in {s.name for s in encrypting_specs()}
    assert "audit.signature" not in {s.name for s in indexing_specs()}


def test_attachment_sensitive_cifra_sin_indice_sin_firma_y_sin_columnas() -> None:
    """S6-D25: `encrypt=True`, `index_kind=None`, `sign=False`, `value_type="str"`, `columns=()`.
    Entra a `encrypting_specs` (su DEK la crea `ensure_keys`) y no a las de índice ni firma."""
    spec = get_spec("attachment.sensitive")
    assert (spec.encrypt, spec.index_kind, spec.sign, spec.value_type) == (True, None, False, "str")
    assert spec.columns == ()
    assert "attachment.sensitive" in {s.name for s in encrypting_specs()}
    assert "attachment.sensitive" not in {s.name for s in indexing_specs()}
    assert "attachment.sensitive" not in {s.name for s in signing_specs()}


def test_athlete_metric_cifra_cuatro_columnas_sin_indice_sin_firma() -> None:
    """S9-A1 (S9-D4, S9-D5): `encrypt=True`, `index_kind=None`, `sign=False`, `value_type="str"` y
    las cuatro columnas de `athletes.body_metrics` (en el orden del contrato). Entra a
    `encrypting_specs` (su DEK la crea `ensure_keys`) y no a las de índice ni firma."""
    spec = get_spec("athlete.metric")
    assert (spec.encrypt, spec.index_kind, spec.sign, spec.value_type) == (True, None, False, "str")
    assert spec.columns == (
        "athletes.body_metrics.weight_g",
        "athletes.body_metrics.height_cm",
        "athletes.body_metrics.body_fat_pct",
        "athletes.body_metrics.notes",
    )
    assert "athlete.metric" in {s.name for s in encrypting_specs()}
    assert "athlete.metric" not in {s.name for s in indexing_specs()}
    assert "athlete.metric" not in {s.name for s in signing_specs()}

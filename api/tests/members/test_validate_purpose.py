"""`members.service.validate_purpose` (S4A-B6, US-077; S4A-D21): pura, sin base.

Solo `notify` y `auth_link` son propósitos del contacto para avisos; `mask`, `reveal` y `export`
existen en `OP_PURPOSES` pero no sirven aquí, y cualquier otro valor (también vacío, con
espacios, en mayúsculas o `None`) lanza `InvalidPurpose` (`MemberError`, `invalid_purpose`).
"""

from __future__ import annotations

import pytest

from app.core.crypto.models import OP_PURPOSES
from app.modules.members import service
from app.modules.members.exceptions import InvalidPurpose, MemberError


@pytest.mark.parametrize("proposito", ["notify", "auth_link"])
def test_notify_y_auth_link_son_validos_y_se_devuelven_tal_cual(proposito: str) -> None:
    assert service.validate_purpose(proposito) == proposito


@pytest.mark.parametrize(
    "proposito",
    ["marketing", "mask", "reveal", "export", "", " notify", "NOTIFY", "notify ", None, 1],
)
def test_cualquier_otro_proposito_da_invalid_purpose(proposito: object) -> None:
    with pytest.raises(InvalidPurpose) as error:
        service.validate_purpose(proposito)
    assert error.value.code == "invalid_purpose"
    assert isinstance(error.value, MemberError)


def test_los_dos_validos_estan_en_op_purposes() -> None:
    """Sin migración: la restricción de `crypto_ops.purpose` ya acepta los dos (S4A-D21)."""
    assert {"notify", "auth_link"} <= set(OP_PURPOSES)


def test_las_excepciones_tienen_su_codigo_y_heredan_de_member_error() -> None:
    assert issubclass(service.InvalidPurpose, MemberError)
    assert issubclass(service.MemberNotContactable, MemberError)
    assert service.InvalidPurpose().code == "invalid_purpose"
    assert service.MemberNotContactable().code == "member_not_contactable"


def test_el_mensaje_de_invalid_purpose_no_repite_el_valor_recibido() -> None:
    with pytest.raises(InvalidPurpose) as error:
        service.validate_purpose("marketing-3001234567")
    assert "3001234567" not in str(error.value)
    assert "marketing" not in error.value.message

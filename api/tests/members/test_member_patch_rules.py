"""Reglas puras de la edición del socio (S3-B10; US-075; D21, M-3, S3-D46).

`diff_fields(before, patch) -> frozenset[str]`:
- `before` es el estado actual en claro (los nombres de `MemberPatch` salvo `data_consent`; una
  clave ausente vale `None`); solo cuentan los campos de `patch.model_fields_set`;
- documento, teléfono y correo se comparan normalizados (N-02): un cambio solo de formato no
  cuenta (`"300 123 4567"` frente a `"3001234567"`, `"7.319.582.046"` frente a `"7319582046"`);
- `null` sobre un opcional con valor cuenta como cambio; `null` sobre uno vacío no;
- `data_consent` no se compara aquí (lo decide `update` con `data_consent_at`).

`ensure_can_change(set_fields, role)` por PRESENCIA (M-3): un coach con `document` o
`document_type` en el cuerpo, aunque sea el mismo valor, recibe `MemberFieldForbidden` (403
`forbidden_field`, `field` = el campo); el admin pasa; un coach sin ninguno de los dos pasa.

`MemberPatch` (S3-D46): los diez campos exactos; `status`, `deleted_at` y `data_consent_at` dan
error de validación; `null` en nombres, documento, tipo o autorización también.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from app.modules.members import service
from app.modules.members.exceptions import MemberFieldForbidden
from app.modules.members.schemas import MemberCreate, MemberPatch

ANTES: dict[str, Any] = {
    "first_name": "Lucía",
    "last_name": "Gómez",
    "sex": "f",
    "document_type": "CC",
    "document": "7319582046",
    "phone": "3001234567",
    "email": "lucia.gomez@correo.co",
    "birth_date": date(1991, 7, 23),
    "emergency_contact": {"name": "Rosa", "phone": "3115550199"},
}

DIEZ_CAMPOS = {
    "first_name",
    "last_name",
    "sex",
    "birth_date",
    "phone",
    "email",
    "emergency_contact",
    "document",
    "document_type",
    "data_consent",
}


def _patch(**campos: Any) -> MemberPatch:
    return MemberPatch.model_validate(campos)


# diff_fields --------------------------------------------------------------------------------


def test_un_patch_vacio_no_cambia_nada() -> None:
    assert service.diff_fields(ANTES, _patch()) == frozenset()


def test_los_mismos_valores_no_cambian_nada() -> None:
    igual = _patch(
        first_name="Lucía",
        last_name="Gómez",
        sex="f",
        document_type="CC",
        document="7319582046",
        phone="3001234567",
        email="lucia.gomez@correo.co",
        birth_date="1991-07-23",
        emergency_contact={"name": "Rosa", "phone": "3115550199"},
    )
    assert service.diff_fields(ANTES, igual) == frozenset()


def test_un_cambio_devuelve_solo_ese_campo() -> None:
    assert service.diff_fields(ANTES, _patch(first_name="Lucy", last_name="Gómez")) == {
        "first_name"
    }


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("phone", "300 123 4567"),
        ("phone", "+57 300 123 4567"),
        ("phone", "300-123-4567"),
        ("document", "7.319.582.046"),
        ("document", "7 319 582 046"),
        ("email", "LUCIA.Gomez@correo.co"),
    ],
    ids=[
        "telefono-con-espacios",
        "telefono-con-prefijo",
        "telefono-con-guiones",
        "documento-con-puntos",
        "documento-con-espacios",
        "correo-en-mayusculas",
    ],
)
def test_un_cambio_solo_de_formato_no_cuenta(campo: str, valor: str) -> None:
    assert service.diff_fields(ANTES, _patch(**{campo: valor})) == frozenset()


def test_otro_numero_si_cuenta() -> None:
    assert service.diff_fields(ANTES, _patch(phone="300 123 4568")) == {"phone"}
    assert service.diff_fields(ANTES, _patch(document="7319582047")) == {"document"}
    assert service.diff_fields(ANTES, _patch(email="lucia@correo.co")) == {"email"}


@pytest.mark.parametrize("campo", ["phone", "email", "birth_date", "emergency_contact", "sex"])
def test_null_sobre_un_opcional_con_valor_cuenta(campo: str) -> None:
    assert service.diff_fields(ANTES, _patch(**{campo: None})) == {campo}


@pytest.mark.parametrize("campo", ["phone", "email", "birth_date", "emergency_contact", "sex"])
def test_null_sobre_un_opcional_vacio_no_cuenta(campo: str) -> None:
    vacio = {**ANTES, campo: None}
    assert service.diff_fields(vacio, _patch(**{campo: None})) == frozenset()


def test_una_clave_ausente_en_before_vale_none() -> None:
    sin_correo = {k: v for k, v in ANTES.items() if k != "email"}
    assert service.diff_fields(sin_correo, _patch(email="nuevo@correo.co")) == {"email"}
    assert service.diff_fields(sin_correo, _patch(email=None)) == frozenset()


def test_contacto_de_emergencia_y_tipo_de_documento() -> None:
    contacto = {"name": "Rosa", "phone": "3115550199", "relationship": "madre"}
    assert service.diff_fields(ANTES, _patch(emergency_contact=contacto)) == {"emergency_contact"}
    assert service.diff_fields(ANTES, _patch(document_type="CE")) == {"document_type"}
    assert service.diff_fields(ANTES, _patch(birth_date="1991-07-24")) == {"birth_date"}


def test_varios_cambios_a_la_vez() -> None:
    patch = _patch(first_name="Lucy", phone="3109998877", email="lucia.gomez@correo.co")
    assert service.diff_fields(ANTES, patch) == {"first_name", "phone"}


def test_data_consent_no_se_compara_en_diff_fields() -> None:
    assert service.diff_fields(ANTES, _patch(data_consent=True)) == frozenset()


def test_diff_fields_devuelve_un_frozenset() -> None:
    assert isinstance(service.diff_fields(ANTES, _patch(first_name="Lucy")), frozenset)


# ensure_can_change (M-3: por presencia) -----------------------------------------------------


def test_admin_only_fields_son_documento_y_tipo() -> None:
    assert service.ADMIN_ONLY_FIELDS == frozenset({"document", "document_type"})


@pytest.mark.parametrize(
    ("campos", "campo_prohibido"),
    [
        ({"document"}, "document"),
        ({"document_type"}, "document_type"),
        ({"phone", "document"}, "document"),
        ({"document", "document_type"}, "document"),
    ],
    ids=["documento", "tipo", "telefono-y-documento", "documento-y-tipo"],
)
def test_el_coach_con_documento_o_tipo_presente_recibe_403(
    campos: set[str], campo_prohibido: str
) -> None:
    with pytest.raises(MemberFieldForbidden) as error:
        service.ensure_can_change(frozenset(campos), "coach")
    assert (error.value.status, error.value.code) == (403, "forbidden_field")
    assert error.value.field == campo_prohibido


def test_el_coach_con_el_mismo_documento_tambien_recibe_403() -> None:
    """M-3: decide la presencia, no el valor (sin oráculo de igualdad para el coach)."""
    igual = _patch(document=ANTES["document"])
    with pytest.raises(MemberFieldForbidden):
        service.ensure_can_change(igual.model_fields_set, "coach")
    mismo_tipo = _patch(document_type="CC")
    with pytest.raises(MemberFieldForbidden):
        service.ensure_can_change(mismo_tipo.model_fields_set, "coach")


def test_el_admin_puede_cambiar_documento_y_tipo() -> None:
    assert service.ensure_can_change(frozenset({"document", "document_type"}), "admin") is None


def test_el_coach_sin_documento_ni_tipo_pasa() -> None:
    campos = frozenset(DIEZ_CAMPOS - {"document", "document_type"})
    assert service.ensure_can_change(campos, "coach") is None
    assert service.ensure_can_change(frozenset(), "coach") is None


def test_el_mensaje_no_repite_el_valor() -> None:
    with pytest.raises(MemberFieldForbidden) as error:
        service.ensure_can_change(_patch(document="99887766").model_fields_set, "coach")
    assert "99887766" not in error.value.message


# MemberPatch (S3-D46) -----------------------------------------------------------------------


def test_member_patch_tiene_exactamente_los_diez_campos() -> None:
    assert set(MemberPatch.model_fields) == DIEZ_CAMPOS


@pytest.mark.parametrize(
    "campo", ["status", "deleted_at", "data_consent_at", "notes", "id", "document_idx"]
)
def test_member_patch_rechaza_los_campos_que_no_son_suyos(campo: str) -> None:
    with pytest.raises(ValidationError) as error:
        MemberPatch.model_validate({campo: "x"})
    assert error.value.errors()[0]["loc"] == (campo,)


@pytest.mark.parametrize(
    "campo", ["first_name", "last_name", "document", "document_type", "data_consent"]
)
def test_null_en_un_campo_obligatorio_es_invalido(campo: str) -> None:
    with pytest.raises(ValidationError) as error:
        MemberPatch.model_validate({campo: None})
    assert error.value.errors()[0]["loc"] == (campo,)


def test_null_en_un_opcional_es_valido_y_queda_en_fields_set() -> None:
    patch = MemberPatch.model_validate({"phone": None, "sex": None})
    assert patch.model_fields_set == {"phone", "sex"}
    assert patch.phone is None and patch.sex is None


def test_data_consent_es_estricto() -> None:
    with pytest.raises(ValidationError):
        MemberPatch.model_validate({"data_consent": "true"})
    assert MemberPatch.model_validate({"data_consent": False}).data_consent is False


def test_el_telefono_del_contacto_rechaza_controles() -> None:
    """S3-D46 (M-3, punto 3): `emergency_contact.phone` es `SafeText`."""
    with pytest.raises(ValidationError) as error:
        MemberPatch.model_validate({"emergency_contact": {"name": "Rosa", "phone": "311\x00555"}})
    assert error.value.errors()[0]["loc"] == ("emergency_contact", "phone")


# Revisión de seguridad del Verde (LOW-1): documento y teléfono son `SafeText` -------------------

NUL = chr(0x00)
RLO = chr(0x202E)  # anulación bidireccional de derecha a izquierda


@pytest.mark.parametrize("campo", ["document", "phone"])
@pytest.mark.parametrize("control", [NUL, RLO], ids=["nul", "rlo"])
def test_documento_y_telefono_rechazan_controles_en_patch_y_alta(campo: str, control: str) -> None:
    valor = f"300{control}1234567"
    with pytest.raises(ValidationError) as error:
        MemberPatch.model_validate({campo: valor})
    assert error.value.errors()[0]["loc"] == (campo,)
    alta = {"first_name": "Ana", "last_name": "Ruiz", "document": "1020304417", campo: valor}
    with pytest.raises(ValidationError) as error_alta:
        MemberCreate.model_validate(alta)
    assert error_alta.value.errors()[0]["loc"] == (campo,)

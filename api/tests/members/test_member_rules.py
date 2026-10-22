"""Reglas puras de socios y contrato de `MemberCreate` (S2-B7, US-069; M-4, M-5, L-3).

- `validate_member_input(data, today)`: nombres no vacíos, `sex` en `f`/`m`/`x` o nulo,
  `birth_date <= today`, y documento, teléfono o correo que no se normalicen a vacío (L-3; el
  teléfono `"+57"` solo trae el prefijo del país y tampoco sirve). Lanza `MemberValidationError`
  (422, `validation_error`) con `field` y sin repetir el valor.
- `compute_warnings(data)`: `["data_consent_missing"]` sin autorización, `[]` con ella.
- `mask(field, value, *, document_type=None)`: en memoria, nunca sobre el blob.
- `MemberCreate`: `extra="forbid"` (ni `notes`, M-5, ni `data_consent_at`, M-4),
  `data_consent: bool = False`, `document_type = "CC"`, correo normalizado.
Las pruebas de `validate_member_input` aplican los cambios con `model_copy(update=...)` para
llegar a la regla aunque el schema ya rechazaría el valor.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from app.modules.members.exceptions import MemberValidationError
from app.modules.members.schemas import MemberCreate
from app.modules.members.service import compute_warnings, mask, validate_member_input
from tests.members._apoyo import cuerpo

HOY = date(2026, 10, 21)  # `T0` en Bogotá
GUIONES_TIPOGRAFICOS = "".join(map(chr, (0x2010, 0x2011, 0x2012)))


def _sin_validar(**cambios: Any) -> MemberCreate:
    """Entrada válida con `cambios` aplicados sin pasar por el schema (`model_copy`)."""
    return MemberCreate.model_validate(cuerpo()).model_copy(update=cambios)


def _campo_rechazado(data: MemberCreate) -> str | None:
    with pytest.raises(MemberValidationError) as error:
        validate_member_input(data, HOY)
    assert error.value.status == 422
    assert error.value.code == "validation_error"
    return error.value.field


# validate_member_input ---------------------------------------------------------------------


def test_una_entrada_completa_y_valida_pasa() -> None:
    validate_member_input(_sin_validar(), HOY)  # no lanza


def test_una_entrada_minima_pasa() -> None:
    minima = MemberCreate.model_validate(
        {"first_name": "Ana", "last_name": "Ruiz", "document": "1020304"}
    )
    validate_member_input(minima, HOY)  # no lanza


@pytest.mark.parametrize("campo", ["first_name", "last_name"])
@pytest.mark.parametrize("valor", ["", "   ", "\t\n"])
def test_nombres_vacios_o_en_blanco_dan_422_con_field(campo: str, valor: str) -> None:
    assert _campo_rechazado(_sin_validar(**{campo: valor})) == campo


@pytest.mark.parametrize("sexo", ["z", "F", "otro", ""])
def test_sexo_fuera_de_f_m_x_da_422(sexo: str) -> None:
    assert _campo_rechazado(_sin_validar(sex=sexo)) == "sex"


@pytest.mark.parametrize("sexo", ["f", "m", "x", None])
def test_sexo_valido_o_nulo_pasa(sexo: str | None) -> None:
    validate_member_input(_sin_validar(sex=sexo), HOY)  # no lanza


def test_fecha_de_nacimiento_futura_da_422() -> None:
    assert _campo_rechazado(_sin_validar(birth_date=HOY + timedelta(days=1))) == "birth_date"


def test_fecha_de_nacimiento_de_hoy_o_nula_pasa() -> None:
    validate_member_input(_sin_validar(birth_date=HOY), HOY)  # no lanza
    validate_member_input(_sin_validar(birth_date=None), HOY)  # no lanza


def test_fecha_de_nacimiento_anterior_a_1900_da_422() -> None:
    """LOW L6 de la revisión Python: tope inferior `1900-01-01` (un año mal tecleado, `0991`)."""
    assert _campo_rechazado(_sin_validar(birth_date=date(1899, 12, 31))) == "birth_date"
    assert _campo_rechazado(_sin_validar(birth_date=date(991, 7, 23))) == "birth_date"
    validate_member_input(_sin_validar(birth_date=date(1900, 1, 1)), HOY)  # no lanza


def test_hoy_es_el_que_recibe_no_el_reloj() -> None:
    """`today` viene de `today_bogota()` en el service; la regla no lee el reloj."""
    manana = HOY + timedelta(days=1)
    validate_member_input(_sin_validar(birth_date=manana), manana)  # no lanza


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("document", "..."),
        ("document", "- . -"),
        ("document", GUIONES_TIPOGRAFICOS),
        ("phone", "+57"),
        ("phone", "..."),
        ("phone", "   "),
        ("phone", "( ) -"),
        ("email", "   "),
    ],
)
def test_un_valor_que_se_normaliza_a_vacio_da_422_con_field(campo: str, valor: str) -> None:
    """L-3: sin esta regla el `before_flush` lanzaría `CryptoError("empty_value")` y un 500."""
    data = _sin_validar(**{campo: valor})
    with pytest.raises(MemberValidationError) as error:
        validate_member_input(data, HOY)
    assert error.value.field == campo
    assert valor.strip() == "" or valor not in error.value.message


@pytest.mark.parametrize("telefono", ["+57 300 765 4321", "3007654321", "(601) 555 0199"])
def test_telefonos_con_digitos_pasan(telefono: str) -> None:
    validate_member_input(_sin_validar(phone=telefono), HOY)  # no lanza


def test_el_documento_con_puntos_pasa() -> None:
    validate_member_input(_sin_validar(document="1.020.304"), HOY)  # no lanza


# compute_warnings ---------------------------------------------------------------------------


def test_sin_autorizacion_avisa_data_consent_missing() -> None:
    assert compute_warnings(_sin_validar(data_consent=False)) == ["data_consent_missing"]


def test_con_autorizacion_no_hay_avisos() -> None:
    assert compute_warnings(_sin_validar(data_consent=True)) == []


# mask ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "tipo", "esperado"),
    [
        ("1020304", "CC", "CC •••• 0304"),
        ("1.020.304", "CC", "CC •••• 0304"),
        ("7319582046", "CC", "CC •••• 2046"),
        ("1.020.304.417", "CE", "CE •••• 4417"),
        ("AB-123456", "PA", "PA •••• 3456"),
    ],
)
def test_mascara_del_documento(valor: str, tipo: str, esperado: str) -> None:
    assert mask("document", valor, document_type=tipo) == esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("300 123 4567", "••• ••• 4567"),
        ("3001234567", "••• ••• 4567"),
        ("+57 300 765 4321", "••• ••• 4321"),
    ],
)
def test_mascara_del_telefono(valor: str, esperado: str) -> None:
    assert mask("phone", valor) == esperado


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("lucia.gomez@correo.co", "l•••@•••.co"),
        ("ana@gym.com.co", "a•••@•••.co"),
        ("x@dominio.org", "x•••@•••.org"),
    ],
)
def test_mascara_del_correo(valor: str, esperado: str) -> None:
    assert mask("email", valor) == esperado


def test_mascara_de_la_fecha_deja_solo_el_anio() -> None:
    assert mask("birth_date", date(1991, 7, 23)) == "••/••/1991"


def test_mascara_del_contacto_de_emergencia() -> None:
    assert mask("emergency_contact", {"name": "Rosa", "phone": "3115550199"}) == "Registrado"


@pytest.mark.parametrize("campo", ["document", "phone", "email", "birth_date", "emergency_contact"])
def test_mascara_de_nulo_es_nulo(campo: Any) -> None:
    assert mask(campo, None) is None


def test_ninguna_mascara_contiene_el_valor_completo() -> None:
    salidas = [
        mask("document", "7319582046", document_type="CC"),
        mask("phone", "+57 300 765 4321"),
        mask("email", "lucia.gomez@correo.co"),
        mask("birth_date", date(1991, 7, 23)),
        mask("emergency_contact", {"name": "Rosa", "phone": "3115550199"}),
    ]
    texto = " ".join(s or "" for s in salidas)
    for prohibido in ("7319582046", "3007654321", "lucia", "gomez", "correo", "07/23", "Rosa"):
        assert prohibido not in texto, prohibido


# MemberCreate (contrato) -------------------------------------------------------------------


def test_member_create_tiene_defaults_de_tipo_y_autorizacion() -> None:
    data = MemberCreate.model_validate(
        {"first_name": " Ana ", "last_name": "Ruiz", "document": " 1020304 "}
    )
    assert data.document_type == "CC"
    assert data.data_consent is False
    assert data.first_name == "Ana" and data.document == "1020304"
    assert data.phone is None and data.email is None and data.emergency_contact is None


def test_member_create_normaliza_el_correo() -> None:
    assert entrada_correo("  Lucia.Gomez@Correo.CO ") == "lucia.gomez@correo.co"


def entrada_correo(correo: str) -> str | None:
    return MemberCreate.model_validate(cuerpo(email=correo)).email


@pytest.mark.parametrize(
    "extra",
    [
        {"notes": "lesión de rodilla"},
        {"data_consent_at": "2026-10-21T15:00:00Z"},
        {"data_consent_version": "v1"},
        {"status": "inactive"},
        {"document_idx": "abc"},
    ],
    ids=["notes", "data_consent_at", "data_consent_version", "status", "document_idx"],
)
def test_member_create_rechaza_campos_que_no_son_del_cliente(extra: dict[str, str]) -> None:
    """M-4 y M-5: ni la fecha de autorización ni las notas llegan desde el cliente."""
    with pytest.raises(ValidationError) as error:
        MemberCreate.model_validate(cuerpo(**extra))
    assert error.value.errors()[0]["type"] == "extra_forbidden"
    assert error.value.errors()[0]["loc"] == (next(iter(extra)),)


def test_member_create_no_declara_notes_ni_data_consent_at() -> None:
    assert "notes" not in MemberCreate.model_fields
    assert "data_consent_at" not in MemberCreate.model_fields
    assert MemberCreate.model_fields["data_consent"].annotation is bool


@pytest.mark.parametrize("tipo", ["CC", "CE", "TI", "PA"])
def test_member_create_acepta_los_cuatro_tipos_de_documento(tipo: str) -> None:
    assert MemberCreate.model_validate(cuerpo(document_type=tipo)).document_type == tipo


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"document_type": "NIT"}, "document_type"),
        ({"document": "12"}, "document"),
        ({"document": "1" * 31}, "document"),
        ({"sex": "z"}, "sex"),
        ({"email": "no-es-correo"}, "email"),
        ({"first_name": "   "}, "first_name"),
        ({"emergency_contact": {"name": "Rosa"}}, "emergency_contact"),
        ({"emergency_contact": {"name": "Rosa", "phone": "1", "otro": 1}}, "emergency_contact"),
    ],
)
def test_member_create_rechaza_valores_invalidos(cambios: dict[str, Any], campo: str) -> None:
    with pytest.raises(ValidationError) as error:
        MemberCreate.model_validate(cuerpo(**cambios))
    assert error.value.errors()[0]["loc"][0] == campo

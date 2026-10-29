"""`app.imports.members_xlsx`: cabecera, fila y enmascarado (S4B-B1, US-112; S4B-D34, D35; Q17).

Contrato (funciones puras):
- `validate_header(cells)`: exige las diez columnas de Q17, en ese orden exacto; si no,
  `HeaderError`;
- `parse_member_row(row_number, cells)` devuelve `MemberCreate` o `RowError(row, reason)`:
  documento `1020304.0` o `1.020.304` -> `1020304`; fecha AAAA-MM-DD estricta o celda de fecha;
  sexo `F`/`M`/`x` -> `f`/`m`/`x` (cualquier otro, rechazo); nombres o apellidos que empiezan por
  `=`, `+`, `-` o `@`, celdas de más de 200 caracteres, documento/nombres/apellidos vacíos y
  correo inválido se rechazan; contacto de emergencia incompleto -> socio sin contacto; `notas`
  se ignora; `data_consent` queda falso (Q16, S4B-D77);
- `RowError.reason` es una frase fija: nunca repite el valor de la celda (sin PII en reportes);
- `mask_document("1020304") == "•••304"`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.imports.members_xlsx import (
    TEMPLATE_HEADER,
    HeaderError,
    RowError,
    mask_document,
    parse_member_row,
    validate_header,
)
from app.modules.members.schemas import MemberCreate
from tests.factories.xlsx import fila_valida

ENCABEZADO_Q17 = [
    "documento",
    "nombres",
    "apellidos",
    "telefono",
    "correo",
    "fecha_nacimiento",
    "sexo",
    "contacto_emergencia_nombre",
    "contacto_emergencia_telefono",
    "notas",
]


def _socio(resultado: MemberCreate | RowError) -> MemberCreate:
    assert isinstance(resultado, MemberCreate), resultado
    return resultado


def _rechazo(resultado: MemberCreate | RowError) -> RowError:
    assert isinstance(resultado, RowError), resultado
    return resultado


# Cabecera -------------------------------------------------------------------------------------


def test_la_cabecera_de_la_plantilla_es_la_de_q17() -> None:
    assert list(TEMPLATE_HEADER) == ENCABEZADO_Q17


def test_cabecera_correcta_se_acepta() -> None:
    validate_header(list(ENCABEZADO_Q17))


@pytest.mark.parametrize(
    "cabecera",
    [
        [*ENCABEZADO_Q17[:4], "email", *ENCABEZADO_Q17[5:]],  # otro nombre
        [ENCABEZADO_Q17[0], ENCABEZADO_Q17[2], ENCABEZADO_Q17[1], *ENCABEZADO_Q17[3:]],  # orden
        ENCABEZADO_Q17[:-1],  # falta `notas`
        [*ENCABEZADO_Q17, "extra"],  # sobra una columna
        [None] * 10,  # hoja sin cabecera
        [c.upper() for c in ENCABEZADO_Q17],  # Q17 es exacta
    ],
    ids=["otro-nombre", "otro-orden", "falta-una", "sobra-una", "vacia", "mayusculas"],
)
def test_cabecera_distinta_se_rechaza(cabecera: list[object]) -> None:
    with pytest.raises(HeaderError):
        validate_header(cabecera)


# Fila válida ----------------------------------------------------------------------------------


def test_fila_valida_da_un_member_create_completo() -> None:
    socio = _socio(parse_member_row(2, fila_valida(1)))
    assert socio.document == "2000001"
    assert (socio.first_name, socio.last_name) == ("Nombre1", "Apellido1")
    assert socio.phone == "3005000001"
    assert socio.email == "socio1@ejemplo.com"
    assert socio.birth_date == date(1990, 5, 17)
    assert socio.sex == "f"
    assert socio.emergency_contact is not None
    assert (socio.emergency_contact.name, socio.emergency_contact.phone) == (
        "Contacto Prueba",
        "3105550100",
    )
    assert socio.document_type == "CC"
    assert socio.data_consent is False


@pytest.mark.parametrize(
    ("celda", "esperado"),
    [
        (1020304.0, "1020304"),
        (1020304, "1020304"),
        ("1.020.304", "1020304"),
        ("1020304", "1020304"),
    ],
)
def test_documento_numerico_o_con_puntos_queda_como_texto_de_digitos(
    celda: object, esperado: str
) -> None:
    assert _socio(parse_member_row(2, fila_valida(1, documento=celda))).document == esperado


@pytest.mark.parametrize(
    "celda",
    [date(1990, 5, 17), datetime(1990, 5, 17, 0, 0, tzinfo=UTC), datetime(1990, 5, 17, 0, 0)],
    ids=["date", "datetime-utc", "datetime-naive"],
)
def test_celda_de_fecha_se_acepta(celda: object) -> None:
    socio = _socio(parse_member_row(2, fila_valida(1, fecha_nacimiento=celda)))
    assert socio.birth_date == date(1990, 5, 17)


@pytest.mark.parametrize(("celda", "esperado"), [("F", "f"), ("f", "f"), ("M", "m"), ("x", "x")])
def test_sexo_se_normaliza_a_minuscula(celda: str, esperado: str) -> None:
    assert _socio(parse_member_row(2, fila_valida(1, sexo=celda))).sex == esperado


@pytest.mark.parametrize("celda", [None, ""])
def test_sexo_vacio_es_opcional(celda: object) -> None:
    assert _socio(parse_member_row(2, fila_valida(1, sexo=celda))).sex is None


def test_correo_y_telefono_son_opcionales() -> None:
    socio = _socio(parse_member_row(2, fila_valida(1, correo=None, telefono=None)))
    assert socio.email is None and socio.phone is None


def test_notas_se_ignora_y_no_llega_al_socio() -> None:
    socio = _socio(parse_member_row(2, fila_valida(1, notas="texto-de-la-nota-privada")))
    assert "texto-de-la-nota-privada" not in repr(socio.model_dump())


@pytest.mark.parametrize(
    "cambios",
    [
        {"contacto_emergencia_nombre": "Solo Nombre", "contacto_emergencia_telefono": None},
        {"contacto_emergencia_nombre": None, "contacto_emergencia_telefono": "3105550100"},
        {"contacto_emergencia_nombre": None, "contacto_emergencia_telefono": None},
    ],
    ids=["solo-nombre", "solo-telefono", "ninguno"],
)
def test_contacto_incompleto_deja_al_socio_sin_contacto(cambios: dict[str, object]) -> None:
    socio = _socio(parse_member_row(2, fila_valida(1, **cambios)))
    assert socio.emergency_contact is None


# Filas rechazadas -----------------------------------------------------------------------------


def test_fecha_imposible_se_rechaza_sin_repetir_el_valor() -> None:
    error = _rechazo(parse_member_row(5, fila_valida(1, fecha_nacimiento="2001-02-30")))
    assert error.row == 5
    assert "2001-02-30" not in error.reason and error.reason.strip()


@pytest.mark.parametrize("celda", ["17/05/1990", "1990-5-7", "mayo", 19900517])
def test_fecha_que_no_es_aaaa_mm_dd_se_rechaza(celda: object) -> None:
    assert isinstance(parse_member_row(2, fila_valida(1, fecha_nacimiento=celda)), RowError)


@pytest.mark.parametrize("celda", ["z", "Femenino", "fm", 1])
def test_sexo_fuera_de_f_m_x_se_rechaza(celda: object) -> None:
    assert isinstance(parse_member_row(2, fila_valida(1, sexo=celda)), RowError)


@pytest.mark.parametrize("columna", ["nombres", "apellidos"])
@pytest.mark.parametrize("valor", ["=SUMA(A1:A9)", "+57 Carlos", "-Pedro", "@cuenta"])
def test_nombre_que_parece_formula_se_rechaza(columna: str, valor: str) -> None:
    error = _rechazo(parse_member_row(7, fila_valida(1, **{columna: valor})))
    assert error.row == 7
    assert valor not in error.reason


@pytest.mark.parametrize("columna", ["documento", "nombres", "apellidos"])
@pytest.mark.parametrize("valor", [None, "", "   "])
def test_documento_nombres_y_apellidos_son_obligatorios(columna: str, valor: object) -> None:
    assert isinstance(parse_member_row(2, fila_valida(1, **{columna: valor})), RowError)


def test_correo_invalido_se_rechaza_sin_repetirlo() -> None:
    error = _rechazo(parse_member_row(2, fila_valida(1, correo="no-es-un-correo")))
    assert "no-es-un-correo" not in error.reason


@pytest.mark.parametrize("columna", ["nombres", "notas", "apellidos"])
def test_celda_de_mas_de_200_caracteres_se_rechaza(columna: str) -> None:
    largo = "a" * 201
    error = _rechazo(parse_member_row(2, fila_valida(1, **{columna: largo})))
    assert largo not in error.reason


# Enmascarado ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("documento", "esperado"), [("1020304", "•••304"), ("99912345678", "•••678")]
)
def test_mask_document_deja_solo_los_tres_ultimos(documento: str, esperado: str) -> None:
    assert mask_document(documento) == esperado


# Fórmulas en cualquier campo de texto (revisión de seguridad de B1, LOW) -----------------------


@pytest.mark.parametrize(
    "columna",
    [
        "documento",
        "telefono",
        "correo",
        "contacto_emergencia_nombre",
        "contacto_emergencia_telefono",
    ],
)
@pytest.mark.parametrize("valor", ["=1+1", "+573001234567", "-5551234", "@cuenta"])
def test_ningun_campo_de_texto_puede_empezar_como_una_formula(columna: str, valor: str) -> None:
    error = _rechazo(parse_member_row(4, fila_valida(1, **{columna: valor})))
    assert error.row == 4
    assert valor not in error.reason

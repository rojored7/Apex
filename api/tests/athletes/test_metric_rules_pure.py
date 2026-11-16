"""Reglas puras de las medidas (S9-A1, US-178; S9-D3, S9-D4, S9-D32, S9-D36 L-1). Rojo A1.

Valores esperados derivados a mano de las decisiones, nunca calculados con el código bajo prueba:
- ancho fijo y marca de campo (S9-D4, S9-D32): `weight_g` es `w` + 6 dígitos (7 caracteres),
  `height_cm` es `h` + 3 (4) y `body_fat_pct` es `f` + 2 (3); `62500 -> "w062500"`, `165 -> "h165"`,
  `7 -> "f07"`;
- `notes` (S9-D36, L-1): `n` + 4 dígitos con los BYTES UTF-8 del texto + el texto + espacios hasta
  que el claro completo (con la cabecera de 5 bytes) mida un múltiplo de 128 bytes. Interpretación
  del plan: el múltiplo cuenta el claro entero (`"n0005abcde"` mide 10 bytes y se rellena a 128);
- `decode_metric` exige marca, largo exacto y solo dígitos ASCII; falla con un error opaco que no
  repite el texto ni encadena la causa;
- `validate_metric` da 422 con el campo; `measured_on` es la fecha civil de Bogotá (a la 01:00 UTC
  Bogotá todavía está en el día anterior).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.clock import FrozenClock
from app.modules.athletes.exceptions import MetricValidationError
from app.modules.athletes.rules import (
    METRIC_FIELDS,
    MetricDecodeError,
    decode_metric,
    encode_metric,
    validate_metric,
)

HOY = date(2026, 10, 21)
EMOJI = "\U0001f3cb"  # 4 bytes en UTF-8
FULLWIDTH = "".join(chr(0xFF10 + int(d)) for d in "062500")  # `isdigit()`, no ASCII


# Constantes del contrato ---------------------------------------------------------------------


def test_los_cuatro_campos_en_el_orden_del_contrato() -> None:
    assert METRIC_FIELDS == ("weight_g", "height_cm", "body_fat_pct", "notes")


# encode_metric: números ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("campo", "valor", "esperado"),
    [
        ("weight_g", 20_000, "w020000"),
        ("weight_g", 62_500, "w062500"),
        ("weight_g", 100_000, "w100000"),
        ("weight_g", 400_000, "w400000"),
        ("height_cm", 50, "h050"),
        ("height_cm", 165, "h165"),
        ("height_cm", 250, "h250"),
        ("body_fat_pct", 1, "f01"),
        ("body_fat_pct", 7, "f07"),
        ("body_fat_pct", 22, "f22"),
        ("body_fat_pct", 75, "f75"),
    ],
)
def test_encode_antepone_la_marca_y_rellena_con_ceros_a_ancho_fijo(
    campo: str, valor: int, esperado: str
) -> None:
    assert encode_metric(campo, valor) == esperado


@pytest.mark.parametrize(
    ("campo", "bajo", "alto"),
    [
        ("weight_g", 19_999, 400_001),
        ("height_cm", 49, 251),
        ("body_fat_pct", 0, 76),
    ],
)
def test_encode_rechaza_un_valor_fuera_del_rango_para_no_romper_el_ancho(
    campo: str, bajo: int, alto: int
) -> None:
    for valor in (bajo, alto, -1, 10**9):
        with pytest.raises(MetricValidationError) as excepcion:
            encode_metric(campo, valor)
        assert excepcion.value.field == campo
        assert str(valor) not in excepcion.value.message


def test_el_ancho_es_el_mismo_en_todo_el_rango_de_cada_campo() -> None:
    assert {len(encode_metric("weight_g", v)) for v in (20_000, 62_500, 100_000, 400_000)} == {7}
    assert {len(encode_metric("height_cm", v)) for v in (50, 99, 100, 250)} == {4}
    assert {len(encode_metric("body_fat_pct", v)) for v in (1, 9, 10, 75)} == {3}


def test_encode_con_un_campo_desconocido_falla() -> None:
    for campo in ("member_id", "id", "weight", ""):
        with pytest.raises(ValueError, match="campo"):
            encode_metric(campo, 1)


# encode_metric: notes ------------------------------------------------------------------------


def test_encode_de_notas_cortas_rellena_hasta_128_bytes() -> None:
    assert encode_metric("notes", "abcde") == "n0005abcde" + " " * 118
    assert len(encode_metric("notes", "abcde").encode("utf-8")) == 128


def test_encode_de_notas_cuenta_bytes_utf8_no_caracteres() -> None:
    # "Buen día" = 8 caracteres y 9 bytes ("í" ocupa 2); cabecera 5 + 9 = 14; relleno 114.
    esperado = "n0009Buen día" + " " * 114
    salida = encode_metric("notes", "Buen día")
    assert salida == esperado
    assert len(salida) == 127  # 127 caracteres y 128 bytes
    assert len(salida.encode("utf-8")) == 128


@pytest.mark.parametrize(
    ("texto", "bytes_esperados"),
    [
        ("a" * 123, 128),  # 5 + 123 = 128 exactos: sin relleno
        ("a" * 124, 256),  # 5 + 124 = 129: salta al siguiente múltiplo
        ("a" * 251, 256),  # 5 + 251 = 256 exactos
        ("a" * 252, 384),
        ("a" * 500, 512),  # tope de caracteres: 505 bytes
        (EMOJI * 500, 2048),  # 4 bytes por carácter: 2000 + 5 = 2005
    ],
)
def test_el_claro_de_las_notas_mide_un_multiplo_de_128_bytes(
    texto: str, bytes_esperados: int
) -> None:
    salida = encode_metric("notes", texto)
    assert len(salida.encode("utf-8")) == bytes_esperados
    cuenta = len(texto.encode("utf-8"))
    assert salida.startswith(f"n{cuenta:04d}{texto}")
    assert salida[5 + len(texto) :] == " " * (len(salida) - 5 - len(texto))


def test_notas_de_5_y_de_100_caracteres_miden_lo_mismo() -> None:
    corta = encode_metric("notes", "a" * 5)
    larga = encode_metric("notes", "b" * 100)
    assert len(corta.encode("utf-8")) == len(larga.encode("utf-8")) == 128


@pytest.mark.parametrize(
    "texto",
    [
        "abcde",
        "Buen día",
        "ñandú, ¿cómo estás? " + EMOJI,
        "con espacios al final   ",
        "a" * 500,
        EMOJI * 500,
    ],
)
def test_ida_y_vuelta_de_las_notas_con_tildes_emoji_y_espacios_finales(texto: str) -> None:
    assert decode_metric("notes", encode_metric("notes", texto)) == texto


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("weight_g", 20_000), ("weight_g", 62_500), ("height_cm", 165), ("body_fat_pct", 7)],
)
def test_ida_y_vuelta_de_las_medidas_numericas(campo: str, valor: int) -> None:
    decodificado = decode_metric(campo, encode_metric(campo, valor))
    assert decodificado == valor and type(decodificado) is int


# decode_metric: rechazos opacos --------------------------------------------------------------


@pytest.mark.parametrize(
    ("campo", "texto"),
    [
        ("weight_g", "h165"),  # marca ajena (la de estatura)
        ("weight_g", "f07"),
        ("weight_g", "n0005abcde"),
        ("height_cm", "w062500"),
        ("height_cm", "f07"),
        ("body_fat_pct", "h165"),
        ("body_fat_pct", "w062500"),
        ("notes", "w062500"),
        ("notes", "h165"),
    ],
)
def test_decode_rechaza_la_marca_de_otro_campo(campo: str, texto: str) -> None:
    """M-2: un blob copiado a otra columna de la misma fila descifra, pero no se acepta."""
    with pytest.raises(MetricDecodeError):
        decode_metric(campo, texto)


@pytest.mark.parametrize(
    ("campo", "texto"),
    [
        ("weight_g", "w62500"),  # un dígito de menos
        ("weight_g", "w0625000"),  # uno de más
        ("weight_g", "w"),
        ("weight_g", ""),
        ("height_cm", "h16"),
        ("height_cm", "h1650"),
        ("body_fat_pct", "f7"),
        ("body_fat_pct", "f007"),
    ],
)
def test_decode_rechaza_un_largo_distinto_al_exacto(campo: str, texto: str) -> None:
    with pytest.raises(MetricDecodeError):
        decode_metric(campo, texto)


@pytest.mark.parametrize(
    ("campo", "texto"),
    [
        ("weight_g", "w06250x"),
        ("weight_g", "w+62500"),
        ("weight_g", "w 62500"),
        ("weight_g", "w-62500"),
        ("weight_g", "w" + FULLWIDTH),  # son `isdigit()`, pero no dígitos ASCII
        ("height_cm", "h16a"),
        ("body_fat_pct", "f0.7"),
    ],
)
def test_decode_exige_solo_digitos_ascii(campo: str, texto: str) -> None:
    with pytest.raises(MetricDecodeError):
        decode_metric(campo, texto)


@pytest.mark.parametrize(
    ("campo", "texto"),
    [
        ("weight_g", "w000001"),
        ("weight_g", "w019999"),
        ("weight_g", "w400001"),
        ("weight_g", "w999999"),
        ("height_cm", "h000"),
        ("height_cm", "h049"),
        ("height_cm", "h251"),
        ("body_fat_pct", "f00"),
        ("body_fat_pct", "f76"),
        ("body_fat_pct", "f99"),
    ],
)
def test_decode_valida_el_rango_despues_de_leer_los_digitos(campo: str, texto: str) -> None:
    with pytest.raises(MetricDecodeError):
        decode_metric(campo, texto)


@pytest.mark.parametrize(
    "texto",
    [
        "n0005abcde",  # sin relleno: no es múltiplo de 128 bytes
        "n0200abc" + " " * 120,  # la cuenta pasa del texto disponible
        "n0003abc" + "x" * 117,  # relleno que no son espacios
        "n00a3abc" + " " * 120,  # la cuenta no son dígitos
        "n3abc" + " " * 123,  # la cuenta mide menos de 4 dígitos
        "n0003abc" + " " * 119,  # 127 bytes: un byte de menos
        "",
    ],
)
def test_decode_de_notas_rechaza_formas_invalidas(texto: str) -> None:
    with pytest.raises(MetricDecodeError):
        decode_metric("notes", texto)


def test_decode_de_notas_rechaza_una_cuenta_que_corta_un_caracter_a_la_mitad() -> None:
    # "í" son 2 bytes; con cuenta 1 el texto sería un UTF-8 inválido. 5 + 2 + 121 = 128 bytes.
    with pytest.raises(MetricDecodeError):
        decode_metric("notes", "n0001í" + " " * 121)


@pytest.mark.parametrize(
    ("campo", "texto"),
    [("weight_g", "w06250x"), ("height_cm", "h16a"), ("notes", "n00a3secreto" + " " * 116)],
)
def test_el_error_del_decode_es_opaco_y_no_encadena_la_causa(campo: str, texto: str) -> None:
    with pytest.raises(MetricDecodeError) as excepcion:
        decode_metric(campo, texto)
    error = excepcion.value
    assert isinstance(error, ValueError)
    for pedazo in ("06250", "16a", "secreto", texto):
        assert pedazo not in str(error) and pedazo not in repr(error)
    assert error.__cause__ is None


def test_decode_con_un_campo_desconocido_falla() -> None:
    with pytest.raises(ValueError, match="campo"):
        decode_metric("member_id", "w062500")


# validate_metric -----------------------------------------------------------------------------


def _validar(**cambios: object) -> None:
    valores: dict[str, object] = {
        "measured_on": HOY,
        "weight_g": 62_500,
        "height_cm": None,
        "body_fat_pct": None,
        "notes": None,
        "today": HOY,
    }
    valores.update(cambios)
    validate_metric(**valores)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "cambios",
    [
        {"weight_g": 20_000},
        {"weight_g": 400_000},
        {"weight_g": None, "height_cm": 50},
        {"weight_g": None, "height_cm": 250},
        {"weight_g": None, "body_fat_pct": 1},
        {"weight_g": None, "body_fat_pct": 75},
        {"weight_g": 62_500, "height_cm": 165, "body_fat_pct": 22, "notes": "ok"},
        {"notes": "a" * 500},
    ],
)
def test_los_limites_exactos_pasan(cambios: dict[str, object]) -> None:
    _validar(**cambios)


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"weight_g": 19_999}, "weight_g"),
        ({"weight_g": 400_001}, "weight_g"),
        ({"weight_g": None, "height_cm": 49}, "height_cm"),
        ({"weight_g": None, "height_cm": 251}, "height_cm"),
        ({"weight_g": None, "body_fat_pct": 0}, "body_fat_pct"),
        ({"weight_g": None, "body_fat_pct": 76}, "body_fat_pct"),
        ({"notes": ""}, "notes"),
        ({"notes": "a" * 501}, "notes"),
    ],
)
def test_un_valor_fuera_de_rango_da_422_con_el_campo_y_sin_repetirlo(
    cambios: dict[str, object], campo: str
) -> None:
    with pytest.raises(MetricValidationError) as excepcion:
        _validar(**cambios)
    assert excepcion.value.status == 422
    assert excepcion.value.field == campo
    for valor in cambios.values():
        if isinstance(valor, int) and valor > 100:
            assert str(valor) not in excepcion.value.message


@pytest.mark.parametrize(
    "cambios",
    [
        {"weight_g": None},
        {"weight_g": None, "notes": "solo texto"},  # las notas no cuentan como medida
    ],
)
def test_sin_ninguna_de_las_tres_medidas_el_campo_es_weight_g(cambios: dict[str, object]) -> None:
    with pytest.raises(MetricValidationError) as excepcion:
        _validar(**cambios)
    assert excepcion.value.field == "weight_g"


def test_measured_on_no_puede_ser_futura_ni_anterior_a_2000() -> None:
    _validar(measured_on=HOY)
    _validar(measured_on=date(2000, 1, 1))
    for fecha in (HOY + timedelta(days=1), date(1999, 12, 31), date(1900, 1, 1)):
        with pytest.raises(MetricValidationError) as excepcion:
            _validar(measured_on=fecha)
        assert excepcion.value.field == "measured_on"
        assert fecha.isoformat() not in excepcion.value.message


def test_a_la_01_utc_la_fecha_civil_de_bogota_sigue_en_el_dia_anterior() -> None:
    """Bogotá es UTC-5: a las 01:00 UTC del 21 aún es el 20 a las 20:00. La fecha UTC no vale."""
    reloj = FrozenClock(datetime(2026, 10, 21, 1, 0, tzinfo=UTC))
    hoy_bogota = reloj.today_bogota()
    assert hoy_bogota == date(2026, 10, 20)
    _validar(measured_on=date(2026, 10, 20), today=hoy_bogota)
    with pytest.raises(MetricValidationError) as excepcion:
        _validar(measured_on=date(2026, 10, 21), today=hoy_bogota)  # el día UTC, futuro en Bogotá
    assert excepcion.value.field == "measured_on"

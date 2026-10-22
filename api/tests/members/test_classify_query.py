"""`members.service.classify_query`, pura (S2-B8; US-070 T1 y T6; RN-13, N-02, L-3).

Decide qué busca un término de la caja única de `/socios`:
- `name_pattern`: el término recortado entre `%`, con la barra invertida, `%` y `_` escapados
  (`LIKE_ESCAPE`), para `ILIKE ... ESCAPE '\\'`; siempre que el término no esté en blanco;
- `by_document`: el valor normalizado `generic` (N-02) cuando no queda vacío, tiene al menos
  un dígito y solo letras y dígitos (un nombre como `"góm"` no gasta un HMAC de documento);
- `by_phone`: el valor normalizado `phone` (sin `57`/`+57` inicial) con al menos 7 dígitos;
- `by_email`: el valor normalizado `email` solo si el término tiene `@`;
- `CryptoError("empty_value")` se captura: `"..."` o `"+57"` no rompen, solo no dan índices;
- `q` `None`, vacío o en blanco da el plan vacío.
Los valores del plan son los que `bus.blind_index` vuelve a normalizar (idempotente), así que
`"300 123 4567"` y `"+57 300 123 4567"` llegan al mismo índice.
"""

from __future__ import annotations

import pytest

from app.core.crypto import bus
from app.core.crypto.keyring import Keyring
from app.core.crypto.normalize import normalize_for_index
from app.modules.members.service import LIKE_ESCAPE, QueryPlan, classify_query

PLAN_VACIO = QueryPlan(q=None, name_pattern=None, by_document=None, by_phone=None, by_email=None)


def test_el_escape_de_like_es_la_barra_invertida() -> None:
    assert LIKE_ESCAPE == "\\"


def test_un_documento_con_puntos_va_al_indice_de_documento_normalizado() -> None:
    plan = classify_query("1.020.304")
    assert plan.q == "1.020.304"
    assert plan.by_document == normalize_for_index("1.020.304", "generic") == "1020304"
    assert plan.by_email is None
    assert plan.name_pattern == "%1.020.304%"


def test_un_documento_con_guiones_y_espacios_da_el_mismo_valor_que_sin_ellos() -> None:
    assert classify_query(" 1020-304 ").by_document == "1020304"
    assert classify_query("1 020 304").by_document == "1020304"


def test_un_pasaporte_con_letras_y_digitos_va_al_indice_de_documento() -> None:
    assert classify_query("AB-123456").by_document == "ab123456"


@pytest.mark.parametrize("telefono", ["300 123 4567", "+57 300 123 4567", "(300) 123-4567"])
def test_un_telefono_con_espacios_o_prefijo_va_al_mismo_indice(telefono: str) -> None:
    plan = classify_query(telefono)
    assert plan.by_phone == "3001234567"
    assert plan.by_email is None


def test_siete_digitos_activan_el_telefono_y_seis_no() -> None:
    assert classify_query("6015550").by_phone == "6015550"
    seis = classify_query("123456")
    assert seis.by_phone is None
    assert seis.by_document == "123456"


def test_el_documento_de_siete_digitos_tambien_se_busca_como_telefono() -> None:
    """La caja es única: un término de 7 o más dígitos se busca por documento y por teléfono."""
    plan = classify_query("1.020.304")
    assert plan.by_document == "1020304"
    assert plan.by_phone == "1020304"


def test_un_correo_en_mayusculas_va_al_indice_de_correo_normalizado() -> None:
    plan = classify_query("Lucia.Gomez@Correo.co")
    assert plan.by_email == normalize_for_index("Lucia.Gomez@Correo.co", "email")
    assert plan.by_email == "lucia.gomez@correo.co"
    assert plan.by_phone is None
    assert plan.by_document is None  # sin dígitos y con `@`: no es un documento


def test_un_correo_con_digitos_no_es_un_documento() -> None:
    plan = classify_query("ana2@correo.co")
    assert plan.by_email == "ana2@correo.co"
    assert plan.by_document is None


@pytest.mark.parametrize("nombre", ["góm", "Góm", "Laura Gómez", "gom"])
def test_un_nombre_solo_da_el_patron_de_nombre(nombre: str) -> None:
    plan = classify_query(nombre)
    assert plan.q == nombre
    assert plan.name_pattern is not None
    assert plan.by_document is None
    assert plan.by_phone is None
    assert plan.by_email is None


def test_el_patron_de_nombre_va_recortado_entre_porcentajes() -> None:
    assert classify_query("  ana ruiz  ").name_pattern == "%ana ruiz%"
    assert classify_query("  ana ruiz  ").q == "ana ruiz"


@pytest.mark.parametrize(
    ("termino", "patron"),
    [
        ("%", "%\\%%"),
        ("_", "%\\_%"),
        ("\\", "%\\\\%"),
        ("a%b_c\\d", "%a\\%b\\_c\\\\d%"),
        ("100%", "%100\\%%"),
    ],
    ids=["porcentaje", "guion-bajo", "barra", "mezcla", "con-digitos"],
)
def test_los_comodines_y_la_barra_van_escapados(termino: str, patron: str) -> None:
    assert classify_query(termino).name_pattern == patron


@pytest.mark.parametrize("termino", ["...", "+57", "--", "( )"])
def test_un_termino_sin_valor_indexable_no_da_indices_y_conserva_el_patron(termino: str) -> None:
    """L-3: `"..."` se normaliza a vacío (se captura `CryptoError("empty_value")`); `"+57"`
    queda en `"57"` (2 dígitos: no es teléfono) y lleva `+` (no es documento)."""
    plan = classify_query(termino)
    assert plan.by_document is None
    assert plan.by_phone is None
    assert plan.by_email is None
    assert plan.name_pattern == f"%{termino.strip()}%"


@pytest.mark.parametrize("termino", [None, "", "   ", "\t\n"])
def test_un_termino_vacio_o_en_blanco_da_el_plan_vacio(termino: str | None) -> None:
    assert classify_query(termino) == PLAN_VACIO


def test_el_plan_es_inmutable() -> None:
    plan = classify_query("góm")
    with pytest.raises(AttributeError):
        plan.name_pattern = "%x%"  # type: ignore[misc]


def test_los_valores_del_plan_dan_el_mismo_indice_ciego_que_el_termino(
    bus_listo: Keyring,
) -> None:
    """`list` indexa los valores del plan: deben coincidir con el índice del término crudo."""
    documento = classify_query("1.020.304").by_document
    assert documento is not None
    assert bus.blind_index("member.document", documento) == bus.blind_index(
        "member.document", "1020304"
    )
    con_prefijo = classify_query("+57 300 123 4567").by_phone
    sin_prefijo = classify_query("300 123 4567").by_phone
    assert con_prefijo is not None and sin_prefijo is not None
    assert bus.blind_index("member.phone", con_prefijo) == bus.blind_index(
        "member.phone", sin_prefijo
    )
    correo = classify_query("LUCIA.GOMEZ@CORREO.CO").by_email
    assert correo is not None
    assert bus.blind_index("member.email", correo) == bus.blind_index(
        "member.email", "lucia.gomez@correo.co"
    )

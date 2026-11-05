"""`whatsapp.build_link(..., country_code=)` (S5-V11c; S5-D265c). # Rojo V11c

Con `57` (por defecto) rige S5-D224 sin cambios. Con otro indicativo el número guardado debe ser
de 8 a 15 dígitos y el enlace antepone SIEMPRE el indicativo (nacional, S5-D270). Fuera del rango,
`ValueError` (el servicio lo traduce a 422 `invalid_phone`).
"""

from __future__ import annotations

import pytest

from app.modules.notifications import whatsapp


def test_con_57_por_defecto_rige_el_celular_colombiano() -> None:
    assert whatsapp.build_link("300 765 4321", "Hola") == "https://wa.me/573007654321?text=Hola"
    assert (
        whatsapp.build_link("3007654321", "Hola", country_code="57")
        == "https://wa.me/573007654321?text=Hola"
    )
    with pytest.raises(ValueError):
        whatsapp.build_link("6017654321", "Hola", country_code="57")


@pytest.mark.parametrize("telefono", ["5512345678", "55 1234 5678", "(55) 1234-5678"])
def test_con_otro_indicativo_se_antepone(telefono: str) -> None:
    enlace = whatsapp.build_link(telefono, "Hola", country_code="52")

    assert enlace == "https://wa.me/525512345678?text=Hola"


def test_un_numero_que_ya_empieza_por_el_indicativo_se_antepone_igual() -> None:
    enlace = whatsapp.build_link("5255123456", "Hola", country_code="52")

    assert enlace == "https://wa.me/525255123456?text=Hola"


def test_numero_brasileno_con_9_inicial_no_pierde_digitos() -> None:
    enlace = whatsapp.build_link("55912345678", "Hola", country_code="55")

    assert enlace == "https://wa.me/5555912345678?text=Hola"


@pytest.mark.parametrize("telefono", ["1234567", "1234567890123456", "", "abc"])
def test_con_otro_indicativo_los_digitos_fuera_de_8_a_15_son_un_error(telefono: str) -> None:
    with pytest.raises(ValueError):
        whatsapp.build_link(telefono, "Hola", country_code="52")


@pytest.mark.parametrize("digitos", ["12345678", "123456789012345"])
def test_los_limites_de_8_y_15_digitos_son_validos(digitos: str) -> None:
    enlace = whatsapp.build_link(digitos, "x", country_code="52")

    assert enlace.startswith("https://wa.me/") and enlace.endswith("?text=x")

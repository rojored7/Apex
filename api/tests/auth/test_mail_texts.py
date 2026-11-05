"""Texto fijo de los correos de cuenta (S5-B9, US-131; S5-D37, N-36). # Rojo B9

`mail_texts.activation_mail(url, sender)` y `reset_mail(url, sender)` devuelven `(asunto, cuerpo)`:
texto plano en español, fijo (lo único que cambia entre dos correos del mismo tipo es el enlace
y el remitente), sin HTML, sin `\\r`, sin datos del socio y con el enlace completo.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.modules.auth import mail_texts

URL_A = "https://gym.ejemplo.test/restablecer/AbC_123-xyz0987654321AbC_123-xyz09876"
URL_B = "https://otro.ejemplo.test/restablecer/Zz9-_Zz9-_Zz9-_Zz9-_Zz9-_Zz9-_Zz9-_Zz9-_Zz"
REMITENTE = "APEX CrossFit"

Fabrica = Callable[[str, str], tuple[str, str]]
AMBAS = [mail_texts.activation_mail, mail_texts.reset_mail]
IDS = ["activacion", "recuperacion"]


@pytest.mark.parametrize("construir", AMBAS, ids=IDS)
def test_el_cuerpo_lleva_el_enlace_completo_sin_alterar(construir: Fabrica) -> None:
    asunto, cuerpo = construir(URL_A, REMITENTE)
    assert URL_A in cuerpo
    assert asunto.strip() != ""


@pytest.mark.parametrize("construir", AMBAS, ids=IDS)
def test_es_texto_plano_sin_html_ni_retorno_de_carro(construir: Fabrica) -> None:
    asunto, cuerpo = construir(URL_A, REMITENTE)
    for texto in (asunto, cuerpo):
        assert "\r" not in texto
        assert "<" not in texto and ">" not in texto
    assert "\n" not in asunto


@pytest.mark.parametrize("construir", AMBAS, ids=IDS)
def test_el_texto_es_fijo_y_solo_cambia_el_enlace(construir: Fabrica) -> None:
    asunto_a, cuerpo_a = construir(URL_A, REMITENTE)
    asunto_b, cuerpo_b = construir(URL_B, REMITENTE)
    assert asunto_a == asunto_b
    assert cuerpo_a.replace(URL_A, "<URL>") == cuerpo_b.replace(URL_B, "<URL>")
    assert URL_B not in cuerpo_a


@pytest.mark.parametrize("construir", AMBAS, ids=IDS)
def test_nombra_al_remitente_del_canal(construir: Fabrica) -> None:
    asunto, cuerpo = construir(URL_A, REMITENTE)
    assert REMITENTE in asunto + cuerpo
    otro = construir(URL_A, "Gimnasio Norte")
    assert "Gimnasio Norte" in otro[0] + otro[1]
    assert REMITENTE not in otro[0] + otro[1]


@pytest.mark.parametrize("construir", AMBAS, ids=IDS)
def test_el_asunto_es_corto_para_una_cabecera(construir: Fabrica) -> None:
    asunto, _ = construir(URL_A, REMITENTE)
    assert 0 < len(asunto) <= 78


@pytest.mark.parametrize("construir", AMBAS, ids=IDS)
def test_no_repite_el_correo_ni_datos_de_personas(construir: Fabrica) -> None:
    asunto, cuerpo = construir(URL_A, REMITENTE)
    assert "@" not in asunto + cuerpo


def test_la_activacion_habla_de_activar_la_cuenta() -> None:
    asunto, cuerpo = mail_texts.activation_mail(URL_A, REMITENTE)
    assert "activ" in (asunto + cuerpo).lower()


def test_la_recuperacion_habla_de_restablecer_la_contrasena() -> None:
    asunto, cuerpo = mail_texts.reset_mail(URL_A, REMITENTE)
    texto = (asunto + cuerpo).lower()
    assert "contraseña" in texto and "restablec" in texto


def test_activacion_y_recuperacion_no_son_el_mismo_texto() -> None:
    assert mail_texts.activation_mail(URL_A, REMITENTE) != mail_texts.reset_mail(URL_A, REMITENTE)
    assert (
        mail_texts.activation_mail(URL_A, REMITENTE)[0]
        != mail_texts.reset_mail(URL_A, REMITENTE)[0]
    )

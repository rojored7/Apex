"""`core/pdf.py`: escritor de PDF propio (S5-B11, S5-D65, S5-D61, M-11).

# Rojo B11

Contrato: una página A4; Courier y Courier-Bold sin incrustar; WinAnsi; TODA cadena en hexadecimal
(ningún paréntesis ni barra invertida en el archivo); `xref` y `/Length` calculados; sin
`/JavaScript`, `/JS`, `/OpenAction`, `/AA`, `/URI`, `/Launch`, `/Annots` ni `/EmbeddedFile`; lo que
no cabe en WinAnsi (U+202E, emoji, NUL, controles) sale como `?`, también en el título de `/Info`;
más de `MAX_PDF_BYTES` (100 000) es `ValueError`. Se verifica con `pypdf` (solo desarrollo).
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any

import pytest
from pypdf import PdfReader

from app.core.pdf import MAX_PDF_BYTES, PdfLine, render_text_pdf

TITULO = "Recibo de prueba"
MM = 72 / 25.4
PROHIBIDAS = (
    b"/JavaScript",
    b"/JS",
    b"/OpenAction",
    b"/AA",
    b"/URI",
    b"/Launch",
    b"/Annots",
    b"/EmbeddedFile",
)


def linea(texto: str, y_mm: float = 270, **kw: Any) -> PdfLine:
    return PdfLine(texto, kw.pop("x_mm", 20), y_mm, kw.pop("size", 10), **kw)


def abrir(datos: bytes) -> PdfReader:
    return PdfReader(BytesIO(datos), strict=True)


def texto_de(datos: bytes) -> str:
    return "\n".join(p.extract_text() for p in abrir(datos).pages)


def test_el_limite_de_tamano_es_cien_mil_bytes() -> None:
    assert MAX_PDF_BYTES == 100_000


def test_un_pdf_con_una_linea_lo_abre_pypdf_estricto_con_una_pagina_a4() -> None:
    datos = render_text_pdf([linea("Hola mundo")], title=TITULO)
    lector = abrir(datos)
    assert len(lector.pages) == 1
    caja = lector.pages[0].mediabox
    assert abs(float(caja.width) - 595.28) < 1
    assert abs(float(caja.height) - 841.89) < 1
    assert datos.startswith(b"%PDF-1.")
    assert datos.rstrip().endswith(b"%%EOF")
    assert "Hola mundo" in texto_de(datos)


def test_sin_lineas_es_un_pdf_valido_de_una_pagina_sin_texto() -> None:
    datos = render_text_pdf([], title=TITULO)
    lector = abrir(datos)
    assert len(lector.pages) == 1
    assert texto_de(datos).strip() == ""


def test_el_titulo_queda_en_info() -> None:
    lector = abrir(render_text_pdf([linea("x")], title=TITULO))
    assert lector.metadata is not None
    assert lector.metadata.title == TITULO


def test_el_texto_con_parentesis_barra_tildes_y_enie_sale_integro() -> None:
    frases = [
        "Pago (parcial) de Muñoz \\ Peña",
        "Áéíóú ÁÉÍÓÚ ñ Ñ ü Ü ¿Qué? ¡Hola!",
        "a) b( ))) ((( \\\\ \\( \\)",
    ]
    lineas = [linea(f, y_mm=270 - 10 * i) for i, f in enumerate(frases)]
    extraido = texto_de(render_text_pdf(lineas, title=TITULO))
    for frase in frases:
        assert frase in extraido, frase


def test_ninguna_cadena_lleva_parentesis_ni_barra_en_el_archivo() -> None:
    datos = render_text_pdf([linea("x (y) \\ z")], title="T (1) \\")
    assert b"(" not in datos
    assert b")" not in datos
    assert b"\\" not in datos
    assert b"<" in datos


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Hola ‮mundo", "Hola ?mundo"),
        ("Hola \U0001f600 mundo", "Hola ? mundo"),
        ("Hola\x00mundo", "Hola?mundo"),
        ("a\x1fb", "a?b"),
        ("a\x7fb", "a?b"),
        ("a\tb", "a?b"),
        ("‮‮\U0001f600", "???"),
    ],
)
def test_lo_que_no_cabe_en_winansi_sale_como_signo_de_interrogacion(
    entrada: str, esperado: str
) -> None:
    extraido = texto_de(render_text_pdf([linea(entrada)], title=TITULO))
    assert esperado in extraido
    assert "‮" not in extraido
    assert "\x00" not in extraido
    assert "\U0001f600" not in extraido


def test_el_titulo_hostil_tambien_se_sanea() -> None:
    lector = abrir(render_text_pdf([linea("x")], title="Recibo ‮\x00\U0001f600 (1)"))
    assert lector.metadata is not None
    assert lector.metadata.title == "Recibo ??? (1)"


def test_el_texto_con_claves_de_pdf_no_las_deja_en_el_archivo() -> None:
    hostil = "/JavaScript /JS /OpenAction /AA /URI (http://x) /Launch /Annots /EmbeddedFile"
    datos = render_text_pdf([linea(hostil)], title=hostil)
    assert hostil in texto_de(datos)
    for clave in PROHIBIDAS:
        assert clave not in datos, clave


def test_el_texto_con_endstream_y_endobj_no_rompe_la_estructura() -> None:
    hostil = "endstream endobj xref trailer startxref %%EOF"
    datos = render_text_pdf([linea(hostil)], title=TITULO)
    assert hostil in texto_de(datos)
    assert len(abrir(datos).pages) == 1


def test_sin_claves_prohibidas_en_un_pdf_normal() -> None:
    datos = render_text_pdf([linea("a"), linea("b", bold=True, y_mm=250)], title=TITULO)
    for clave in PROHIBIDAS:
        assert clave not in datos, clave
    assert b"/FontFile" not in datos


def test_xref_y_startxref_apuntan_a_donde_dicen() -> None:
    datos = render_text_pdf([linea("a"), linea("b", y_mm=250)], title=TITULO)
    final = re.search(rb"startxref\s+(\d+)\s+%%EOF\s*$", datos)
    assert final is not None
    inicio = int(final.group(1))
    assert datos[inicio : inicio + 4] == b"xref"
    cabecera = re.match(rb"xref\s+0 (\d+)\s", datos[inicio:])
    assert cabecera is not None
    total = int(cabecera.group(1))
    entradas = re.findall(rb"(\d{10}) (\d{5}) ([nf]) ", datos[inicio + cabecera.end() :])
    assert len(entradas) >= total
    for numero, (offset, _gen, uso) in enumerate(entradas[:total]):
        if uso == b"n":
            esperado = f"{numero} 0 obj".encode()
            assert datos[int(offset) :].startswith(esperado), numero


def test_el_length_del_contenido_es_el_largo_real_del_flujo() -> None:
    # pypdf quita `/Length` del diccionario al leer: se mide sobre los bytes crudos.
    datos = render_text_pdf([linea("a")], title=TITULO)
    hallado = re.search(rb"/Length (\d+) >>\nstream\n(.*?)endstream", datos, re.DOTALL)
    assert hallado is not None
    assert b"/Filter" not in datos
    assert int(hallado.group(1)) == len(hallado.group(2))


def test_las_fuentes_son_courier_estandar_con_winansi_sin_incrustar() -> None:
    datos = render_text_pdf([linea("a"), linea("b", bold=True, y_mm=250)], title=TITULO)
    assert b"/Courier" in datos
    assert b"/Courier-Bold" in datos
    assert b"/WinAnsiEncoding" in datos
    assert b"/FontFile" not in datos


def test_posicion_tamano_y_negrita_de_cada_linea() -> None:
    vistas: list[tuple[str, float, float, float, str]] = []

    def visitante(texto: str, cm: list[float], tm: list[float], fuente: Any, tamano: float) -> None:
        if texto.strip():
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            vistas.append((texto.strip(), x, y, tamano, str(fuente["/BaseFont"])))

    datos = render_text_pdf(
        [
            PdfLine("Normal", 20, 270, 10),
            PdfLine("Negrita", 30, 100, 14, bold=True),
        ],
        title=TITULO,
    )
    abrir(datos).pages[0].extract_text(visitor_text=visitante)
    por_texto = {v[0]: v for v in vistas}
    _, x, y, tamano, fuente = por_texto["Normal"]
    assert (round(x, 1), round(y, 1), round(tamano, 1)) == (
        round(20 * MM, 1),
        round(270 * MM, 1),
        10.0,
    )
    assert fuente.endswith("Courier")
    _, x, y, tamano, fuente = por_texto["Negrita"]
    assert (round(x, 1), round(y, 1), round(tamano, 1)) == (
        round(30 * MM, 1),
        round(100 * MM, 1),
        14.0,
    )
    assert fuente.endswith("Courier-Bold")


def test_doscientas_lineas_caben_en_cien_kb() -> None:
    lineas = [linea(f"Línea {i:03d} " + "x" * 90, y_mm=290 - i * 1.4, size=6) for i in range(200)]
    datos = render_text_pdf(lineas, title=TITULO)
    assert len(datos) <= MAX_PDF_BYTES
    extraido = texto_de(datos)
    assert "Línea 000 xxx" in extraido
    assert "Línea 199 xxx" in extraido


def test_mas_de_cien_kb_es_value_error() -> None:
    lineas = [linea("y" * 400, y_mm=290 - (i % 200)) for i in range(600)]
    with pytest.raises(ValueError, match=r"\d"):
        render_text_pdf(lineas, title=TITULO)

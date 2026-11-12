"""`core/http.file_download` (S6-B3, US-146; S6-D57). Rojo B3.

Descarga de un archivo ya armado en memoria: `Content-Disposition: attachment`, `no-store`,
`nosniff`, CSP que no deja ejecutar nada, `media_type` respetado y nombre de archivo saneado (sin
separadores de ruta, comillas ni caracteres de control).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import Response
from fastapi.responses import StreamingResponse

from app.core.http import file_download, file_stream

CSP = "default-src 'none'; sandbox"
JSON = "application/json; charset=utf-8"


def descargar(
    cuerpo: bytes = b'{"a": 1}', nombre: str = "apex-cbom-2026-10-21.json", tipo: str = JSON
) -> Response:
    return file_download(cuerpo, filename=nombre, media_type=tipo)


def test_devuelve_una_response_con_el_cuerpo_tal_cual() -> None:
    r = descargar(b'{"format": "apex-cbom/1"}')

    assert isinstance(r, Response)
    assert r.body == b'{"format": "apex-cbom/1"}'
    assert r.status_code == 200


def test_lleva_las_cuatro_cabeceras_de_descarga() -> None:
    r = descargar()

    assert r.headers["content-disposition"] == "attachment; filename=apex-cbom-2026-10-21.json"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-security-policy"] == CSP


@pytest.mark.parametrize("tipo", [JSON, "text/plain; charset=utf-8", "application/pdf"])
def test_el_media_type_se_respeta(tipo: str) -> None:
    assert descargar(tipo=tipo).headers["content-type"] == tipo


def test_content_length_es_el_del_cuerpo() -> None:
    assert descargar(b"x" * 123).headers["content-length"] == "123"


@pytest.mark.parametrize(
    ("entrada", "prohibidos"),
    [
        ("../../etc/passwd", ("/", "..")),
        ("a/b/c.json", ("/",)),
        ("a\\b\\c.json", ("\\",)),
        ('a"b.json', ('"',)),
        ("a\r\nSet-Cookie: x=1.json", ("\r", "\n")),
        ("a\x00b\x1f.json", ("\x00", "\x1f")),
        ("a\x7fb.json", ("\x7f",)),
        # Revisión de seguridad de S6-B3: `;` añadiría parámetros a la cabecera y un carácter fuera
        # de ASCII rompería su codificación.
        ("a;b.json", (";",)),
        ("a%20b.json", ("%",)),
        ("año-ñ.json", ("ñ",)),
        ("名前.json", ("名", "前")),
    ],
)
def test_el_nombre_se_sanea(entrada: str, prohibidos: tuple[str, ...]) -> None:
    r = descargar(nombre=entrada)

    disposicion = r.headers["content-disposition"]
    assert disposicion.startswith("attachment; filename=")
    nombre = disposicion.removeprefix("attachment; filename=")
    for caracter in prohibidos:
        assert caracter not in nombre, (entrada, nombre)
    assert nombre != ""
    assert "\r" not in disposicion and "\n" not in disposicion
    assert "set-cookie" not in r.headers


def test_un_nombre_limpio_no_cambia() -> None:
    r = descargar(nombre="apex-cbom-2026-10-21.json")

    assert r.headers["content-disposition"].endswith("filename=apex-cbom-2026-10-21.json")


def test_un_nombre_que_queda_vacio_cae_a_uno_por_defecto() -> None:
    r = descargar(nombre='/\\"\r\n')

    nombre = r.headers["content-disposition"].removeprefix("attachment; filename=")
    assert nombre.strip() != ""
    assert not set(nombre) & set('/\\"\r\n')


def test_no_agrega_cookies_ni_cabeceras_de_cache_publico() -> None:
    r = descargar()

    assert "set-cookie" not in r.headers
    assert "etag" not in r.headers
    assert "public" not in r.headers["cache-control"]


# `file_stream` (S6-C4, US-150): la foto sale por streaming con las mismas cabeceras --------------


async def _trozos(*partes: bytes) -> AsyncIterator[bytes]:
    for parte in partes:
        yield parte


def transmitir(nombre: str = "adjunto-0a1b2c3d.jpg", tipo: str = "image/jpeg") -> StreamingResponse:
    return file_stream(_trozos(b"uno", b"dos"), filename=nombre, media_type=tipo)


def test_file_stream_devuelve_una_streaming_response_200() -> None:
    r = transmitir()

    assert isinstance(r, StreamingResponse)
    assert r.status_code == 200


async def test_file_stream_entrega_los_trozos_tal_cual() -> None:
    r = transmitir()

    recibido = [t async for t in r.body_iterator]

    assert b"".join(recibido) == b"unodos"


def test_file_stream_lleva_las_mismas_cuatro_cabeceras_que_file_download() -> None:
    en_stream = transmitir("adjunto-0a1b2c3d.jpg", "image/jpeg")
    en_memoria = file_download(b"x", filename="adjunto-0a1b2c3d.jpg", media_type="image/jpeg")

    for cabecera in (
        "content-disposition",
        "cache-control",
        "x-content-type-options",
        "content-security-policy",
    ):
        assert en_stream.headers[cabecera] == en_memoria.headers[cabecera], cabecera
    assert en_stream.headers["content-security-policy"] == CSP
    assert en_stream.headers["content-type"] == "image/jpeg"


def test_file_stream_no_fija_content_length_ni_cookies() -> None:
    r = transmitir()

    assert "content-length" not in r.headers  # el tamaño real lo da el almacén al transmitir
    assert "set-cookie" not in r.headers
    assert "etag" not in r.headers


@pytest.mark.parametrize(
    ("entrada", "prohibidos"),
    [
        ("../../etc/passwd", ("/", "..")),
        ('a"b.jpg', ('"',)),
        ("a\r\nSet-Cookie: x=1.jpg", ("\r", "\n")),
        ("a;b.jpg", (";",)),
        ("名前.jpg", ("名", "前")),
    ],
)
def test_file_stream_sanea_el_nombre_como_file_download(
    entrada: str, prohibidos: tuple[str, ...]
) -> None:
    r = transmitir(nombre=entrada)

    disposicion = r.headers["content-disposition"]
    assert disposicion.startswith("attachment; filename=")
    for caracter in prohibidos:
        assert caracter not in disposicion.removeprefix("attachment; filename="), entrada
    assert "set-cookie" not in r.headers

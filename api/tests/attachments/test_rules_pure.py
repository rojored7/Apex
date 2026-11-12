"""Reglas puras de adjuntos (S6-C1, US-147; S6-D22, S6-D25, S6-D59): sin base ni disco.

- `detect_mime(head)`: JPEG `FF D8 FF`, PNG `89 50 4E 47 0D 0A 1A 0A`, PDF `%PDF-`; ELF, PE, vacío y
  una cabecera de 3 bytes devuelven `None` (la extensión y el `Content-Type` no cuentan).
- `validate_upload(size, mime, kind)`: 5.242.880 pasa, 5.242.881 → `FileTooLarge`; cero o negativo
  y un tipo fuera de los tres → error; la foto solo admite imagen; `consent` y `other`, imagen o
  PDF.
- `kind_is_sensitive`: `consent` y `other` sí; `photo` no; un `kind` ajeno es un error.
- `find_orphans(row_keys, stored_keys)`: filas sin objeto y objetos sin fila, ordenados.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from app.modules.attachments import rules
from app.modules.attachments.exceptions import FileTooLarge, UnsupportedType
from app.modules.attachments.rules import (
    ATTACHMENT_MAX_BYTES,
    ATTACHMENT_READ_LIMIT,
    OrphanReport,
    detect_mime,
    find_orphans,
    kind_is_sensitive,
    validate_upload,
)
from tests.factories import files

JPEG, PNG, PDF = "image/jpeg", "image/png", "application/pdf"


def test_las_constantes_del_tope_son_las_de_s6_d59() -> None:
    assert ATTACHMENT_MAX_BYTES == 5_242_880
    assert ATTACHMENT_READ_LIMIT == 5_242_881 == ATTACHMENT_MAX_BYTES + 1
    assert rules.ATTACHMENT_UPLOAD_TIMEOUT_S == 30  # S6-D84


@pytest.mark.parametrize(
    ("cabecera", "esperado"),
    [
        (files.jpeg()[:64], JPEG),
        (files.png()[:64], PNG),
        (files.pdf()[:64], PDF),
        (files.elf()[:64], None),
        (files.pe()[:64], None),
        (b"", None),
        (b"\xff\xd8\xff"[:2], None),
        (b"\x89PN", None),
        (b"%PDF", None),
        (b"abc", None),
    ],
    ids=[
        "jpeg",
        "png",
        "pdf",
        "elf",
        "pe",
        "vacio",
        "jpeg_truncado",
        "png_truncado",
        "pdf_sin_guion",
        "tres_bytes",
    ],
)
def test_detect_mime_decide_por_los_bytes_magicos(cabecera: bytes, esperado: str | None) -> None:
    assert detect_mime(cabecera) == esperado


def test_detect_mime_con_exactamente_los_bytes_de_la_firma() -> None:
    assert detect_mime(b"\xff\xd8\xff") == JPEG
    assert detect_mime(b"\x89PNG\r\n\x1a\n") == PNG
    assert detect_mime(b"%PDF-") == PDF


def test_un_ejecutable_con_nombre_de_imagen_no_se_reconoce() -> None:
    """El nombre no se pasa a la función: lo único que decide es la cabecera."""
    assert detect_mime(files.elf()) is None and detect_mime(files.pe()) is None


# Tamaño ------------------------------------------------------------------------------------------


def test_el_tope_exacto_pasa_y_un_byte_mas_es_file_too_large() -> None:
    validate_upload(5_242_880, JPEG, "photo")
    with pytest.raises(FileTooLarge) as error:
        validate_upload(5_242_881, JPEG, "photo")
    assert (error.value.status, error.value.code, error.value.field) == (
        413,
        "file_too_large",
        "file",
    )


@pytest.mark.parametrize("tamano", [0, -1])
def test_un_tamano_no_positivo_se_rechaza(tamano: int) -> None:
    with pytest.raises((FileTooLarge, UnsupportedType, ValueError)):
        validate_upload(tamano, JPEG, "photo")


def test_un_byte_es_valido() -> None:
    validate_upload(1, PNG, "photo")


# Matriz kind x mime ------------------------------------------------------------------------------

PERMITIDOS = {
    ("photo", JPEG): True,
    ("photo", PNG): True,
    ("photo", PDF): False,
    ("consent", JPEG): True,
    ("consent", PNG): True,
    ("consent", PDF): True,
    ("other", JPEG): True,
    ("other", PNG): True,
    ("other", PDF): True,
}


@pytest.mark.parametrize(("par", "permitido"), sorted(PERMITIDOS.items()), ids=lambda x: str(x))
def test_matriz_kind_por_mime(par: tuple[str, str], permitido: bool) -> None:
    kind, mime = par
    if permitido:
        validate_upload(1024, mime, kind)
    else:
        with pytest.raises(UnsupportedType) as error:
            validate_upload(1024, mime, kind)
        assert (error.value.status, error.value.code, error.value.field) == (
            422,
            "unsupported_type",
            "file",
        )


@pytest.mark.parametrize("mime", ["text/html", "image/gif", "application/x-msdownload", ""])
def test_un_mime_fuera_de_los_tres_se_rechaza(mime: str) -> None:
    with pytest.raises(UnsupportedType):
        validate_upload(1024, mime, "other")


def test_un_kind_ajeno_se_rechaza() -> None:
    with pytest.raises((UnsupportedType, ValueError)):
        validate_upload(1024, JPEG, "avatar")


# Sensibilidad ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "sensible"), [("consent", True), ("other", True), ("photo", False)]
)
def test_kind_is_sensitive_lo_decide_el_servidor(kind: str, sensible: bool) -> None:
    assert kind_is_sensitive(kind) is sensible


def test_kind_is_sensitive_con_un_kind_ajeno_falla_en_vez_de_adivinar() -> None:
    with pytest.raises(ValueError):
        kind_is_sensitive("avatar")


# Huérfanos ---------------------------------------------------------------------------------------

A, B, C = UUID(int=1), UUID(int=2), UUID(int=3)
HA, HB, HC = "a" * 32, "b" * 32, "c" * 32


def test_find_orphans_sin_nada_en_ningun_lado_es_vacio() -> None:
    assert find_orphans({}, []) == OrphanReport(rows_without_object=(), objects_without_row=())


def test_find_orphans_con_todo_emparejado_es_vacio() -> None:
    assert find_orphans({A: HA, B: HB}, [HB, HA]) == OrphanReport((), ())


def test_find_orphans_una_fila_sin_objeto_se_informa_por_id() -> None:
    informe = find_orphans({A: HA, B: HB}, [HA])
    assert informe.rows_without_object == (B,) and informe.objects_without_row == ()


def test_find_orphans_un_objeto_sin_fila_se_informa_por_nombre() -> None:
    informe = find_orphans({A: HA}, [HA, HC])
    assert informe.rows_without_object == () and informe.objects_without_row == (HC,)


def test_find_orphans_ambos_lados_y_orden_estable() -> None:
    informe = find_orphans({C: HC, B: HB, A: HA}, [HB, "f" * 32, "d" * 32])
    assert informe.rows_without_object == (A, C)
    assert informe.objects_without_row == ("d" * 32, "f" * 32)


def test_find_orphans_con_solo_objetos_o_solo_filas() -> None:
    assert find_orphans({}, [HA]) == OrphanReport((), (HA,))
    assert find_orphans({A: HA}, []) == OrphanReport((A,), ())


def test_find_orphans_acepta_un_iterador_de_un_solo_uso() -> None:
    assert find_orphans({A: HA}, iter([HA])) == OrphanReport((), ())

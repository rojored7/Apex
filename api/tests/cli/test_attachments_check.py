"""`attachments-check [--as <correo>]` (S6-C1, US-147; S6-D22, S6-D76, S6-D80). Rojo C1.

Solo lectura: compara las filas de `attachments.attachments` con los objetos del almacenamiento
(`find_orphans`) y sale 0 sin huérfanos o 1 con ellos. Contrato que el Rojo asume (el Verde puede
discutirlo):
- la salida trae dos líneas de resumen `filas sin objeto: N` y `objetos sin fila: N`, y debajo la
  lista: los IDS de las filas sin objeto y los NOMBRES hexadecimales de los objetos sin fila;
  nunca el `filename_random` de una fila (con S3 es la clave del objeto);
- no escribe nada: ni filas de la tabla, ni de `audit_log` o `crypto_ops`, ni archivos del volumen
  (tampoco crea la carpeta `UPLOADS_DIR/attachments` si falta);
- `--as` atribuye la corrida a un admin activo; un correo desconocido o que no es admin sale 2;
  con `ENV=production` `--as` es obligatorio (2), como `sign-audit`.
El almacén sale de `storage_from_settings(Settings)`: la prueba apunta `UPLOADS_DIR` a `tmp_path`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from click.testing import Result
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.cli import app
from app.core.config import Settings
from tests.attachments._apoyo import insertar
from tests.cli._apoyo import conteos_de_tablas, correr
from tests.cli._apoyo_firma import Fabrica, admin
from tests.conftest import LIMPIAR_ATTACHMENTS

__all__ = ["admin"]

pytestmark = pytest.mark.usefixtures("reloj")


@pytest.fixture
def volumen(tmp_path: Path) -> Path:
    """`UPLOADS_DIR/attachments` con su carpeta creada."""
    carpeta = tmp_path / "uploads" / "attachments"
    carpeta.mkdir(parents=True)
    return carpeta


@pytest.fixture
def ajustes(settings_prueba: Settings, tmp_path: Path) -> Settings:
    return settings_prueba.model_copy(update={"UPLOADS_DIR": tmp_path / "uploads"})


@pytest.fixture
async def fabrica(limpiar_demo: Fabrica, engine: AsyncEngine) -> AsyncIterator[Fabrica]:
    try:
        yield limpiar_demo
    finally:
        async with engine.begin() as conexion:
            await conexion.execute(text(LIMPIAR_ATTACHMENTS))


async def _fila(
    fabrica: Fabrica, *, con_objeto: bool, volumen: Path, kind: str = "photo"
) -> tuple[UUID, str]:
    nombre = uuid4().hex
    async with fabrica() as sesion, sesion.begin():
        id_ = await insertar(sesion, owner=uuid4(), kind=kind, nombre=nombre)
    if con_objeto:
        (volumen / nombre).write_bytes(await _contenido(fabrica, id_, kind))
    return id_, nombre


async def _contenido(fabrica: Fabrica, id_: UUID, kind: str) -> bytes:
    """Un sensible lleva una cabecera `apx1.<su key_id>.…`; la foto, bytes cualquiera."""
    if kind == "photo":
        return b"x" * 10
    async with fabrica() as sesion:
        llave = await sesion.scalar(
            text("SELECT key_id FROM attachments.attachments WHERE id = :i"), {"i": id_}
        )
    return f"apx1.{llave}.A256GCM.bm9uY2U.Y2lwaGVy".encode("ascii")


def _check(
    ajustes: Settings, monkeypatch: pytest.MonkeyPatch, *args: str, env: Any = "dev"
) -> Result:
    return correr(app, ["attachments-check", *args], env, base=ajustes, monkeypatch=monkeypatch)


def _existe(ruta: Path) -> bool:
    return os.path.exists(ruta)


def _instantanea(volumen: Path) -> dict[str, tuple[int, int]]:
    return {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(volumen.iterdir())}


# Salidas ----------------------------------------------------------------------------------------


async def test_sin_huerfanos_sale_0_y_dice_cero_en_ambos_conteos(
    fabrica: Fabrica,
    volumen: Path,
    ajustes: Settings,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _fila(fabrica, con_objeto=True, volumen=volumen)
    await _fila(fabrica, con_objeto=True, volumen=volumen, kind="consent")

    resultado = _check(ajustes, monkeypatch, "--as", admin.email)

    assert resultado.exit_code == 0, resultado.output
    assert not isinstance(resultado.exception, NotImplementedError)
    assert "filas sin objeto: 0" in resultado.output
    assert "objetos sin fila: 0" in resultado.output


async def test_una_base_y_un_volumen_vacios_tambien_salen_0(
    fabrica: Fabrica, volumen: Path, ajustes: Settings, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = _check(ajustes, monkeypatch, "--as", admin.email)

    assert resultado.exit_code == 0, resultado.output
    assert "filas sin objeto: 0" in resultado.output and "objetos sin fila: 0" in resultado.output


async def test_con_huerfanos_sale_1_y_lista_ids_y_nombres_hexadecimales(
    fabrica: Fabrica,
    volumen: Path,
    ajustes: Settings,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sin_objeto, nombre_sin_objeto = await _fila(fabrica, con_objeto=False, volumen=volumen)
    _, nombre_emparejado = await _fila(fabrica, con_objeto=True, volumen=volumen)
    huerfano_hex = uuid4().hex
    (volumen / huerfano_hex).write_bytes(b"sin fila")

    resultado = _check(ajustes, monkeypatch, "--as", admin.email)

    assert resultado.exit_code == 1, resultado.output
    assert not isinstance(resultado.exception, NotImplementedError)
    assert "filas sin objeto: 1" in resultado.output
    assert "objetos sin fila: 1" in resultado.output
    assert str(sin_objeto) in resultado.output  # la fila se nombra por su id
    assert huerfano_hex in resultado.output  # el objeto, por su nombre hexadecimal
    # Nunca el `filename_random` de una fila (con S3 es la clave del objeto).
    assert nombre_sin_objeto not in resultado.output
    assert nombre_emparejado not in resultado.output


async def test_solo_filas_sin_objeto_o_solo_objetos_sin_fila_tambien_salen_1(
    fabrica: Fabrica, volumen: Path, ajustes: Settings, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _fila(fabrica, con_objeto=False, volumen=volumen)
    primera = _check(ajustes, monkeypatch, "--as", admin.email)
    assert primera.exit_code == 1 and "filas sin objeto: 1" in primera.output
    assert "objetos sin fila: 0" in primera.output

    async with fabrica() as sesion, sesion.begin():
        await sesion.execute(text(LIMPIAR_ATTACHMENTS))
    (volumen / uuid4().hex).write_bytes(b"x")
    segunda = _check(ajustes, monkeypatch, "--as", admin.email)
    assert segunda.exit_code == 1 and "objetos sin fila: 1" in segunda.output
    assert "filas sin objeto: 0" in segunda.output


# `key_id` contra la cabecera del blob (V9 M1) -----------------------------------------------------


async def test_un_sensible_con_key_id_distinto_del_blob_se_lista_y_sale_1(
    fabrica: Fabrica,
    volumen: Path,
    ajustes: Settings,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bueno, _ = await _fila(fabrica, con_objeto=True, volumen=volumen, kind="consent")
    manipulado, _ = await _fila(fabrica, con_objeto=True, volumen=volumen, kind="other")
    async with fabrica() as sesion, sesion.begin():
        await sesion.execute(
            text("UPDATE attachments.attachments SET key_id = :k WHERE id = :i"),
            {"k": uuid4(), "i": manipulado},
        )

    resultado = _check(ajustes, monkeypatch, "--as", admin.email)

    assert resultado.exit_code == 1, resultado.output
    assert "filas sin objeto: 0" in resultado.output
    assert "objetos sin fila: 0" in resultado.output
    assert "key_id distinto del blob: 1" in resultado.output
    assert f"  key_id distinto del blob: {manipulado}" in resultado.output
    assert str(bueno) not in resultado.output


async def test_un_objeto_sensible_que_no_es_un_blob_apx1_cuenta_como_discrepancia(
    fabrica: Fabrica,
    volumen: Path,
    ajustes: Settings,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    id_, nombre = await _fila(fabrica, con_objeto=True, volumen=volumen, kind="consent")
    (volumen / nombre).write_bytes(b"no es un blob")

    resultado = _check(ajustes, monkeypatch, "--as", admin.email)

    assert resultado.exit_code == 1, resultado.output
    assert f"  key_id distinto del blob: {id_}" in resultado.output


async def test_la_foto_no_se_compara_con_ningun_blob(
    fabrica: Fabrica, volumen: Path, ajustes: Settings, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _fila(fabrica, con_objeto=True, volumen=volumen)

    resultado = _check(ajustes, monkeypatch, "--as", admin.email)

    assert resultado.exit_code == 0, resultado.output
    assert "key_id distinto" not in resultado.output


# Solo lectura -------------------------------------------------------------------------------------


async def test_no_escribe_nada_ni_en_la_base_ni_en_el_volumen(
    fabrica: Fabrica,
    volumen: Path,
    ajustes: Settings,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
) -> None:
    await _fila(fabrica, con_objeto=False, volumen=volumen)
    await _fila(fabrica, con_objeto=True, volumen=volumen)
    (volumen / uuid4().hex).write_bytes(b"sin fila")
    async with fabrica() as sesion:
        antes_tablas = await conteos_de_tablas(sesion)
        antes_adjuntos = await sesion.scalar(text("SELECT count(*) FROM attachments.attachments"))
    antes_volumen = _instantanea(volumen)

    resultado = _check(ajustes, monkeypatch, "--as", admin.email)

    assert resultado.exit_code == 1, resultado.output
    async with fabrica() as sesion:
        assert await conteos_de_tablas(sesion) == antes_tablas  # ni audit_log ni crypto_ops
        assert await sesion.scalar(text("SELECT count(*) FROM attachments.attachments")) == (
            antes_adjuntos
        )
    assert _instantanea(volumen) == antes_volumen


async def test_si_la_carpeta_del_volumen_no_existe_no_la_crea_y_lo_reporta_como_filas_sin_objeto(
    fabrica: Fabrica,
    ajustes: Settings,
    admin: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async with fabrica() as sesion, sesion.begin():
        await insertar(sesion, owner=uuid4())

    resultado = _check(ajustes, monkeypatch, "--as", admin.email)

    assert resultado.exit_code == 1, resultado.output
    assert "filas sin objeto: 1" in resultado.output
    assert not (tmp_path / "uploads").exists()


async def test_el_comando_no_borra_los_huerfanos(
    fabrica: Fabrica, volumen: Path, ajustes: Settings, admin: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    huerfano = uuid4().hex
    (volumen / huerfano).write_bytes(b"sin fila")

    resultado = _check(ajustes, monkeypatch, "--as", admin.email)

    assert resultado.exit_code == 1 and huerfano in resultado.output
    assert _existe(volumen / huerfano)  # reparar es decisión de la persona (S6-D76)


# --as ----------------------------------------------------------------------------------------


async def test_un_correo_desconocido_sale_2_y_no_revisa_nada(
    fabrica: Fabrica, volumen: Path, ajustes: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    sin_objeto, _ = await _fila(fabrica, con_objeto=False, volumen=volumen)

    resultado = _check(ajustes, monkeypatch, "--as", "nadie@test.apex")

    assert resultado.exit_code == 2, resultado.output
    assert str(sin_objeto) not in resultado.output


async def test_en_produccion_sin_as_sale_2(
    fabrica: Fabrica, volumen: Path, ajustes: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = _check(ajustes, monkeypatch, env="production")

    assert resultado.exit_code == 2
    assert "--as <correo> es obligatorio con ENV=production" in resultado.output


async def test_sin_as_en_dev_funciona_como_el_usuario_tecnico(
    fabrica: Fabrica, volumen: Path, ajustes: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = _check(ajustes, monkeypatch)

    assert resultado.exit_code == 0, resultado.output


def test_el_comando_figura_en_la_ayuda_del_cli() -> None:
    from typer.testing import CliRunner

    ayuda = CliRunner().invoke(app, ["--help"])

    assert ayuda.exit_code == 0 and "attachments-check" in ayuda.output

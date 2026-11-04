"""`core/crypto/digest.py`: `digest_file` (S4B-B2; S4B-D20, S4B-D59; movido desde `archive.py` en la
revisión de B3a, S4B-D134) y las constantes de `archive.py`.

- coincide con `sha256_hex` del bus para 5 MB, para un archivo vacío y para tamaños de bloque
  distintos (1 byte antes del límite, justo en él, 1 después);
- no carga el archivo entero: `Path.read_bytes`/`read_text` prohibidos por `monkeypatch` y el pico
  de memoria de un archivo de 24 MB queda muy por debajo de su tamaño;
- un archivo inexistente lanza `FileNotFoundError`; un enlace simbólico se rechaza (`O_NOFOLLOW`);
  un `chunk_size` no positivo lanza `ValueError`;
- constantes: `DIGEST_CHUNK` 1 MiB, `AGE_BINARY` `/usr/bin/age`, `AGE_TIMEOUT_S` 600.
"""

from __future__ import annotations

import os
import threading
import time
import tracemalloc
from pathlib import Path
from typing import Any

import pytest

from app.core.crypto.archive import AGE_BINARY, AGE_TIMEOUT_S
from app.core.crypto.digest import DIGEST_CHUNK, digest_file, sha256_hex

MIB = 1 << 20


def _archivo(carpeta: Path, tamano: int, nombre: str = "a.bin") -> Path:
    ruta = carpeta / nombre
    patron = bytes(range(251))
    with ruta.open("wb") as destino:
        restante = tamano
        while restante > 0:
            trozo = patron[: min(restante, len(patron))]
            destino.write(trozo)
            restante -= len(trozo)
    return ruta


def test_las_constantes_son_las_del_plan() -> None:
    assert DIGEST_CHUNK == 1 << 20
    assert AGE_BINARY == "/usr/bin/age"
    assert AGE_TIMEOUT_S == 600


def test_digest_file_coincide_con_sha256_hex_para_5_mb(tmp_path: Path) -> None:
    ruta = _archivo(tmp_path, 5 * MIB)

    assert digest_file(ruta) == sha256_hex(ruta.read_bytes())


def test_digest_file_de_un_archivo_vacio(tmp_path: Path) -> None:
    ruta = _archivo(tmp_path, 0)

    assert digest_file(ruta) == sha256_hex(b"")


@pytest.mark.parametrize("tamano", [4095, 4096, 4097, 3 * 4096])
def test_digest_file_con_bloque_pequeno_en_los_bordes(tmp_path: Path, tamano: int) -> None:
    ruta = _archivo(tmp_path, tamano)

    assert digest_file(ruta, 4096) == sha256_hex(ruta.read_bytes())
    assert digest_file(ruta, 1) == sha256_hex(ruta.read_bytes())


def test_digest_file_devuelve_hexadecimal_en_minusculas_de_64(tmp_path: Path) -> None:
    valor = digest_file(_archivo(tmp_path, 10))

    assert len(valor) == 64
    assert valor == valor.lower()
    assert set(valor) <= set("0123456789abcdef")


def test_digest_file_no_lee_el_archivo_entero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ruta = _archivo(tmp_path, 5 * MIB)
    esperado = sha256_hex(ruta.read_bytes())

    def prohibido(*_a: object, **_k: object) -> bytes:
        raise AssertionError("digest_file no puede leer el archivo entero")

    monkeypatch.setattr(Path, "read_bytes", prohibido)
    monkeypatch.setattr(Path, "read_text", prohibido)

    assert digest_file(ruta) == esperado


def test_digest_file_de_24_mb_no_sube_la_memoria_a_su_tamano(tmp_path: Path) -> None:
    ruta = _archivo(tmp_path, 24 * MIB)
    tracemalloc.start()
    try:
        digest_file(ruta)
        _, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert pico < 8 * MIB


def test_un_archivo_inexistente_lanza(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        digest_file(tmp_path / "no-existe.bin")


@pytest.mark.parametrize("tamano_de_bloque", [0, -1])
def test_un_chunk_size_no_positivo_lanza_value_error(tmp_path: Path, tamano_de_bloque: int) -> None:
    with pytest.raises(ValueError):
        digest_file(_archivo(tmp_path, 10), tamano_de_bloque)


def test_un_enlace_simbolico_se_rechaza(tmp_path: Path) -> None:
    real = _archivo(tmp_path, 100)
    enlace = tmp_path / "enlace.bin"
    try:
        os.symlink(real, enlace)
    except (OSError, NotImplementedError):
        pytest.skip("enlaces simbólicos sin privilegios en este equipo; corren en CI/Linux")

    with pytest.raises(OSError):
        digest_file(enlace)


def test_un_directorio_lanza(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        digest_file(tmp_path)


# S4B-B2 (revisión de seguridad): FIFO, tope de lectura y archivo que crece ------------------------

sin_fifo = pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="mkfifo no existe en Windows")


@sin_fifo
def test_un_fifo_da_error_inmediato_y_no_cuelga(tmp_path: Path) -> None:
    fifo = tmp_path / "tuberia"
    os.mkfifo(fifo)
    # Si `digest_file` bloqueara en `open`, este temporizador abre el otro extremo a los 3 s.
    liberador = threading.Timer(3, lambda: os.close(os.open(fifo, os.O_WRONLY)))
    liberador.start()
    try:
        inicio = time.perf_counter()
        with pytest.raises(OSError):
            digest_file(fifo)
        assert time.perf_counter() - inicio < 2
    finally:
        liberador.cancel()


def test_un_archivo_que_no_es_regular_se_rechaza_con_oserror(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        digest_file(tmp_path)


def test_max_bytes_igual_al_tamano_se_acepta(tmp_path: Path) -> None:
    ruta = _archivo(tmp_path, 1000)

    assert digest_file(ruta, 64, max_bytes=1000) == sha256_hex(ruta.read_bytes())


def test_un_archivo_mas_grande_que_max_bytes_aborta_con_oserror(tmp_path: Path) -> None:
    ruta = _archivo(tmp_path, 1001)

    with pytest.raises(OSError):
        digest_file(ruta, 64, max_bytes=1000)


def test_max_bytes_cero_acepta_el_archivo_vacio_y_rechaza_uno_con_datos(tmp_path: Path) -> None:
    assert digest_file(_archivo(tmp_path, 0), max_bytes=0) == sha256_hex(b"")
    with pytest.raises(OSError):
        digest_file(_archivo(tmp_path, 1, "b.bin"), max_bytes=0)


def test_un_archivo_que_crece_durante_la_lectura_aborta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ruta = _archivo(tmp_path, 100)
    real = os.fdopen

    class Crece:
        def __init__(self, archivo: Any) -> None:
            self._a = archivo
            self._extra = 0

        def read(self, n: int) -> bytes:
            datos: bytes = self._a.read(n)
            if not datos and self._extra < 5:
                self._extra += 1
                return b"x" * 10  # el archivo sigue creciendo tras el EOF aparente
            return datos

        def __enter__(self) -> Crece:
            return self

        def __exit__(self, *_a: object) -> None:
            self._a.close()

    monkeypatch.setattr(os, "fdopen", lambda *a, **k: Crece(real(*a, **k)))

    with pytest.raises(OSError):
        digest_file(ruta, 64, max_bytes=100)

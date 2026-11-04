"""Autoprueba del `age` falso (`tests/factories/fake_age.py`, S4B-D89): lo que las demás pruebas
de la KEK suponen de él. Corre en todas las plataformas (en Windows con el entorno heredado,
porque `cmd.exe` no arranca con `env={}`)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.factories.fake_age import (
    MENSAJE_SIN_TTY,
    configurar,
    desenvolver_falso,
    envolver_falso,
    fake_age,
    llamadas,
)

ENTORNO = None if sys.platform == "win32" else {}


def _correr(
    ejecutable: Path, *args: str, entrada: bytes = b""
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # noqa: S603
        [str(ejecutable), *args], input=entrada, env=ENTORNO, capture_output=True, check=False
    )


def test_p_envuelve_la_entrada_y_d_la_desenvuelve(tmp_path: Path) -> None:
    ejecutable = fake_age(tmp_path)
    kek = bytes(range(32))

    cifrado = _correr(ejecutable, "-p", "-o", "/dev/stdout", entrada=kek)
    plano = _correr(ejecutable, "-d", entrada=cifrado.stdout)

    assert cifrado.returncode == 0 and cifrado.stdout == envolver_falso(kek)
    assert plano.returncode == 0 and plano.stdout == kek
    assert desenvolver_falso(cifrado.stdout) == kek


def test_d_acepta_un_archivo_y_o(tmp_path: Path) -> None:
    ejecutable = fake_age(tmp_path)
    origen = tmp_path / "k.age"
    origen.write_bytes(envolver_falso(b"x" * 32))
    destino = tmp_path / "k.bin"

    resultado = _correr(ejecutable, "-d", "-o", str(destino), str(origen))

    assert resultado.returncode == 0 and destino.read_bytes() == b"x" * 32 and not resultado.stdout


def test_un_archivo_ajeno_o_una_opcion_desconocida_salen_con_1(tmp_path: Path) -> None:
    ejecutable = fake_age(tmp_path)

    ajeno = _correr(ejecutable, "-d", entrada=b"no es age")
    opcion = _correr(ejecutable, "--passphrase-file", "x")

    assert ajeno.returncode == 1 and opcion.returncode == 1


def test_sin_tty_reproduce_el_mensaje_de_age(tmp_path: Path) -> None:
    ejecutable = fake_age(tmp_path)
    configurar(ejecutable, no_tty=True)

    resultado = _correr(ejecutable, "-p")

    assert resultado.returncode == 1
    assert MENSAJE_SIN_TTY in resultado.stderr.decode()


def test_registra_argv_y_entorno_de_cada_llamada(tmp_path: Path) -> None:
    ejecutable = fake_age(tmp_path)

    _correr(ejecutable, "-p", entrada=b"k" * 32)

    (llamada,) = llamadas(ejecutable)
    assert llamada["argv"] == ["-p"] and isinstance(llamada["pid"], int)

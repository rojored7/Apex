"""Corre un comando bajo un pseudoterminal y le teclea una frase (solo Linux; S4B-B3a, S4B-D89).

`age -p` y `age -d` piden la frase por `/dev/tty`; `pty.fork` da una terminal de control al hijo y
el padre escribe la frase cuando aparece el aviso. En Windows no existe `pty`: la función salta la
prueba con `pytest.skip` (los archivos `*_real_age.py` ya llevan `skipif`).
"""

from __future__ import annotations

import os
import re
import select
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

AVISO_DE_FRASE = re.compile(rb"(?i)passphrase[^\n:]*:\s*$")


def correr_con_pty(
    args: Sequence[str],
    frase: str,
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    timeout_s: float = 60.0,
) -> tuple[int, str]:
    """Ejecuta `args` con terminal de control; cada vez que el hijo pide una frase teclea `frase`.

    Devuelve `(código de salida, transcripción)`. La transcripción puede incluir la frase generada
    por `age` cuando `frase` es vacía: las pruebas no deben imprimirla ni registrarla.
    """
    if sys.platform == "win32":
        pytest.skip("pty no existe en Windows; corre en CI/Linux")
    import pty

    pid, fd = pty.fork()
    if pid == 0:  # hijo
        try:
            if cwd is not None:
                os.chdir(cwd)
            os.execvpe(  # noqa: S606
                args[0], list(args), dict(env) if env is not None else dict(os.environ)
            )
        finally:
            os._exit(127)
    salida = b""
    desde = 0  # lo anterior a este índice ya se contestó
    limite = time.monotonic() + timeout_s
    while time.monotonic() < limite:
        listo, _, _ = select.select([fd], [], [], 0.2)
        if not listo:
            continue
        try:
            trozo = os.read(fd, 4096)
        except OSError:
            break
        if not trozo:
            break
        salida += trozo
        if AVISO_DE_FRASE.search(salida[desde:]):
            desde = len(salida)
            os.write(fd, frase.encode() + b"\n")
    else:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
        raise TimeoutError("el comando bajo pty no terminó a tiempo")
    _, estado = os.waitpid(pid, 0)
    codigo = os.waitstatus_to_exitcode(estado)
    return codigo, salida.decode(errors="replace")

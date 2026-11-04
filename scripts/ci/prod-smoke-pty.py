"""Corre un comando bajo un pseudoterminal y teclea la frase cuando age la pide.

Lo usa scripts/ci/prod-smoke.sh dentro de la imagen apex-api (que trae age y Python) para fabricar
una copia REAL de la KEK con `age -p`: age solo lee la frase de la terminal. PTY_ARGV es una lista
JSON; PTY_FRASE llega por el entorno del contenedor y no se imprime ni se guarda.
"""

import json
import os
import pty
import re
import select
import sys
import time

AVISO = re.compile(rb"(?i)passphrase[^\n:]*:\s*$")


def correr(args: list[str], frase: str, timeout: float = 120.0) -> tuple[int, str]:
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.execvpe(args[0], list(args), dict(os.environ))
        finally:
            os._exit(127)
    salida, desde, limite = b"", 0, time.monotonic() + timeout
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
        if AVISO.search(salida[desde:]):
            desde = len(salida)
            os.write(fd, frase.encode() + b"\n")
    else:
        os.kill(pid, 9)
        raise TimeoutError("el comando bajo pty no terminó a tiempo")
    _, estado = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(estado), salida.decode(errors="replace")


if __name__ == "__main__":
    codigo, _texto = correr(json.loads(os.environ["PTY_ARGV"]), os.environ["PTY_FRASE"])
    sys.exit(codigo)

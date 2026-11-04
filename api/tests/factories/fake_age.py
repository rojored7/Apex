"""`age` falso para las pruebas de la KEK (S4B-B3a, S4B-D89).

`fake_age(tmp_path) -> Path` escribe un ejecutable que imita `age -p` y `age -d` sin terminal:
- `-p [-o SALIDA]`: lee la KEK por `stdin` y escribe `fake-age-v1\\n` + base64 (a `stdout`, o a
  `SALIDA` si no es `/dev/stdout` ni `-`);
- `-d [-o SALIDA] [ARCHIVO]`: lee `ARCHIVO` o `stdin`, desenvuelve y escribe a `stdout`/`SALIDA`;
  si la entrada no empieza por `fake-age-v1` sale 1 como `age` ante un archivo ajeno;
- cualquier otra opción (`--passphrase`, `--passphrase-file`, `-i`...) sale 1 como `age`.

El ejecutable que devuelve `fake_age` es directamente invocable con `Popen([ruta, ...])`: en Linux
es un script con `#!` y modo 0o755; en Windows es un `.cmd` que llama a `sys.executable`.

El hijo recibe `env={}` en producción, así que el control NO va por variables de entorno
(el plan decía `FAKE_AGE_NO_TTY=1`: desviación declarada en el cuaderno). Se controla con un
archivo junto al script: `configurar(ruta, no_tty=True, dormir_s=30)`. Cada llamada anota en
`llamadas.jsonl` sus `argv`, su entorno (sin `LC_CTYPE`, que el intérprete de Python 3.12 inyecta
con la coerción de locale C: S4B-D122) y su `pid`; `llamadas(ruta)` las lee, y las pruebas afirman
`entorno == {}` y que la KEK no aparece en `argv`. Con `dormir_s` el falso duerme escribiendo
`latido` cada 0,1 s (la prueba de plazo comprueba que el latido se detiene tras `kill`).
"""

from __future__ import annotations

import base64
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

MAGIA = b"fake-age-v1\n"
MENSAJE_SIN_TTY = (
    "age: error: could not read passphrase: failed to open /dev/tty: "
    "open /dev/tty: no such device or address"
)

_SCRIPT = r"""
import base64, json, os, sys, time

MAGIA = b"fake-age-v1\n"
AQUI = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
control_ruta = os.path.join(AQUI, "control.json")
control = json.load(open(control_ruta)) if os.path.exists(control_ruta) else {}
with open(os.path.join(AQUI, "llamadas.jsonl"), "a") as f:
    entorno = {k: v for k, v in os.environ.items() if k != "LC_CTYPE"}
    f.write(json.dumps({"argv": args, "env": entorno, "pid": os.getpid()}) + "\n")

def falla(texto, codigo=1):
    sys.stderr.write(texto + "\n")
    sys.exit(codigo)

if control.get("no_tty"):
    falla("MENSAJE_SIN_TTY")
if control.get("dormir_s"):
    fin = time.monotonic() + control["dormir_s"]
    while time.monotonic() < fin:
        with open(os.path.join(AQUI, "latido"), "w") as f:
            f.write(str(time.monotonic()))
        time.sleep(0.1)

modo = None
salida = None
entrada = None
i = 0
while i < len(args):
    a = args[i]
    if a in ("-p", "-d"):
        modo = a
    elif a == "-o":
        i += 1
        salida = args[i] if i < len(args) else None
    elif a.startswith("-") and a != "-":
        falla("age: error: flag provided but not defined: " + a)
    else:
        entrada = a
    i += 1
if modo is None:
    falla("age: error: missing mode")

if modo == "-p":
    plano = sys.stdin.buffer.read()
    resultado = MAGIA + base64.b64encode(plano)
else:
    if entrada is None or entrada == "-":
        crudo = sys.stdin.buffer.read()
    else:
        crudo = open(entrada, "rb").read()
    if not crudo.startswith(MAGIA):
        falla("age: error: failed to read header: parsing age header: unknown version")
    resultado = base64.b64decode(crudo[len(MAGIA):])

if salida in (None, "-", "/dev/stdout"):
    sys.stdout.buffer.write(resultado)
    sys.stdout.buffer.flush()
else:
    with open(salida, "wb") as f:
        f.write(resultado)
""".replace("MENSAJE_SIN_TTY", MENSAJE_SIN_TTY)


def envolver_falso(plano: bytes) -> bytes:
    """Lo que escribe el falso con `-p`: el archivo `.age` de la KEK `plano`."""
    return MAGIA + base64.b64encode(plano)


def desenvolver_falso(datos: bytes) -> bytes:
    """Inversa de `envolver_falso`; `ValueError` si `datos` no es del falso."""
    if not datos.startswith(MAGIA):
        raise ValueError("no es un archivo del age falso")
    return base64.b64decode(datos[len(MAGIA) :])


def fake_age(tmp_path: Path) -> Path:
    """Crea el `age` falso dentro de `tmp_path/age-falso/` y devuelve su ruta ejecutable."""
    carpeta = tmp_path / "age-falso"
    carpeta.mkdir(parents=True, exist_ok=True)
    script = carpeta / "age_falso.py"
    if os.name == "nt":
        script.write_text(_SCRIPT, encoding="utf-8")
        lanzador = carpeta / "age.cmd"
        lanzador.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
        return lanzador
    script.write_text(f"#!{sys.executable}\n{_SCRIPT}", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def configurar(ejecutable: Path, **opciones: Any) -> None:
    """Escribe `control.json` junto al falso: `no_tty=True` o `dormir_s=<segundos>`."""
    (ejecutable.parent / "control.json").write_text(json.dumps(opciones), encoding="utf-8")


def llamadas(ejecutable: Path) -> list[dict[str, Any]]:
    """Las invocaciones registradas: `{"argv": [...], "env": {...}, "pid": N}`."""
    ruta = ejecutable.parent / "llamadas.jsonl"
    if not ruta.exists():
        return []
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines() if linea]


def latido(ejecutable: Path) -> str | None:
    """Último latido del falso dormido (`None` si nunca durmió)."""
    ruta = ejecutable.parent / "latido"
    return ruta.read_text(encoding="utf-8") if ruta.exists() else None

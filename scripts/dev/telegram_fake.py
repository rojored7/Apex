#!/usr/bin/env python3
"""Telegram falso para desarrollo (S5-B4; S5-D78).

Servidor HTTP mínimo con la biblioteca estándar: acepta `POST /bot<token>/sendMessage`, escribe a
stdout UNA línea con el JSON recibido (nunca el token) y responde como la API real. Solo corre en
el perfil `avisos` de `infra/compose.dev.yml`; la lógica vive en `handle` (pura, sin red).
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_RUTA = re.compile(r"/bot[^/]+/(?P<metodo>[A-Za-z]+)")
MAX_BODY = 1024 * 1024
_contador = {"message_id": 0}


def body_length(cabecera: str | None) -> int:
    """`Content-Length` acotado a `0..MAX_BODY`; un valor ilegible cuenta como 0."""
    try:
        largo = int(cabecera or 0)
    except ValueError:
        return 0
    return max(0, min(largo, MAX_BODY))


def _error(estado: int, descripcion: str) -> tuple[int, dict[str, object], str | None]:
    return estado, {"ok": False, "error_code": estado, "description": descripcion}, None


def handle(method: str, path: str, body: bytes) -> tuple[int, dict[str, object], str | None]:
    """`(estado HTTP, cuerpo JSON de la respuesta, línea para stdout o None)`."""
    ruta = _RUTA.fullmatch(path)
    if ruta is None or ruta.group("metodo") != "sendMessage":
        return _error(404, "Not Found")
    if method != "POST":
        return _error(405, "Method Not Allowed")
    try:
        datos = json.loads(body)
    except ValueError:
        return _error(400, "Bad Request: invalid json")
    if not isinstance(datos, dict):
        return _error(400, "Bad Request: object expected")
    if not datos.get("chat_id"):
        return _error(400, "Bad Request: chat_id is empty")
    if not isinstance(datos.get("text"), str) or not datos["text"]:
        return _error(400, "Bad Request: text is empty")
    _contador["message_id"] += 1
    respuesta: dict[str, object] = {"ok": True, "result": {"message_id": _contador["message_id"]}}
    return 200, respuesta, json.dumps(datos, ensure_ascii=False, separators=(",", ":"))


class _Manejador(BaseHTTPRequestHandler):
    def _atender(self) -> None:
        largo = body_length(self.headers.get("Content-Length"))
        cuerpo = self.rfile.read(largo) if largo else b""
        estado, respuesta, linea = handle(self.command, self.path, cuerpo)
        if linea is not None:
            print(linea, flush=True)
        datos = json.dumps(respuesta).encode()
        self.send_response(estado)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    do_GET = do_POST = do_PUT = do_DELETE = _atender

    def log_message(self, format: str, *args: object) -> None:
        """Sin log de acceso: la ruta lleva el token."""


def main(argv: Sequence[str] | None = None) -> int:
    analizador = argparse.ArgumentParser(description="Telegram falso para desarrollo (S5-D78).")
    analizador.add_argument("--host", default="0.0.0.0")  # noqa: S104 - solo la red de compose
    analizador.add_argument("--port", type=int, default=8081)
    args = analizador.parse_args(argv)
    servidor = ThreadingHTTPServer((args.host, args.port), _Manejador)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

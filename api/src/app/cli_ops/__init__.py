"""Comandos de la capa de aplicación del CLI, un archivo por familia (S4B-D28).

Solo `cli.py` importa este paquete (S4B-D76); cada archivo importa a lo sumo `app.cli_base`.
`register_ops(app)` registra en el `Typer` los comandos que nacen aquí (B1 en adelante); en B0
no hay ninguno.
"""

from __future__ import annotations

import typer


def register_ops(app: typer.Typer) -> None:
    """Registra los comandos de `cli_ops/` en `app`. Vacío hasta B1."""
    del app

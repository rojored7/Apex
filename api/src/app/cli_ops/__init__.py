"""Comandos de la capa de aplicación del CLI, un archivo por familia (S4B-D28).

Solo `cli.py` importa este paquete (S4B-D76); cada archivo importa a lo sumo `app.cli_base`
(y, para B1, su paquete de aplicación: `seed` o `imports`). `register_ops(app)` registra en el
`Typer` los comandos que nacen aquí: `import-members` desde B1 y, desde B3a, `export-kek`,
`verify-kek-backup` y `restore-kek`; desde B3b, `rotate-key` y `retire-key`.
"""

from __future__ import annotations

import typer

from app.cli_ops import (
    import_members,
    kek,
    migrate_provider,
    notify,
    retire_key,
    retire_local_kek,
    rotate_kek,
    rotate_key,
    seed_notifications,
)


def register_ops(app: typer.Typer) -> None:
    """Registra los comandos de `cli_ops/` en `app`."""
    import_members.register(app)
    kek.register(app)
    rotate_key.register(app)
    retire_key.register(app)
    migrate_provider.register(app)  # S5-B2
    rotate_kek.register(app)  # S5-B2 (con --trim)
    retire_local_kek.register(app)  # S5-B2
    seed_notifications.register(app)  # S5-B6
    notify.register(app)  # S5-B7 (provisional: --generate-only)

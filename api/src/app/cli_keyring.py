"""Carga del keyring de los comandos que cifran (S4B-D30, D62); extraída de `cli_base.py` en B1.

Solo la importa `cli_base.crypto_runtime`. Cada corrida abre las DEK y las deja en el keyring del
proceso; si no se creó ninguna llave nueva, la transacción se deshace: las filas `unwrap` de
`crypto_ops` son ruido de cada arranque y una segunda corrida idempotente (`seed --demo`,
`import-members`) no debe dejar rastro nuevo (US-111, criterio de idempotencia).
"""

from __future__ import annotations

from typing import Any

import typer
from sqlalchemy import select

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto import oplog
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.errors import CryptoError, CryptoUnavailable
from app.core.crypto.models import CryptoKey
from app.core.crypto.provider import ProviderResolver, current_provider

_RAZON = {
    "sealed": "OpenBao sellado: desellarlo antes de continuar",
    "unreachable": "OpenBao inalcanzable: revise la red y OPENBAO_ADDR",
    "forbidden": "OpenBao rechazó el token del servicio",
    "not_loaded": "las llaves no están cargadas",
}


async def load_keyring(session: Any, resolver: ProviderResolver, *, persist: bool = True) -> None:
    """Bajo `SYSTEM_USER_ID`: abre cada DEK `active` existente (si una no se desenvuelve,
    `unwrap_failed`, salida 2 y ningún `INSERT`: S4B-D62) y luego `ensure_keys`; confirma solo
    si `ensure_keys` creó llaves (hay filas `wrap` pendientes) y `persist`, si no, deshace.
    `persist=False` (`import-members --dry-run`): las llaves faltantes viven solo en el keyring
    del proceso y no se escribe nada, ni en `crypto_keys` ni en `crypto_ops`."""
    proveedor = current_provider()
    with actor_scope(SYSTEM_USER_ID):
        async with session.begin():
            filas = await session.execute(
                select(CryptoKey.provider, CryptoKey.wrapped_material).where(
                    CryptoKey.state == "active", CryptoKey.purpose != "sign"
                )
            )
            try:
                for nombre, envuelta in filas.all():
                    await resolver(nombre).unwrap(envuelta)
            except CryptoUnavailable as error:
                typer.echo(f"crypto: {_RAZON[error.reason]}", err=True)
                raise typer.Exit(code=2) from None
            except CryptoError:
                typer.echo("crypto: unwrap_failed: una DEK activa no se abre con la KEK", err=True)
                raise typer.Exit(code=2) from None
            await ensure_keys(session, proveedor, resolver)
            creadas = any(fila.verb == "wrap" for fila in oplog.pending_rows())
            if not (persist and creadas):
                await session.rollback()  # nada que guardar: sin filas `unwrap`

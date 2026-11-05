"""Manifiesto de respaldo firmado y reciente para los comandos de custodia (S5-D72; stub del Rojo).

Capa de aplicación (como `cli_keyring.py`): la usan `retire-key`, `migrate-provider`, `rotate-kek` y
`retire-local-kek`; desde S5-B2 también reúne las pruebas de custodia de esos tres (S5-D186):
`custody_proofs` (verify-kek-backup reciente + manifiesto firmado con instantánea de OpenBao) y
`confirmation_error` (palabra escrita). Verifica la firma `minisign` por
`bus.verified_manifest_bytes`,
nunca con un binario. Solo la importan los archivos de `cli_ops/`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Literal, NoReturn

import typer
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.crypto import service
from app.core.crypto.bus import verified_manifest_bytes
from app.core.crypto.file_digest import digest_file
from app.core.crypto.migration import MigrationInProgress, MigrationResult
from app.core.crypto.service import RotationInProgress
from app.core.db import DatabaseBusy, translate_busy

MANIFEST_MAX_AGE: Final = timedelta(hours=24)
MAX_MANIFEST_BYTES: Final = 1 << 20
CLOCK_SKEW: Final = timedelta(minutes=5)
MAX_BACKUP_BYTES: Final = 50 * 1024**3
_SET_RE: Final = re.compile(r"(apex|pre-deploy|pre-restore)-[0-9]{8}-[0-9]{6}")
_SHA_RE: Final = re.compile(r"[0-9a-f]{64}")

Reason = Literal["ok", "no_signature", "bad_signature", "stale", "no_snapshot", "invalid"]


@dataclass(frozen=True)
class ManifestCheck:
    """Resultado: `ok`, el motivo, el `created_at` leído (si se pudo) y si el manifiesto trae una
    instantánea de OpenBao con `verified = true`."""

    ok: bool
    reason: Reason
    created_at: datetime | None
    has_snapshot: bool


def _fail(reason: Reason, created_at: datetime | None = None) -> ManifestCheck:
    return ManifestCheck(False, reason, created_at, False)


def _placed_ok(path: Path, base: Path | None) -> bool:
    """Ni el manifiesto ni su firma son enlaces y, con `base`, `path` resuelto queda bajo ella."""
    try:
        firma = path.with_name(path.name + ".minisig")
        if path.is_symlink() or firma.is_symlink():
            return False
        return base is None or path.resolve().is_relative_to(base.resolve())
    except OSError:
        return False


def _read_fields(crudo: bytes) -> tuple[datetime, bool, dict[str, Any] | None] | None:
    """`(created_at, verify == "ok", openbao_snapshot)` de los bytes YA firmados, o `None`."""
    try:
        datos = json.loads(crudo.decode("utf-8"))
        creado = datetime.strptime(datos["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        snapshot = datos.get("openbao_snapshot")
        nombre = datos["name"]
        if not isinstance(nombre, str) or not _SET_RE.fullmatch(nombre):
            return None
        return creado, datos["verify"] == "ok", _con_nombre(snapshot, nombre)
    except (UnicodeDecodeError, ValueError, KeyError, TypeError, RecursionError):
        return None


def _con_nombre(snapshot: object, juego: str) -> dict[str, Any] | None:
    """La entrada `openbao_snapshot` con el nombre del juego añadido en `_set`, o `None`."""
    if not isinstance(snapshot, dict):
        return None
    return {**snapshot, "_set": juego}


def _snapshot_en_disco(path: Path, entrada: dict[str, Any]) -> bool:
    """La entrada es válida de forma y el `.snap.age` junto a `path` es un archivo regular, sin
    enlaces, con el tamaño y el `sha256` declarados (S5-D177: un borrado o un cambio no pasan)."""
    nombre, tam, sha = entrada.get("name"), entrada.get("size_bytes"), entrada.get("sha256")
    if nombre != f"{entrada['_set']}-openbao.snap.age" or ".." in str(nombre):
        return False
    if type(tam) is not int or not 0 <= tam <= MAX_BACKUP_BYTES:
        return False
    if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
        return False
    archivo = path.with_name(nombre)
    try:
        if archivo.is_symlink() or not archivo.is_file() or archivo.stat().st_size != tam:
            return False
        return digest_file(archivo, max_bytes=tam) == sha
    except OSError:
        return False


def recent_signed_manifest(
    path: Path,
    pubkey: str,
    *,
    now: datetime,
    max_age: timedelta = MANIFEST_MAX_AGE,
    base: Path | None = None,
    require_openbao_snapshot: bool = False,
) -> ManifestCheck:
    """`path` (un `latest.json` con su `.minisig` al lado) con firma válida de `pubkey`, `verify`
    igual a `ok`, de menos de `max_age` y sin más de 5 min en el futuro. Con `base`, además debe
    quedar bajo esa carpeta. Con `require_openbao_snapshot`, exige `openbao_snapshot.verified` Y
    el `.snap.age` en disco junto a `path` con el tamaño y el `sha256` declarados (S5-D177).

    Orden: forma (enlaces, base, tamaño) -> firma -> contenido -> edad -> instantánea; la firma va
    antes de leer nada, así un manifiesto sin firma válida nunca se interpreta."""
    if not _placed_ok(path, base):
        return _fail("invalid")
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            return _fail("invalid")
        if not path.with_name(path.name + ".minisig").is_file():
            return _fail("no_signature")
    except OSError:
        return _fail("no_signature")
    crudo = verified_manifest_bytes(path, pubkey)  # una sola lectura: se parsean ESOS bytes
    if crudo is None:
        return _fail("bad_signature")
    campos = _read_fields(crudo)
    if campos is None:
        return _fail("invalid")
    creado, verificado, entrada = campos
    con_snapshot = entrada is not None and entrada.get("verified") is True
    if not verificado:
        return _fail("invalid", creado)
    if now - creado >= max_age or creado - now > CLOCK_SKEW:
        return _fail("stale", creado)
    if require_openbao_snapshot and not (
        con_snapshot and entrada is not None and _snapshot_en_disco(path, entrada)
    ):
        return ManifestCheck(False, "no_snapshot", creado, False)
    return ManifestCheck(True, "ok", creado, con_snapshot)


# Pruebas de custodia de B2 (S5-D186) -----------------------------------------------------------

NO_VERIFY: Final = "no hay un verify-kek-backup ok de una persona en las últimas 24 h"
NO_SNAPSHOT_MANIFEST: Final = (
    "no hay un latest.json reciente con firma e instantánea de OpenBao verificada en "
    "/data/backups (verify: ok)"
)


class CustodyRejected(Exception):
    """Falta una prueba de custodia; el mensaje es fijo y nunca trae texto del proveedor."""


async def custody_proofs(
    session: AsyncSession, settings: Settings, manifest: Path, *, now: datetime
) -> ManifestCheck:
    """H-1: un `verify-kek-backup` `ok` de una persona de menos de 24 h y, en este orden, un
    manifiesto firmado, reciente, con la instantánea de OpenBao verificada y presente en disco.
    Devuelve la revisión del manifiesto (el `--trim` usa su `created_at`)."""
    async with session.begin():
        verificado = await service.recent_kek_verify(session, within=service.KEK_VERIFY_WINDOW)
    if not verificado:
        raise CustodyRejected(NO_VERIFY)
    pubkey = settings.BACKUP_SIGN_PUBKEY
    if pubkey is None:
        raise CustodyRejected(NO_SNAPSHOT_MANIFEST)
    revision = recent_signed_manifest(
        manifest, pubkey, now=now, base=settings.BACKUP_DIR, require_openbao_snapshot=True
    )
    if not revision.ok:
        raise CustodyRejected(NO_SNAPSHOT_MANIFEST)
    return revision


def confirmation_error(word: str, *, yes: bool) -> str | None:
    """Pide `word` por stdin salvo `--yes`; devuelve el rechazo o `None` (EOF cuenta como vacío)."""
    if yes:
        return None
    try:
        escrito = typer.prompt(f"Escriba {word} para continuar", default="", show_default=False)
    except typer.Abort:
        escrito = ""
    if escrito.strip() == word:
        return None
    return f"la confirmación debe ser exactamente {word}"


# Errores comunes de los comandos de custodia (S5-D189, D190) -----------------------------------

BASE_OCUPADA: Final = "la base está ocupada; repita el comando"
OTRA_OPERACION: Final = "hay otra operación de llaves en curso; repita el comando más tarde"
FALLO_REPETIR: Final = "falló una llave; repita el comando para reanudar"


@contextmanager
def custody_errors(command: str) -> Iterator[None]:
    """Traduce a salida con mensaje fijo, sin traza: otra operación de llaves en curso (candado
    de la KEK o job abierto) sale 2; una base ocupada (`lock_timeout`, `statement_timeout`,
    interbloqueo) sale 1 como `rotate-key`."""
    try:
        yield
    except (RotationInProgress, MigrationInProgress):
        typer.echo(f"{command}: {OTRA_OPERACION}", err=True)
        raise typer.Exit(code=2) from None
    except DatabaseBusy:
        typer.echo(f"{command}: {BASE_OCUPADA}", err=True)
        raise typer.Exit(code=1) from None
    except DBAPIError as error:
        if translate_busy(error) is None:
            raise
        typer.echo(f"{command}: {BASE_OCUPADA}", err=True)
        raise typer.Exit(code=1) from None


def exit_after_failure(command: str, result: MigrationResult) -> NoReturn:
    """Un job que quedó `failed` (se reanuda repitiendo el comando): mensaje fijo y salida 1."""
    mensaje = BASE_OCUPADA if result.error == "busy" else FALLO_REPETIR
    typer.echo(f"{command}: {mensaje}", err=True)
    raise typer.Exit(code=1)

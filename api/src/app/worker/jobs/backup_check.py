"""Job diario `backup_check`: verifica el manifiesto del último respaldo (US-114, US-115).

S4B-B2 (S4B-D23 a D25, S4B-D59, S4B-D69 a D71, S4B-D80, S4B-D87, S4B-D97). Lee `latest.json` de
`Settings.BACKUP_DIR` (el volumen `backups`, solo lectura en el worker) como DATO NO CONFIABLE:
`parse_manifest` valida esquema, nombres y formas; `evaluate` (pura) decide uno de los seis
estados de `BackupStatus` con la prioridad `missing > corrupt > undecryptable > stale >
ok_unverified > ok`. El job no ejecuta `age`, no abre identidades y no verifica la firma del
manifiesto (la verifica `restore.sh`, S4B-D80); comprueba existencia, tamaño y `sha256` en reposo
de cada archivo (`digest_file` en `asyncio.to_thread`), la edad y el campo `verify`.

`run(ctx)` devuelve `JobResult(ok=status in {"ok", "ok_unverified"}, status=status,
details={archivos, edad_horas, tamano_bytes, verificado})`, todo entero (`DETAIL_KEYS`).
El log `backup_check finished` lleva el nombre del juego (fecha y hora UTC, sin datos
personales) y nunca la ruta, `upload_error` ni el `sha256` completo (S4B-D70). Si las últimas
7 corridas (incluida la actual) son `ok_unverified`, avisa `backup_unhealthy` (S4B-D87). El aviso
de los estados malos (`stale`, `missing`, `corrupt`, `undecryptable`) lo emite el runner.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Literal

from app.core.alerts import alert
from app.core.config import get_settings
from app.core.crypto.digest import digest_file
from app.core.jobs import last_results
from app.worker.runner import JobContext, JobResult

logger = logging.getLogger("app.worker.backup_check")

NAME: Final = "backup_check"

MAX_BACKUP_BYTES: Final = 50 * 1024**3
"""Tope de `size_bytes` por archivo (50 GiB, S4B-D69); más que eso es `corrupt`."""

MAX_FILES: Final = 8
"""Archivos por juego (un `db` y un `uploads` hoy); un manifiesto con más es `corrupt`."""

MAX_MANIFEST_BYTES: Final = 1 << 20
"""`latest.json` pesa unos cientos de bytes; más de 1 MiB no es un manifiesto."""

STALE_AFTER: Final = timedelta(hours=24)
FUTURE_TOLERANCE: Final = timedelta(minutes=5)
UNVERIFIED_STREAK: Final = 7
"""Corridas seguidas en `ok_unverified` (la actual incluida) que disparan el aviso (S4B-D87)."""

BackupStatus = Literal["ok", "ok_unverified", "stale", "missing", "corrupt", "undecryptable"]
"""Los seis estados; son los valores de `result` que escribe el runner."""

__all__ = [
    "MAX_BACKUP_BYTES",
    "MAX_FILES",
    "NAME",
    "BackupStatus",
    "Manifest",
    "ManifestFile",
    "evaluate",
    "get_settings",
    "parse_manifest",
    "run",
]

_NAME_RE: Final = re.compile(r"(apex|pre-deploy|pre-restore)-[0-9]{8}-[0-9]{6}")
_FILE_RE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")
_SHA_RE: Final = re.compile(r"[0-9a-f]{64}")
_STAMP_RE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_APEX_SET_RE: Final = re.compile(r"apex-[0-9]{8}-[0-9]{6}-db\.dump\.age")
_REQUIRED_KEYS: Final = frozenset(
    {"format_version", "name", "created_at", "database", "files", "verify", "upload"}
)
_ALLOWED_KEYS: Final = _REQUIRED_KEYS | {"verified_at", "upload_error"}
_FILE_KEYS: Final = frozenset({"kind", "name", "size_bytes", "sha256", "plain_sha256"})


@dataclass(frozen=True)
class ManifestFile:
    """Un archivo del juego: `kind` (`db` o `uploads`), nombre simple, tamaño y `sha256`."""

    kind: str
    name: str
    size_bytes: int
    sha256: str
    plain_sha256: str


@dataclass(frozen=True)
class Manifest:
    """Manifiesto validado de forma (`format_version` 1): lo que `parse_manifest` deja pasar."""

    name: str
    created_at: datetime
    database: str
    files: tuple[ManifestFile, ...]
    verify: str
    verified_at: datetime | None
    upload: str
    upload_error: str | None


def _instante(valor: object) -> datetime | None:
    """`AAAA-MM-DDTHH:MM:SSZ` en UTC o `None` (fechas imposibles incluidas)."""
    if not isinstance(valor, str) or not _STAMP_RE.fullmatch(valor):
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _archivo(crudo: object) -> ManifestFile | None:
    if not isinstance(crudo, dict) or set(crudo) != _FILE_KEYS:
        return None
    kind, name, size = crudo["kind"], crudo["name"], crudo["size_bytes"]
    if kind not in ("db", "uploads") or not isinstance(name, str) or ".." in name:
        return None
    if not _FILE_RE.fullmatch(name) or type(size) is not int or size < 0:
        return None
    huellas = (crudo["sha256"], crudo["plain_sha256"])
    if not all(isinstance(h, str) and _SHA_RE.fullmatch(h) for h in huellas):
        return None
    return ManifestFile(kind, name, size, huellas[0], huellas[1])


def _archivos(crudo: object) -> tuple[ManifestFile, ...] | None:
    if not isinstance(crudo, list) or not crudo:
        return None
    archivos = tuple(_archivo(item) for item in crudo)
    validos = tuple(a for a in archivos if a is not None)
    if len(validos) != len(archivos) or not any(a.kind == "db" for a in validos):
        return None
    return validos


def _cabecera_valida(datos: dict[str, Any]) -> bool:
    """Tipos y valores de los campos escalares del manifiesto."""
    nombre = datos["name"]
    base = type(datos["format_version"]) is int and datos["format_version"] == 1
    base = base and isinstance(nombre, str) and _NAME_RE.fullmatch(nombre) is not None
    base = base and _instante(datos["created_at"]) is not None
    base = base and isinstance(datos["database"], str) and 1 <= len(datos["database"]) <= 63
    base = base and datos["verify"] in ("ok", "failed", "skipped")
    base = base and datos["upload"] in ("ok", "skipped", "failed")
    verificado, error = datos.get("verified_at"), datos.get("upload_error")
    base = base and (verificado is None or _instante(verificado) is not None)
    return base and (error is None or (isinstance(error, str) and len(error) <= 200))


def parse_manifest(raw: bytes) -> Manifest | None:
    """El manifiesto o `None` si `raw` no cumple el esquema de `manifest.schema.json`.

    `None`: JSON inválido, `format_version` distinto de 1, `name` fuera de
    `(apex|pre-deploy|pre-restore)-AAAAMMDD-HHMMSS`, archivo con `/`, barra invertida, `..` o
    ruta absoluta,
    `sha256` mal formado, `files` sin `db`, campos extra. Acepta los tres prefijos (S4B-D97); que
    `latest.json` sea `apex-*` lo decide `run`.
    """
    try:
        datos = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(datos, dict) or not _REQUIRED_KEYS <= set(datos) <= _ALLOWED_KEYS:
        return None
    archivos = _archivos(datos["files"])
    creado = _instante(datos["created_at"])
    if archivos is None or creado is None or not _cabecera_valida(datos):
        return None
    return Manifest(
        name=datos["name"],
        created_at=creado,
        database=datos["database"],
        files=archivos,
        verify=datos["verify"],
        verified_at=_instante(datos.get("verified_at")),
        upload=datos["upload"],
        upload_error=datos.get("upload_error"),
    )


def evaluate(
    manifest: Manifest,
    now_utc: datetime,
    *,
    files_ok: bool | None,
    sizes_ok: bool | None,
) -> BackupStatus:
    """Estado del juego (pura). `files_ok`: todos los archivos existen (`False` -> `missing`);
    `sizes_ok`: tamaño y `sha256` en reposo coinciden con el manifiesto (`False` -> `corrupt`);
    `None`: no se comprobó y no pesa. Además: `created_at` a más de 5 min en el futuro, `name` que
    no coincide con `created_at` (UTC) o `size_bytes > MAX_BACKUP_BYTES` -> `corrupt`;
    `verify == "failed"` -> `undecryptable`; edad >= 24 h -> `stale`; `verify == "skipped"` ->
    `ok_unverified`; si no, `ok`."""
    if files_ok is False:
        return "missing"
    creado = manifest.created_at.astimezone(UTC)
    incoherente = (
        sizes_ok is False
        or creado - now_utc > FUTURE_TOLERANCE
        or not manifest.name.endswith(creado.strftime("-%Y%m%d-%H%M%S"))
        or any(f.size_bytes > MAX_BACKUP_BYTES for f in manifest.files)
    )
    if incoherente:
        return "corrupt"
    if manifest.verify == "failed":
        return "undecryptable"
    if now_utc - creado >= STALE_AFTER:
        return "stale"
    return "ok_unverified" if manifest.verify == "skipped" else "ok"


def _leer_manifiesto(carpeta: Path) -> bytes | None:
    """`latest.json` como bytes (sin seguir enlaces, con tope de tamaño) o `None`."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)  # un FIFO no debe colgar el hilo en el `open`
    try:
        descriptor = os.open(carpeta / "latest.json", flags)
        with os.fdopen(descriptor, "rb") as archivo:
            if not stat.S_ISREG(os.fstat(archivo.fileno()).st_mode):
                return None
            contenido = archivo.read(MAX_MANIFEST_BYTES + 1)
    except OSError:
        return None
    return contenido if len(contenido) <= MAX_MANIFEST_BYTES else None


def _contar_juegos(carpeta: Path) -> int:
    """Juegos `apex-*` presentes (un `-db.dump.age` por juego); los `pre-*` no cuentan."""
    try:
        return sum(1 for nombre in os.listdir(carpeta) if _APEX_SET_RE.fullmatch(nombre))
    except OSError:
        return 0


def _comprobar_archivo(carpeta: Path, archivo: ManifestFile) -> tuple[bool, bool]:
    """`(existe, coincide)`: tamaño y `sha256` en reposo; el archivo se lee por bloques."""
    ruta = carpeta / archivo.name
    try:
        info = os.lstat(ruta)
    except FileNotFoundError:
        return False, False
    except OSError:
        return True, False
    if not stat.S_ISREG(info.st_mode) or info.st_size != archivo.size_bytes:
        return True, False
    if archivo.size_bytes > MAX_BACKUP_BYTES:
        return True, False
    try:
        return True, digest_file(ruta, max_bytes=archivo.size_bytes) == archivo.sha256
    except OSError:
        return True, False


def _juego_coherente(manifest: Manifest) -> bool:
    """Como mucho `MAX_FILES` archivos, nombres únicos y todos con el prefijo del juego."""
    nombres = [f.name for f in manifest.files]
    return (
        len(nombres) <= MAX_FILES
        and len(set(nombres)) == len(nombres)
        and all(n.startswith(manifest.name) for n in nombres)
    )


async def _comprobar_archivos(carpeta: Path, manifest: Manifest) -> tuple[bool, bool]:
    """`(files_ok, sizes_ok)` de todos los archivos del juego, uno por hilo."""
    resultados = [
        await asyncio.to_thread(_comprobar_archivo, carpeta, archivo) for archivo in manifest.files
    ]
    return all(e for e, _ in resultados), all(c for e, c in resultados if e)


async def _racha_sin_verificar(ctx: JobContext) -> bool:
    """`True` si las últimas `UNVERIFIED_STREAK` corridas, la actual incluida, fueron
    `ok_unverified` (la actual aún figura `running`: el runner la cierra después)."""
    async with ctx.session_factory() as sesion:
        resultados = await last_results(sesion, NAME, limit=UNVERIFIED_STREAK)
    previas = resultados[1:] if resultados[:1] == ["running"] else resultados
    previas = previas[: UNVERIFIED_STREAK - 1]
    return len(previas) == UNVERIFIED_STREAK - 1 and all(r == "ok_unverified" for r in previas)


def _resultado(status: BackupStatus, detalles: dict[str, Any]) -> JobResult:
    return JobResult(ok=status in ("ok", "ok_unverified"), status=status, details=detalles)


def _informar(status: BackupStatus, nombre: str | None, detalles: dict[str, Any]) -> None:
    """Log sin ruta, sin `upload_error` y sin `sha256` (S4B-D70); el nombre lleva fecha y hora."""
    malo = status not in ("ok", "ok_unverified")
    logger.log(
        logging.WARNING if malo else logging.INFO,
        "backup_check finished",
        extra={"job": NAME, "result": status, "backup_name": nombre} | detalles,
    )


async def run(ctx: JobContext) -> JobResult:
    """Lee `latest.json`, comprueba los archivos y devuelve el estado (ver docstring del módulo)."""
    carpeta = Path(get_settings().BACKUP_DIR)
    juegos = await asyncio.to_thread(_contar_juegos, carpeta)
    crudo = await asyncio.to_thread(_leer_manifiesto, carpeta)
    manifest = None if crudo is None else parse_manifest(crudo)
    if manifest is None or not manifest.name.startswith("apex-"):
        detalles: dict[str, Any] = {"archivos": juegos}
        _informar("missing", None, detalles)
        return _resultado("missing", detalles)
    if _juego_coherente(manifest):
        files_ok, sizes_ok = await _comprobar_archivos(carpeta, manifest)
    else:  # no se toca el disco con nombres que el manifiesto no puede justificar
        files_ok, sizes_ok = None, False
    ahora = ctx.clock.now_utc()
    status = evaluate(manifest, ahora, files_ok=files_ok, sizes_ok=sizes_ok)
    detalles = {
        "archivos": juegos,
        "edad_horas": max(0, math.floor((ahora - manifest.created_at).total_seconds() / 3600)),
        "tamano_bytes": sum(f.size_bytes for f in manifest.files),
        "verificado": 1 if manifest.verify == "ok" else 0,
    }
    _informar(status, manifest.name, detalles)
    if status == "ok_unverified" and await _racha_sin_verificar(ctx):
        alert("backup_unhealthy", job=NAME, result=status)
    return _resultado(status, detalles)

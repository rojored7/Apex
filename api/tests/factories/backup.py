"""Fábrica de juegos de respaldo y de `latest.json` (plan del Sprint 4B, sección 2, bloque B2).

`make_backup_dir(carpeta, now, ...)` escribe en `carpeta` los dos archivos `.age` de un juego
(`<name>-db.dump.age` y `<name>-uploads.tar.age`, como `infra/backup/run.sh`; contenido aleatorio
pero determinista) y un `latest.json` válido (`format_version` 1,
`infra/backup/manifest.schema.json`)
con el `sha256` y el tamaño reales de esos archivos. `tamper` rompe una sola cosa:

- `sha256`: el `sha256` en reposo del archivo `db` del manifiesto no es el del archivo;
- `size`: `size_bytes` del archivo `db` no es el tamaño real;
- `name`: el `name` no coincide con `created_at`;
- `future`: `created_at` (y el nombre) a una hora del futuro respecto de `now`;
- `absolute`: el nombre del archivo `db` es una ruta absoluta;
- `dotdot`: el nombre del archivo `db` es `../...`;
- `missing_file`: borra el archivo `uploads` después de escribir el manifiesto.

`extra_sets` agrega juegos `apex-*` más viejos (sin tocar `latest.json`) y `pre_sets` juegos
`pre-deploy-*`, para los conteos de `archivos`. Los `sha256` se calculan con `sha256_hex` del bus
(`hashlib` está prohibido fuera de `core/crypto`).
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final

from app.core.crypto.digest import sha256_hex

TAMPERS: Final = ("sha256", "size", "name", "future", "absolute", "dotdot", "missing_file")
BASE_BYTES: Final = 96


@dataclass(frozen=True)
class BackupSet:
    """Lo que escribió `make_backup_dir`: carpeta, nombre del juego y datos del manifiesto."""

    folder: Path
    name: str
    created_at: datetime
    db_file: str
    uploads_file: str
    db_size: int
    uploads_size: int
    manifest: dict[str, Any]

    @property
    def latest(self) -> Path:
        return self.folder / "latest.json"

    @property
    def total_bytes(self) -> int:
        return self.db_size + self.uploads_size


def set_name(prefix: str, created_at: datetime) -> str:
    """`<prefix>-AAAAMMDD-HHMMSS` en UTC (el nombre que escribe `run.sh`)."""
    return f"{prefix}-{created_at.strftime('%Y%m%d-%H%M%S')}"


def iso_z(instant: datetime) -> str:
    return instant.strftime("%Y-%m-%dT%H:%M:%SZ")


def _contenido(semilla: str, tamano: int) -> bytes:
    return random.Random(semilla).randbytes(tamano)  # noqa: S311 - datos de prueba


def _escribir_archivo(carpeta: Path, nombre: str, semilla: str, tamano: int) -> dict[str, Any]:
    datos = _contenido(semilla, tamano)
    (carpeta / nombre).write_bytes(datos)
    return {
        "name": nombre,
        "size_bytes": len(datos),
        "sha256": sha256_hex(datos),
        "plain_sha256": sha256_hex(b"claro:" + datos),
    }


def write_set(carpeta: Path, nombre: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Escribe los dos `.age` de `nombre`; devuelve sus entradas de manifiesto (sin `kind`)."""
    db = _escribir_archivo(carpeta, f"{nombre}-db.dump.age", f"{nombre}-db", BASE_BYTES + 40)
    up = _escribir_archivo(carpeta, f"{nombre}-uploads.tar.age", f"{nombre}-up", BASE_BYTES)
    return db, up


def manifest_dict(
    name: str,
    created_at: datetime,
    db: dict[str, Any],
    up: dict[str, Any] | None,
    *,
    verify: str = "ok",
    upload: str = "ok",
    upload_error: str | None = None,
) -> dict[str, Any]:
    """Un manifiesto válido (`format_version` 1) con los archivos dados."""
    archivos = [{"kind": "db", **db}]
    if up is not None:
        archivos.append({"kind": "uploads", **up})
    datos: dict[str, Any] = {
        "format_version": 1,
        "name": name,
        "created_at": iso_z(created_at),
        "database": "apex",
        "files": archivos,
        "verify": verify,
        "verified_at": iso_z(created_at + timedelta(minutes=2)) if verify != "skipped" else None,
        "upload": upload,
    }
    if upload_error is not None:
        datos["upload_error"] = upload_error
    return datos


def manifest_bytes(datos: dict[str, Any]) -> bytes:
    return json.dumps(datos, indent=2, sort_keys=True).encode("utf-8")


def _aplicar_tamper(datos: dict[str, Any], tamper: str) -> None:
    db = datos["files"][0]
    if tamper == "sha256":
        db["sha256"] = ("0" if db["sha256"][0] != "0" else "1") + db["sha256"][1:]
    elif tamper == "size":
        db["size_bytes"] += 1
    elif tamper == "name":
        datos["name"] = "apex-20200101-000000"
    elif tamper == "absolute":
        db["name"] = "/etc/passwd"
    elif tamper == "dotdot":
        db["name"] = "../fuera-db.dump.age"


def make_backup_dir(
    carpeta: Path,
    now: datetime,
    *,
    verify: str = "ok",
    tamper: str | None = None,
    prefix: str = "apex",
    created_at: datetime | None = None,
    extra_sets: int = 0,
    pre_sets: int = 0,
    upload: str = "ok",
    upload_error: str | None = None,
) -> BackupSet:
    """Escribe el juego, `latest.json` y los juegos extra; `created_at` por defecto `now - 5 h`."""
    if tamper is not None and tamper not in TAMPERS:
        raise ValueError(f"tamper desconocido: {tamper}")
    carpeta.mkdir(parents=True, exist_ok=True)
    creado = created_at or now - timedelta(hours=5)
    if tamper == "future":
        creado = now + timedelta(hours=1)
    nombre = set_name(prefix, creado)
    db, up = write_set(carpeta, nombre)
    datos = manifest_dict(
        nombre, creado, db, up, verify=verify, upload=upload, upload_error=upload_error
    )
    if tamper is not None:
        _aplicar_tamper(datos, tamper)
    (carpeta / "latest.json").write_bytes(manifest_bytes(datos))
    if tamper == "missing_file":
        (carpeta / up["name"]).unlink()
    for i in range(extra_sets):
        write_set(carpeta, set_name("apex", creado - timedelta(days=i + 1)))
    for i in range(pre_sets):
        write_set(carpeta, set_name("pre-deploy", creado - timedelta(hours=i + 1)))
    return BackupSet(
        folder=carpeta,
        name=nombre,
        created_at=creado,
        db_file=db["name"],
        uploads_file=up["name"],
        db_size=db["size_bytes"],
        uploads_size=up["size_bytes"],
        manifest=datos,
    )

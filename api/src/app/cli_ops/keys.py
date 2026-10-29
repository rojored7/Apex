"""Archivos de llaves de `init-keys` (US-023): KEK, llave de firma y par JWT (modo 600).

Extraído de `cli.py` en B0 (S4B-D28) sin cambios de comportamiento. Solo importa `cli_base`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import typer

from app.core.config import Settings


@dataclass(frozen=True)
class KeyPaths:
    kek: Path
    signing_key: Path
    jwt_private: Path
    jwt_public: Path


KEK_LEN = 32
SEED_LEN = 32


def key_paths_in(directory: Path) -> KeyPaths:
    """Rutas estándar dentro de un directorio (el volumen `keys` en Compose)."""
    return KeyPaths(
        kek=directory / "kek.bin",
        signing_key=directory / "sign-ed25519.key",
        jwt_private=directory / "jwt_ed25519.pem",
        jwt_public=directory / "jwt_ed25519.pub",
    )


def key_paths_from_settings(settings: Settings) -> KeyPaths:
    if settings.CRYPTO_LOCAL_KEK_PATH is None:
        raise typer.BadParameter("CRYPTO_LOCAL_KEK_PATH no está definida")
    publica = settings.JWT_PUBLIC_KEY_PATH or settings.JWT_PRIVATE_KEY_PATH.with_suffix(".pub")
    return KeyPaths(
        kek=settings.CRYPTO_LOCAL_KEK_PATH,
        signing_key=settings.CRYPTO_LOCAL_SIGNING_KEY_PATH,
        jwt_private=settings.JWT_PRIVATE_KEY_PATH,
        jwt_public=publica,
    )


def _write_new_private_file(path: Path, data: bytes) -> bool:
    """Crea el archivo con modo 600 solo si no existe (`O_EXCL`). Devuelve si lo creó."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "wb") as archivo:
        archivo.write(data)
    return True


def _jwt_pem_pair() -> tuple[bytes, bytes]:
    from app.core.security import generate_jwt_keypair_pem  # solo core/security toca JWT

    return generate_jwt_keypair_pem()


def init_keys_files(paths: KeyPaths) -> dict[str, str]:
    """Crea lo que falte; nunca sobrescribe. Devuelve `{nombre: "creada" | "ya existe"}`."""
    estado: dict[str, str] = {}
    estado["KEK"] = (
        "creada" if _write_new_private_file(paths.kek, os.urandom(KEK_LEN)) else "ya existe"
    )
    estado["llave de firma"] = (
        "creada"
        if _write_new_private_file(paths.signing_key, os.urandom(SEED_LEN))
        else "ya existe"
    )
    if paths.jwt_private.exists() and paths.jwt_public.exists():
        estado["par JWT"] = "ya existe"
    elif paths.jwt_private.exists():
        from app.core.security import public_pem_from_private_pem

        publica = public_pem_from_private_pem(paths.jwt_private.read_bytes())
        _write_new_private_file(paths.jwt_public, publica)
        estado["par JWT"] = "creada (solo la pública, desde la privada existente)"
    else:
        privada, publica = _jwt_pem_pair()
        if paths.jwt_public.exists():
            paths.jwt_public.unlink()  # pública huérfana: se regenera con la privada nueva
        _write_new_private_file(paths.jwt_private, privada)
        _write_new_private_file(paths.jwt_public, publica)
        estado["par JWT"] = "creada"
    return estado

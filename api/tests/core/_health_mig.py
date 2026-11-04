"""Fixture `apex_health_mig` (S4B-B4, S4B-D60): base propia para probar `migrations` de `/health`.

Crea `apex_health_mig` con `asyncpg` en autocommit (conectado a la base `postgres` del mismo
servidor de `TEST_DATABASE_URL`), la migra a `head` con `command.upgrade` y al terminar la borra
(`DROP DATABASE ... WITH (FORCE)`). Nunca toca `db_test`: las pruebas bajan de versión y cambian
`alembic_version`, cosa que no se puede hacer sobre la base compartida.

`HealthMig` ofrece `settings` (apuntan a esa base), `head`, `anterior` y las operaciones de
Alembic como corrutinas (`downgrade`, `set_revision`), que corren en un hilo porque `env.py` usa
`asyncio.run`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import asyncpg
import pytest
from alembic import command
from alembic.script import ScriptDirectory

from app.cli import key_paths_in
from app.core.config import Settings, load_settings
from tests.conftest import alembic_config_for

BASE_HEALTH_MIG = "apex_health_mig"


def _sql_en_postgres(url_admin: str, *sentencias: str) -> None:
    """Sentencias sin transacción (CREATE/DROP DATABASE) por `asyncpg` en autocommit."""

    async def correr() -> None:
        conexion = await asyncpg.connect(url_admin)
        try:
            for sentencia in sentencias:
                await conexion.execute(sentencia)
        finally:
            await conexion.close()

    asyncio.run(correr())


@dataclass(frozen=True)
class HealthMig:
    """La base `apex_health_mig` ya migrada a `head`."""

    url: str  # postgresql+asyncpg://...
    dsn: str  # postgresql://... (asyncpg directo)
    settings: Settings
    head: str
    anterior: str  # la revisión que sigue justo antes de head

    async def downgrade(self, destino: str = "-1") -> None:
        cfg = alembic_config_for(self.url)
        await asyncio.to_thread(command.downgrade, cfg, destino)

    async def upgrade(self, destino: str = "head") -> None:
        cfg = alembic_config_for(self.url)
        await asyncio.to_thread(command.upgrade, cfg, destino)

    async def revision_actual(self) -> str:
        conexion = await asyncpg.connect(self.dsn)
        try:
            return str(await conexion.fetchval("SELECT version_num FROM public.alembic_version"))
        finally:
            await conexion.close()

    async def set_revision(self, revision: str) -> None:
        conexion = await asyncpg.connect(self.dsn)
        try:
            await conexion.execute("UPDATE public.alembic_version SET version_num = $1", revision)
        finally:
            await conexion.close()


@pytest.fixture
def apex_health_mig(
    test_database_url: str, claves_prueba: Path, tmp_path: Path
) -> Iterator[HealthMig]:
    partes = urlsplit(test_database_url)
    assert partes.hostname and partes.port and partes.username and partes.password
    credenciales = f"{partes.username}:{partes.password}@{partes.hostname}:{partes.port}"
    admin = f"postgresql://{credenciales}/postgres"
    dsn = f"postgresql://{credenciales}/{BASE_HEALTH_MIG}"
    url = f"postgresql+asyncpg://{credenciales}/{BASE_HEALTH_MIG}"

    _sql_en_postgres(admin, f"DROP DATABASE IF EXISTS {BASE_HEALTH_MIG} WITH (FORCE)")
    _sql_en_postgres(admin, f"CREATE DATABASE {BASE_HEALTH_MIG}")
    try:
        cfg = alembic_config_for(url)
        command.upgrade(cfg, "head")
        script = ScriptDirectory.from_config(cfg)
        head = script.get_current_head()
        assert head is not None
        revision = script.get_revision(head)
        assert revision is not None and isinstance(revision.down_revision, str)

        rutas = key_paths_in(claves_prueba)
        env = tmp_path / "health_mig.env"
        env.write_text(
            f"DATABASE_URL={url}\n"
            f"JWT_PRIVATE_KEY_PATH={rutas.jwt_private}\n"
            "CRYPTO_PROVIDER=local\n"
            f"CRYPTO_LOCAL_KEK_PATH={rutas.kek}\n"
            f"CRYPTO_LOCAL_SIGNING_KEY_PATH={rutas.signing_key}\n"
            "UPLOADS_DIR=/data/uploads\n"
            'CORS_ORIGINS=["http://localhost"]\n'
            "LOG_LEVEL=INFO\nENV=dev\nMIGRATE_ON_STARTUP=false\n",
            encoding="utf-8",
        )
        yield HealthMig(
            url=url,
            dsn=dsn,
            settings=load_settings(env_file=env),
            head=head,
            anterior=revision.down_revision,
        )
    finally:
        _sql_en_postgres(admin, f"DROP DATABASE IF EXISTS {BASE_HEALTH_MIG} WITH (FORCE)")

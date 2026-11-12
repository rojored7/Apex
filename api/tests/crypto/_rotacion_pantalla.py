"""Apoyo de la rotación desde la pantalla (S6-R1, US-145; S6-D43, S6-D61). Rojo R1.

- `motor_dedicado_contado`: sustituye `rotate_job.rotation_engine` por un motor de prueba
  (`pool_size=1`, `max_overflow=0`) y cuenta cuántas veces se pidió. Contrato asumido: la
  rotación pide el motor dedicado llamando `rotation_engine(...)` POR ATRIBUTO DE MÓDULO.
- `PuertaDeLotes`: envuelve `service.reencrypt_batch` (la rotación lo llama por atributo de
  módulo, como el CLI). ANTES de cada lote avisa por `llegadas` y espera un permiso: lo ya
  confirmado es lo que ve el resto del mundo mientras la rotación espera.
- `pantalla`: la app real (`create_app`, sin lifespan) con commit real (`get_session` real sobre el
  motor de la prueba), un admin real y la tabla de prueba de `rotacion_lista`; el `POST` lanza la
  tarea en `app.state.rotation_task` y `terminar()` la espera. Al salir limpia usuarios y la cola
  de la cadena de auditoría.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core import db
from app.core.audit import AuditEntry
from app.core.config import Settings
from app.core.crypto import rotate_job, service
from app.core.crypto.keyring import configure_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoJob, CryptoKey
from app.core.crypto.provider import configure_provider
from app.core.security import register_principal_loader
from tests.conftest import (
    CLAVE_PRUEBA,
    Cabeceras,
    UsuarioPrueba,
    limpiar_tras_dos_sesiones,
)
from tests.crypto._rotacion import Fabrica
from tests.factories.users import make_user

ROTATE_URL = "/api/v1/crypto/keys/{key_id}/rotate"
JOBS_URL = "/api/v1/crypto/jobs"
MOTIVO = "sospecha"
ESPERA_S = 60.0


# Motor dedicado ---


@dataclass
class MotorDedicado:
    engine: AsyncEngine
    pedidos: int = 0


@pytest.fixture
async def motor_dedicado_contado(
    migrated_database: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[MotorDedicado]:
    motor = create_async_engine(
        migrated_database, pool_size=1, max_overflow=0, hide_parameters=True
    )
    contado = MotorDedicado(motor)

    def falso(*_args: object, **_kwargs: object) -> AsyncEngine:
        contado.pedidos += 1
        return motor

    monkeypatch.setattr(rotate_job, "rotation_engine", falso)
    try:
        yield contado
    finally:
        await motor.dispose()


# Puerta de lotes ---


@dataclass
class PuertaDeLotes:
    """Espera ANTES de cada `service.reencrypt_batch`. `llegadas` recibe el número de lote que
    está por correr; `permisos.release()` lo deja pasar; `abrir()` deja pasar todos los demás."""

    real: Any
    llegadas: asyncio.Queue[int] = field(default_factory=asyncio.Queue)
    permisos: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(0))
    contador: int = 0
    libre: bool = False
    antes_de_cada_lote: Any = None

    async def __call__(self, session: Any, job: Any, batch_size: int = 500) -> int:
        self.contador += 1
        if self.antes_de_cada_lote is not None:
            await self.antes_de_cada_lote(self.contador)
        if not self.libre:
            self.llegadas.put_nowait(self.contador)
            await self.permisos.acquire()
        return int(await self.real(session, job, batch_size))

    async def llega(self) -> int:
        return await asyncio.wait_for(self.llegadas.get(), ESPERA_S)

    def pasa(self, lotes: int = 1) -> None:
        for _ in range(lotes):
            self.permisos.release()

    def abrir(self) -> None:
        self.libre = True
        self.pasa(1000)


@pytest.fixture
def puerta(monkeypatch: pytest.MonkeyPatch) -> PuertaDeLotes:
    """Instala la puerta sobre `service.reencrypt_batch` (la prueba decide si la usa)."""
    puerta = PuertaDeLotes(service.reencrypt_batch)
    monkeypatch.setattr(service, "reencrypt_batch", puerta)
    return puerta


# La app con commit real ---


@dataclass
class Pantalla:
    app: FastAPI
    http: AsyncClient
    fabrica: Fabrica
    admin: UsuarioPrueba
    cabeceras: Cabeceras
    engine: AsyncEngine

    def _h(self, usuario: UsuarioPrueba | None = None) -> dict[str, str]:
        return self.cabeceras(usuario or self.admin)

    async def rotar(
        self,
        key_id: UUID | str,
        *,
        reason: str = MOTIVO,
        confirm: str = "ROTAR",
        usuario: UsuarioPrueba | None = None,
        cuerpo: dict[str, Any] | None = None,
    ) -> Response:
        return await self.http.post(
            ROTATE_URL.format(key_id=key_id),
            json=cuerpo if cuerpo is not None else {"reason": reason, "confirm": confirm},
            headers=self._h(usuario),
        )

    async def jobs(self, **params: object) -> list[dict[str, Any]]:
        r = await self.http.get(JOBS_URL, params=params, headers=self._h())
        assert r.status_code == 200, r.text
        return list(r.json()["items"])

    async def terminar(self) -> None:
        """Espera la tarea de rotación lanzada por el `POST` (o por `resume_running_jobs`)."""
        tarea: asyncio.Task[Any] | None = getattr(self.app.state, "rotation_task", None)
        assert tarea is not None, "el POST no dejó la tarea en app.state.rotation_task"
        await asyncio.wait({tarea}, timeout=ESPERA_S)
        assert tarea.done(), "la rotación no terminó"

    async def job(self, job_id: UUID | str) -> CryptoJob:
        async with self.fabrica() as sesion:
            job = await sesion.get(CryptoJob, UUID(str(job_id)))
            assert job is not None
            return job

    async def llaves(self, clase: str = "member.document") -> list[CryptoKey]:
        async with self.fabrica() as sesion:
            filas = await sesion.scalars(
                select(CryptoKey)
                .where(CryptoKey.data_class == clase, CryptoKey.purpose == "encrypt")
                .order_by(CryptoKey.version)
            )
            return list(filas)

    async def filas_de_auditoria(self, tabla: str = "crypto.crypto_keys") -> list[dict[str, Any]]:
        async with self.fabrica() as sesion:
            filas = await sesion.execute(
                text(
                    "SELECT seq, action, record_id, before, after, user_id FROM audit.audit_log "
                    "WHERE table_name = :t ORDER BY seq"
                ),
                {"t": tabla},
            )
            return [dict(f) for f in filas.mappings().all()]


@pytest.fixture
async def pantalla(
    rotacion_lista: Fabrica,
    engine: AsyncEngine,
    seguridad: Settings,
    cargador_real: Any,
    reloj: Any,
    cabeceras: Cabeceras,
    proveedor_local: LocalFileProvider,
    motor_dedicado_contado: MotorDedicado,
) -> AsyncIterator[Pantalla]:
    from app.main import create_app

    async with engine.connect() as conexion:
        ultima = int(await conexion.scalar(select(func.coalesce(func.max(AuditEntry.seq), 0))) or 0)
    app = create_app(seguridad, run_migrations_on_startup=False)
    register_principal_loader(cargador_real)
    configure_provider(proveedor_local)
    db.configure_engine(engine)  # `create_app` fijó el motor de `Settings`: manda el de la prueba
    async with rotacion_lista() as sesion:
        admin_orm = await make_user(sesion, role="admin", password=CLAVE_PRUEBA)
        from app.core.security import create_access_token

        token = create_access_token(admin_orm.id, "admin", None, reloj)
        admin = UsuarioPrueba(admin_orm, admin_orm.id, admin_orm.email, "admin", "", token)
    cliente = AsyncClient(transport=ASGITransport(app=app), base_url="http://t")
    try:
        yield Pantalla(app, cliente, rotacion_lista, admin, cabeceras, engine)
    finally:
        tarea: asyncio.Task[Any] | None = getattr(app.state, "rotation_task", None)
        if tarea is not None and not tarea.done():
            tarea.cancel()
            await asyncio.wait({tarea}, timeout=10)
        await cliente.aclose()
        configure_provider(None)
        configure_keyring(None)
        await limpiar_tras_dos_sesiones(engine, ultima)

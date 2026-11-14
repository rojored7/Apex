"""Ayudas comunes de las pruebas de `attachments` (S6-C1)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.context import actor_scope
from app.modules.attachments import service
from app.modules.attachments.models import Attachment
from tests.factories.files import en_trozos


async def subir(
    session: AsyncSession,
    por: UUID,
    kind: str,
    data: bytes,
    *,
    dueno: UUID | None = None,
    tam: int = 65536,
) -> Attachment:
    """`service.store` bajo el actor `por`, con el cuerpo en trozos de `tam`."""
    with actor_scope(por):
        adjunto = await service.store(
            session,
            owner_table="members",
            owner_id=dueno or uuid4(),
            kind=kind,
            chunks=en_trozos(data, tam),
            by=por,
        )
        await session.flush()
    return adjunto


async def fila(session: AsyncSession, adjunto_id: UUID) -> dict[str, Any]:
    """La fila cruda de la tabla (con `filename_random` y `key_id`)."""
    resultado = await session.execute(
        text("SELECT * FROM attachments.attachments WHERE id = :id"), {"id": adjunto_id}
    )
    return dict(resultado.mappings().one())


async def filas_de_auditoria(session: AsyncSession, accion: str) -> list[dict[str, Any]]:
    resultado = await session.execute(
        text(
            "SELECT * FROM audit.audit_log WHERE action = :a "
            "AND table_name = 'attachments.attachments' ORDER BY seq"
        ),
        {"a": accion},
    )
    return [dict(f) for f in resultado.mappings().all()]


async def ops_de(session: AsyncSession, verbo: str, record_id: UUID) -> list[dict[str, Any]]:
    resultado = await session.execute(
        text(
            "SELECT * FROM crypto.crypto_ops WHERE data_class = 'attachment.sensitive' "
            "AND verb = :v AND record_id = :r ORDER BY at"
        ),
        {"v": verbo, "r": record_id},
    )
    return [dict(f) for f in resultado.mappings().all()]


async def subir_real(
    fabrica: async_sessionmaker[AsyncSession],
    por: UUID,
    kind: str,
    data: bytes,
    *,
    dueno: UUID | None = None,
) -> Attachment:
    """`service.store` con commit real en su propia sesión (las filas de `crypto_ops` y de
    auditoría salen en el commit)."""
    with actor_scope(por):
        async with fabrica() as sesion, sesion.begin():
            return await service.store(
                sesion,
                owner_table="members",
                owner_id=dueno or uuid4(),
                kind=kind,
                chunks=en_trozos(data),
                by=por,
            )


async def llave_retirada(session: AsyncSession) -> UUID:
    """Una llave `retired` propia de la fila (la FK `fk_attachments_key_id` de `0025` la exige)."""
    llave = uuid4()
    await session.execute(
        text(
            "INSERT INTO crypto.crypto_keys (id, created_by, purpose, data_class, algorithm, "
            "provider, version, state, wrapped_material) VALUES (:id, :por, 'encrypt', "
            "'prueba.adjunto', 'A256GCM', 'local', :version, 'retired', :material)"
        ),
        {
            "id": llave,
            "por": uuid4(),
            "material": bytes([1]),
            "version": int(llave.int % 2_000_000_000) + 1,
        },
    )
    return llave


async def insertar(
    session: AsyncSession,
    *,
    owner: UUID,
    kind: str = "photo",
    created_at: datetime | None = None,
    id_: UUID | None = None,
    por: UUID | None = None,
    nombre: str | None = None,
) -> UUID:
    """Una fila cruda válida (CHECKs de D25) con `created_at` e `id` a gusto de la prueba."""
    identificador = id_ or uuid4()
    sensible = kind != "photo"
    llave = await llave_retirada(session) if sensible else None
    await session.execute(
        text(
            "INSERT INTO attachments.attachments (id, owner_table, owner_id, kind, "
            "filename_random, mime, size_bytes, sensitive, key_id, storage_provider, "
            "uploaded_by, created_at, updated_at, created_by) VALUES (:id, 'members', :owner, "
            ":kind, :nombre, :mime, 100, :sensible, :llave, 'local', :por, "
            "COALESCE(CAST(:creada AS timestamptz), now()), "
            "COALESCE(CAST(:creada AS timestamptz), now()), :por)"
        ),
        {
            "id": identificador,
            "owner": owner,
            "kind": kind,
            "nombre": nombre or uuid4().hex,
            "mime": "application/pdf" if sensible else "image/jpeg",
            "sensible": sensible,
            "llave": llave,
            "por": por or uuid4(),
            "creada": created_at,
        },
    )
    return identificador


# ASGI en bruto (S6-C4) ---------------------------------------------------------------------------


@dataclass
class Capturada:
    """Lo que el api mandó por `send`, mensaje a mensaje."""

    mensajes: list[dict[str, Any]]

    @property
    def status(self) -> int:
        return int(self.mensajes[0]["status"])

    @property
    def cabeceras(self) -> dict[str, str]:
        return {k.decode().lower(): v.decode() for k, v in self.mensajes[0]["headers"]}

    @property
    def cuerpo(self) -> bytes:
        return b"".join(m.get("body", b"") for m in self.mensajes[1:])


async def pedir_asgi(
    app: Any,
    ruta: str,
    cabeceras: dict[str, str],
    *,
    en_primer_mensaje: Callable[[], Awaitable[None]] | None = None,
    cortar_tras_cabeceras: bool = False,
    tiempo_max_s: float = 20.0,
) -> Capturada:
    """`GET ruta` directo a la app, sin `httpx` (que espera el cuerpo entero antes de devolver).

    `en_primer_mensaje` corre DENTRO del primer `send` (cuando el api empieza a responder: es el
    momento de comprobar lo que debía estar confirmado antes del primer byte). Con
    `cortar_tras_cabeceras` el cliente «se va» al recibir las cabeceras: `receive` entrega
    `http.disconnect` y los trozos del cuerpo se descartan. Una excepción del api sale tal cual.
    """
    mensajes: list[dict[str, Any]] = []
    entregada = False
    cabeceras_vistas = asyncio.Event()
    nunca = asyncio.Event()

    async def receive() -> dict[str, Any]:
        nonlocal entregada
        if not entregada:
            entregada = True
            return {"type": "http.request", "body": b"", "more_body": False}
        if cortar_tras_cabeceras:
            await cabeceras_vistas.wait()
        else:
            await nunca.wait()  # lo cancela quien termine de responder
        return {"type": "http.disconnect"}

    async def send(mensaje: dict[str, Any]) -> None:
        if mensaje["type"] == "http.response.body" and cabeceras_vistas.is_set():
            if cortar_tras_cabeceras:
                return
        mensajes.append(mensaje)
        if len(mensajes) == 1 and en_primer_mensaje is not None:
            await en_primer_mensaje()
        if mensaje["type"] == "http.response.start":
            cabeceras_vistas.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": ruta,
        "raw_path": ruta.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"t")]
        + [(k.lower().encode(), v.encode()) for k, v in cabeceras.items()],
        "client": ("127.0.0.1", 40000),
        "server": ("t", 80),
        "state": {},
    }
    await asyncio.wait_for(app(scope, receive, send), tiempo_max_s)
    return Capturada(mensajes)

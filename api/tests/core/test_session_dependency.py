"""`get_session`: una transacción por petición; un error revierte y el commit ocurre
antes de responder (US-012, T6 y T11)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import (
    Base,
    CommonColumnsMixin,
    SessionDep,
    configure_sessionmaker,
    get_session,
)
from app.core.errors import register_error_handlers


class FilaDePeticion(CommonColumnsMixin, Base):
    __tablename__ = "filas_de_peticion"
    __table_args__ = {"schema": "worker"}  # noqa: RUF012

    nota: Mapped[str] = mapped_column()


@pytest.fixture
async def tabla(engine: AsyncEngine) -> AsyncIterator[None]:
    async with engine.begin() as conexion:
        await conexion.run_sync(
            lambda c: Base.metadata.create_all(c, tables=[FilaDePeticion.__table__])
        )
    configure_sessionmaker(async_sessionmaker(engine, expire_on_commit=False))
    try:
        yield
    finally:
        configure_sessionmaker(None)
        async with engine.begin() as conexion:
            await conexion.run_sync(
                lambda c: Base.metadata.drop_all(c, tables=[FilaDePeticion.__table__])
            )


def _app() -> FastAPI:
    app = FastAPI()

    @app.post("/falla")
    async def falla(session: AsyncSession = Depends(get_session)) -> dict[str, str]:  # noqa: B008
        session.add(FilaDePeticion(nota="no debe quedar", created_by=uuid4()))
        await session.flush()
        raise RuntimeError("falla simulada después de insertar")

    @app.post("/ok")
    async def ok(session: AsyncSession = Depends(get_session)) -> dict[str, str]:  # noqa: B008
        session.add(FilaDePeticion(nota="sí queda", created_by=uuid4()))
        return {"estado": "ok"}

    return app


async def _contar(engine: AsyncEngine) -> int:
    async with engine.connect() as conexion:
        total = await conexion.scalar(select(func.count()).select_from(FilaDePeticion.__table__))
    return int(total or 0)


async def test_una_excepcion_revierte_la_fila(engine: AsyncEngine, tabla: None) -> None:
    transporte = ASGITransport(app=_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://pruebas") as cliente:
        respuesta = await cliente.post("/falla")
    assert respuesta.status_code == 500
    assert await _contar(engine) == 0


async def test_el_commit_ocurre_al_responder(engine: AsyncEngine, tabla: None) -> None:
    transporte = ASGITransport(app=_app())
    async with AsyncClient(transport=transporte, base_url="http://pruebas") as cliente:
        respuesta = await cliente.post("/ok")
    assert respuesta.status_code == 200
    assert await _contar(engine) == 1


# N-1 (revisión de seguridad V10): el commit corre ANTES de enviar el cuerpo ----------------


async def _orden_de_commit_y_respuesta(app: FastAPI) -> list[str]:
    """Llama la app por ASGI con un `send` espía y registra cuándo confirma la sesión frente al
    `http.response.body` (httpx.ASGITransport espera toda la app y no lo distingue)."""
    from sqlalchemy import event
    from sqlalchemy.orm import Session as SyncSession

    orden: list[str] = []

    def _al_confirmar(_sesion: SyncSession) -> None:
        orden.append("commit")

    event.listen(SyncSession, "after_commit", _al_confirmar)
    alcance = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/escribe",
        "raw_path": b"/escribe",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 1),
        "server": ("pruebas", 80),
    }

    async def recibir() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def enviar(mensaje: dict[str, object]) -> None:
        if mensaje["type"] == "http.response.body":
            orden.append("response-body")

    try:
        await app(alcance, recibir, enviar)
    finally:
        event.remove(SyncSession, "after_commit", _al_confirmar)
    return orden


async def test_session_dep_confirma_antes_de_enviar_el_cuerpo(
    engine: AsyncEngine, tabla: None
) -> None:
    app = FastAPI()

    @app.post("/escribe")
    async def escribe(session: SessionDep) -> dict[str, str]:
        session.add(FilaDePeticion(nota="antes de responder", created_by=uuid4()))
        return {"estado": "ok"}

    assert await _orden_de_commit_y_respuesta(app) == ["commit", "response-body"]
    assert await _contar(engine) == 1


async def test_un_error_de_commit_llega_al_cliente_como_envelope(
    engine: AsyncEngine, tabla: None
) -> None:
    """US-017: con el commit antes de responder, un fallo al confirmar es un 500 del envelope
    (antes salía un 200 de una escritura revertida)."""
    from sqlalchemy import event
    from sqlalchemy.orm import Session as SyncSession

    app = FastAPI()
    register_error_handlers(app)

    @app.post("/escribe")
    async def escribe(session: SessionDep) -> dict[str, str]:
        session.add(FilaDePeticion(nota="no debe quedar", created_by=uuid4()))
        return {"estado": "ok"}

    def _falla_al_confirmar(_sesion: SyncSession) -> None:
        raise RuntimeError("fallo simulado en before_commit")

    event.listen(SyncSession, "before_commit", _falla_al_confirmar)
    try:
        transporte = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transporte, base_url="http://pruebas") as cliente:
            respuesta = await cliente.post("/escribe")
    finally:
        event.remove(SyncSession, "before_commit", _falla_al_confirmar)
    assert respuesta.status_code == 500
    assert respuesta.json()["error"]["code"] == "internal_error"
    assert await _contar(engine) == 0

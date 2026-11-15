"""`record_result` no descifra nada en ejecución (S8-B1d, L-6): ni `reveal` ni `crypto_ops`."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import oplog, types
from tests.results._apoyo import escena, registrar

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")


async def test_registrar_y_corregir_no_descifra_ni_deja_filas_en_crypto_ops(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    def prohibido(*_a: Any, **_k: Any) -> None:
        raise AssertionError("results no debe descifrar")

    monkeypatch.setattr(types, "reveal", prohibido)
    e = await escena(session)  # crea el socio: eso sí cifra y deja sus filas
    oplog.reset_buffer()
    antes = await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops"))
    uno = await registrar(session, e, seconds=300)
    await registrar(session, e, seconds=280, supersedes_id=uno.id)
    despues = await session.scalar(text("SELECT count(*) FROM crypto.crypto_ops"))
    assert despues == antes
    assert oplog._buffer_list() == []

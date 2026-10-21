"""Un error de SQL en el log nunca muestra los parámetros (US-018, T6; US-012 criterio 5)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import load_settings
from app.core.logging import configure_logging


def _settings_debug(tmp_path: Path) -> object:
    env = tmp_path / ".env"
    env.write_text(
        "DATABASE_URL=postgresql+asyncpg://apex:x@db:5432/apex\n"
        "JWT_PRIVATE_KEY_PATH=/k.pem\nCRYPTO_PROVIDER=local\nCRYPTO_LOCAL_KEK_PATH=/kek\n"
        'UPLOADS_DIR=/data\nCORS_ORIGINS=["http://localhost"]\nLOG_LEVEL=DEBUG\n',
        encoding="utf-8",
    )
    return load_settings(env_file=env)


async def test_consulta_fallida_no_deja_el_parametro_en_los_logs(
    session: AsyncSession, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = _settings_debug(tmp_path)
    configure_logging(settings)  # type: ignore[arg-type]
    logger = logging.getLogger("app.prueba.sql")

    with pytest.raises(DBAPIError) as excinfo:
        await session.execute(
            text("SELECT * FROM tabla_que_no_existe WHERE document = :doc"), {"doc": "1020304"}
        )
    logger.exception("consulta fallida", exc_info=excinfo.value)
    logging.getLogger("sqlalchemy.engine").debug("parámetros %s", {"doc": "1020304"})

    salida = capsys.readouterr().out
    assert "consulta fallida" in salida
    assert "1020304" not in salida
    assert "1020304" not in str(excinfo.value)

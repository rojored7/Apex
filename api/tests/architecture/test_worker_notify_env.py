"""El worker recibe lo que `notify` necesita en producción (S5-B8, paso 97; S5-D44). # Rojo B8

Estática, sobre `infra/compose.yml`: el servicio `worker` lee `.env` (host, puerto, remitente y chat
no son secretos) y declara en `environment` los dos secretos que el api tampoco guarda en imagen:
`SMTP_PASSWORD` y `TELEGRAM_BOT_TOKEN`. Sin ellos el correo y las alertas del resumen no salen.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

COMPOSE: Final = Path(__file__).resolve().parents[3] / "infra" / "compose.yml"


def bloque_de(servicio: str) -> str:
    texto = COMPOSE.read_text(encoding="utf-8")
    coincide = re.search(rf"^  {servicio}:\n(.*?)(?=^  [a-z][a-z0-9_-]*:\n|\Z)", texto, re.S | re.M)
    assert coincide is not None, servicio
    return coincide.group(1)


def test_el_worker_lee_env_y_declara_los_secretos_de_correo_y_telegram() -> None:
    bloque = bloque_de("worker")
    assert "env_file:" in bloque and "/.env" in bloque
    assert re.search(r"^\s+SMTP_PASSWORD:", bloque, re.M)
    assert re.search(r"^\s+TELEGRAM_BOT_TOKEN:", bloque, re.M)


def test_control_el_bloque_de_un_servicio_inexistente_falla() -> None:
    try:
        bloque_de("no_existe")
    except AssertionError:
        return
    raise AssertionError("debió fallar")

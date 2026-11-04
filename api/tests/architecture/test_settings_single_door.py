"""`Settings` solo se construye con `load_settings` (S5-W0-3, revisión de seguridad, L4).

`Settings(...)` directo saltaría `_a_config_error` (que convierte el `ValidationError` usando solo
`loc` y `type`, con `include_input=False`): un secreto inválido (`SMTP_PASSWORD`, token de OpenBao)
aparecería dentro del mensaje. Fuera de `core/config.py` nadie llama a `Settings(`.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
CONFIG = SRC / "core" / "config.py"
PATRON = re.compile(r"(?<![A-Za-z_.])Settings\(")


def test_nadie_construye_settings_directo_fuera_de_config() -> None:
    culpables = [
        str(p.relative_to(SRC))
        for p in SRC.rglob("*.py")
        if p != CONFIG and "__pycache__" not in p.parts and PATRON.search(p.read_text("utf-8"))
    ]
    assert culpables == []


def test_config_solo_construye_settings_dentro_de_load_settings() -> None:
    texto = CONFIG.read_text("utf-8")
    llamadas = [m.start() for m in re.finditer(r"(?<![A-Za-z_.])Settings\(_env_file", texto)]
    assert len(llamadas) == 1
    antes = texto[: llamadas[0]]
    assert antes.rfind("def load_settings") > antes.rfind("\ndef ")

"""Rendimiento de `import-members` (S4B-B1, US-112; S4B-D34, D52): marcado `perf`, fuera de los
gates (`-m "not perf"`); se corre aparte con `uv run pytest -m perf <este archivo>`.

- 1.000 filas válidas en menos de 120 s (criterio de US-112);
- 5.000 filas (el tope de filas) se miden y se anotan con `record_property`; techo de 600 s.
Cada alta es una transacción propia bajo el candado de la cadena de auditoría (`4_270_002`),
de ahí la cifra.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cli import app
from app.core.config import Settings
from tests.cli import _apoyo_demo as demo
from tests.cli._apoyo import correr
from tests.conftest import CLAVE_PRUEBA
from tests.factories.users import make_user
from tests.factories.xlsx import fila_valida, make_members_xlsx

Fabrica = async_sessionmaker[AsyncSession]
TECHO_1000_S = 120
TECHO_5000_S = 600

pytestmark = [pytest.mark.perf, pytest.mark.usefixtures("reloj", "limpiar_demo")]


async def _importar_n(
    n: int,
    limpiar_demo: Fabrica,
    settings: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[float, str]:
    async with limpiar_demo() as sesion:
        admin: Any = await make_user(sesion, role="admin", password=CLAVE_PRUEBA)
    archivo = make_members_xlsx(
        import_dir / "socios.xlsx", [fila_valida(i) for i in range(1, n + 1)]
    )
    inicio = time.perf_counter()
    resultado = correr(
        app,
        ["import-members", str(archivo), "--as", admin.email],
        "dev",
        base=settings,
        monkeypatch=monkeypatch,
    )
    duracion = time.perf_counter() - inicio
    assert resultado.exit_code == 0, resultado.output
    assert re.search(rf"created={n}\b", resultado.output), resultado.output
    assert (await demo.contar(limpiar_demo))["socios"] == n
    return duracion, resultado.output


async def test_mil_filas_en_menos_de_120_segundos(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
    record_property: Any,
) -> None:
    duracion, _ = await _importar_n(
        1000, limpiar_demo, settings_importacion, import_dir, monkeypatch
    )

    record_property("segundos_1000_filas", round(duracion, 1))
    assert duracion < TECHO_1000_S, f"1.000 filas tardaron {duracion:.1f} s"


async def test_cinco_mil_filas_se_miden_y_no_pasan_de_600_segundos(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
    record_property: Any,
) -> None:
    duracion, _ = await _importar_n(
        5000, limpiar_demo, settings_importacion, import_dir, monkeypatch
    )

    record_property("segundos_5000_filas", round(duracion, 1))
    assert duracion < TECHO_5000_S, f"5.000 filas tardaron {duracion:.1f} s"

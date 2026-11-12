"""El `Reencryptor` de `attachment.sensitive` queda registrado en cada raíz de proceso (S6-C1;
S6-D60, G-09).

`core/crypto/service.py` delega la rotación y el recuento de `retire-key` en el puerto de la
clase; sin él, `rotate-key attachment.sensitive` responde `rotation_not_supported` y `retire-key`
contaría 0 objetos (pérdida irrecuperable, S6-D107). Las raíces de proceso son `main.create_app()`
(api), `cli_base.cli_runtime()` (todo comando de `tools`) y el worker (que no rota ni retira, así
que no se exige). Cada prueba parte de un registro vacío (`_reset_for_tests`).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.crypto import reencryptor
from app.core.crypto.reencryptor import reencryptor_registered

CLASE = "attachment.sensitive"
SRC = Path(__file__).resolve().parents[2] / "src" / "app"


@pytest.fixture(autouse=True)
def registro_vacio() -> Iterator[None]:
    reencryptor._reset_for_tests()
    try:
        yield
    finally:
        reencryptor._reset_for_tests()


def test_create_app_registra_el_reencryptor_de_attachment_sensitive(
    settings_prueba: object,
) -> None:
    from app.main import create_app

    assert not reencryptor_registered(CLASE)
    create_app(settings_prueba)  # type: ignore[arg-type]
    assert reencryptor_registered(CLASE)


async def test_cli_runtime_registra_el_reencryptor_de_attachment_sensitive(
    settings_prueba: object,
) -> None:
    from app import cli_base

    assert not reencryptor_registered(CLASE)
    async with cli_base.cli_runtime(settings_prueba):  # type: ignore[arg-type]
        assert reencryptor_registered(CLASE)


def test_main_y_cli_base_llaman_register_reencryptor_del_service_de_attachments() -> None:
    """Respaldo estático: los dos archivos nombran la llamada (un tercer camino que olvide
    registrar se vería aquí)."""
    for relativo in ("main.py", "cli_base.py"):
        fuente = (SRC / relativo).read_text(encoding="utf-8")
        assert "register_reencryptor" in fuente, relativo
        assert "attachments" in fuente, relativo


def test_registrar_dos_veces_es_un_error_y_el_service_lo_tolera() -> None:
    """`create_app` puede llamarse varias veces en un proceso de pruebas: la función del módulo
    es idempotente (no relanza `ValueError` si ya está su propio puerto)."""
    from app.modules.attachments import service

    service.register_reencryptor()
    service.register_reencryptor()
    assert reencryptor_registered(CLASE)

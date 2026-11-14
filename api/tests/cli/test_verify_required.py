"""`cli_manifest.verify_required`: cuándo la prueba de custodia deja de pedir el verify-kek-backup.

Solo con las TRES condiciones: cero filas `local` `encrypt|index` (cualquier estado), sin archivo de
KEK y con la entrada de auditoría que deja `retire-local-kek` (`{kek_local: retirada}`). Una
ausencia sola (ruta `None`, otra ruta, volumen no montado) nunca basta; el error al comprobar el
archivo cuenta como presente (falla cerrado).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from app.cli_manifest import verify_required
from app.core.config import Settings
from app.core.crypto.local_provider import kek_file_present
from tests.cli._apoyo_custodia import con_retiro_de_la_kek
from tests.crypto._migracion import Entorno, migracion_lista, migrar_a_mano

__all__ = ["migracion_lista"]
pytestmark = pytest.mark.usefixtures("reloj", "limpiar_demo")


def _ajustes(base: Settings, ruta: Path | None) -> Settings:
    return base.model_copy(update={"CRYPTO_LOCAL_KEK_PATH": ruta})


async def _exige(e: Entorno, ajustes: Settings, *, siempre: bool = False) -> bool:
    async with e.fabrica() as sesion:
        return await verify_required(sesion, ajustes, always=siempre)


async def test_sin_filas_sin_archivo_y_con_la_auditoria_del_retiro_no_se_exige(
    migracion_lista: Entorno, settings_prueba: Settings, tmp_path: Path
) -> None:
    await migrar_a_mano(migracion_lista)
    await con_retiro_de_la_kek(migracion_lista.fabrica)

    assert await _exige(migracion_lista, _ajustes(settings_prueba, tmp_path / "no.bin")) is False
    assert await _exige(migracion_lista, _ajustes(settings_prueba, None)) is False


async def test_sin_filas_ni_archivo_pero_sin_la_auditoria_del_retiro_se_exige(
    migracion_lista: Entorno, settings_prueba: Settings, tmp_path: Path
) -> None:
    await migrar_a_mano(migracion_lista)

    assert await _exige(migracion_lista, _ajustes(settings_prueba, tmp_path / "no.bin")) is True


async def test_con_la_ruta_de_la_kek_en_none_y_sin_la_auditoria_se_exige(
    migracion_lista: Entorno, settings_prueba: Settings
) -> None:
    await migrar_a_mano(migracion_lista)

    assert await _exige(migracion_lista, _ajustes(settings_prueba, None)) is True


async def test_filas_locales_retiradas_con_el_archivo_ausente_se_exige(
    migracion_lista: Entorno, settings_prueba: Settings, tmp_path: Path
) -> None:
    await con_retiro_de_la_kek(migracion_lista.fabrica)
    async with migracion_lista.fabrica() as sesion, sesion.begin():
        await sesion.execute(
            text(
                "UPDATE crypto.crypto_keys SET state = 'retired' "
                "WHERE provider = 'local' AND purpose IN ('encrypt', 'index')"
            )
        )

    assert await _exige(migracion_lista, _ajustes(settings_prueba, tmp_path / "no.bin")) is True


async def test_con_la_auditoria_pero_con_el_archivo_presente_se_exige(
    migracion_lista: Entorno, settings_prueba: Settings
) -> None:
    await migrar_a_mano(migracion_lista)
    await con_retiro_de_la_kek(migracion_lista.fabrica)

    assert await _exige(migracion_lista, settings_prueba) is True


async def test_con_la_auditoria_y_filas_locales_se_exige(
    migracion_lista: Entorno, settings_prueba: Settings, tmp_path: Path
) -> None:
    await con_retiro_de_la_kek(migracion_lista.fabrica)

    assert await _exige(migracion_lista, _ajustes(settings_prueba, tmp_path / "no.bin")) is True


async def test_siempre_exige_aunque_se_cumplan_las_tres_condiciones(
    migracion_lista: Entorno, settings_prueba: Settings, tmp_path: Path
) -> None:
    await migrar_a_mano(migracion_lista)
    await con_retiro_de_la_kek(migracion_lista.fabrica)

    ajustes = _ajustes(settings_prueba, tmp_path / "no.bin")
    assert await _exige(migracion_lista, ajustes, siempre=True) is True


def test_un_permission_error_al_comprobar_el_archivo_cuenta_como_presente(
    settings_prueba: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denegado(self: Path) -> bool:
        raise PermissionError(f"sin acceso a {self}")

    monkeypatch.setattr(Path, "exists", denegado)

    assert kek_file_present(_ajustes(settings_prueba, tmp_path / "kek.bin")) is True


def test_sin_ruta_de_kek_el_archivo_no_cuenta_como_presente(settings_prueba: Settings) -> None:
    assert kek_file_present(_ajustes(settings_prueba, None)) is False

"""Rojo B2 · `retire-local-kek --as <correo> [--yes] [--manifest RUTA]` (S5-B2, paso 46; S5-D73).

Precondiciones, en este orden, todas con salida 2 y textos fijos:
1. `verify_provider` en 0 para `openbao`: ninguna fila `encrypt|index` `local` (`QUEDAN_LOCAL`);
2. `verify-kek-backup` `ok` de una persona de menos de 24 h (`SIN_VERIFY`);
3. manifiesto firmado, reciente, con `openbao_snapshot` verificado y presente en disco
   (`SIN_MANIFIESTO`);
4. confirmación `RETIRAR` por stdin o `--yes` (`la confirmación debe ser exactamente RETIRAR`).
Luego `os.unlink` de `CRYPTO_LOCAL_KEK_PATH` (la copia de `tmp_path/keys`), salida
`retire-local-kek: KEK local retirada`, auditoría `update` sobre `crypto.crypto_keys` con
`record_id=None` y `after={"kek_local": "retirada"}`, y NINGUNA fila `wrap` ni `rotate` en
`crypto_ops` (ningún verbo de `OP_VERBS` aplica al retiro). La llave de firma local no se toca.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.cli_ops import retire_local_kek as retire_local_kek_mod
from app.core.audit import AuditEntry
from app.core.config import Settings
from app.core.crypto import migration as migration_mod
from app.core.crypto.keyring import Keyring
from tests.cli._apoyo_custodia import (
    MANIFIESTOS_MALOS,
    OTRA_OPERACION,
    QUEDAN_LOCAL,
    SIN_AS_EN_PRODUCCION,
    SIN_MANIFIESTO,
    SIN_VERIFY,
    UNLINK_FALLO,
    VERIFY_MALOS,
    con_verify,
    ejecutar,
    manifiesto_bueno,
)
from tests.crypto._migracion import Entorno, migrar_a_mano
from tests.crypto._rotacion import cuenta_de_ops

pytestmark = pytest.mark.usefixtures("reloj", "limpiar_demo")

MALA_CONFIRMACION = "la confirmación debe ser exactamente RETIRAR"


def _retirar(
    settings: Settings, mp: pytest.MonkeyPatch, admin: Any, manifiesto: Path, *extra: str, **kw: Any
) -> Any:
    args = ["--as", admin.email, "--manifest", str(manifiesto)]
    return ejecutar(settings, mp, "retire-local-kek", *args, *extra, **kw)


def _kek(settings: Settings) -> Path:
    assert settings.CRYPTO_LOCAL_KEK_PATH is not None
    return settings.CRYPTO_LOCAL_KEK_PATH


async def _auditoria(e: Entorno) -> list[AuditEntry]:
    async with e.fabrica() as sesion:
        filas = await sesion.scalars(
            select(AuditEntry).where(
                AuditEntry.action == "update", AuditEntry.table_name == "crypto.crypto_keys"
            )
        )
        return [f for f in filas if (f.after or {}).get("kek_local") is not None]


async def _todo_listo(e: Entorno, admin: Any) -> None:
    await migrar_a_mano(e)
    await con_verify(e, admin)


async def test_con_todo_en_orden_y_retirar_borra_la_kek_y_sale_0(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _todo_listo(custodia, admin_custodia)
    kek = _kek(settings_custodia)
    assert kek.is_file()

    resultado = _retirar(
        settings_custodia,
        monkeypatch,
        admin_custodia,
        manifiesto_bueno(tmp_path),
        entrada="RETIRAR\n",
    )

    assert resultado.exit_code == 0, resultado.output
    assert "retire-local-kek: KEK local retirada" in resultado.output
    assert not kek.exists()
    assert settings_custodia.CRYPTO_LOCAL_SIGNING_KEY_PATH.is_file()


async def test_yes_evita_la_confirmacion(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _todo_listo(custodia, admin_custodia)

    resultado = _retirar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path), "--yes"
    )

    assert resultado.exit_code == 0, resultado.output
    assert not _kek(settings_custodia).exists()


async def test_audita_el_retiro_sin_record_id_y_sin_filas_de_crypto_ops(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _todo_listo(custodia, admin_custodia)
    async with custodia.fabrica() as sesion:
        envolturas = await cuenta_de_ops(sesion, "wrap")
        rotaciones = await cuenta_de_ops(sesion, "rotate")

    resultado = _retirar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path), "--yes"
    )

    assert resultado.exit_code == 0, resultado.output
    (entrada,) = await _auditoria(custodia)
    assert entrada.after == {"kek_local": "retirada"}
    assert entrada.record_id is None and entrada.user_id == admin_custodia.id
    async with custodia.fabrica() as sesion:
        assert await cuenta_de_ops(sesion, "wrap") == envolturas
        assert await cuenta_de_ops(sesion, "rotate") == rotaciones


async def test_despues_del_retiro_el_keyring_carga_con_openbao_sin_el_archivo(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _todo_listo(custodia, admin_custodia)
    resultado = _retirar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path), "--yes"
    )
    assert resultado.exit_code == 0, resultado.output
    assert not _kek(settings_custodia).exists()

    async with custodia.fabrica() as sesion:
        keyring = Keyring()
        await keyring.load_all(sesion, custodia.resolver_sin_local())

    assert keyring.active_for("encrypt", "member.document").provider == "openbao"


async def test_la_salida_no_trae_material(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _todo_listo(custodia, admin_custodia)
    kek_hex = _kek(settings_custodia).read_bytes().hex()

    resultado = _retirar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path), "--yes"
    )

    assert resultado.exit_code == 0, resultado.output
    assert kek_hex not in resultado.output
    assert "vault:v" not in resultado.output and "apx1." not in resultado.output
    assert "retire-local-kek:" in resultado.output


# Precondiciones --------------------------------------------------------------------------------


async def test_con_filas_local_sale_2_y_no_borra_nada(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await con_verify(custodia, admin_custodia)  # las filas siguen en `local`

    resultado = _retirar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path), "--yes"
    )

    assert resultado.exit_code == 2, resultado.output
    assert QUEDAN_LOCAL in resultado.output
    assert _kek(settings_custodia).is_file()
    assert await _auditoria(custodia) == []


@pytest.mark.parametrize("caso", list(VERIFY_MALOS.values()), ids=list(VERIFY_MALOS))
async def test_sin_un_verify_kek_backup_reciente_de_una_persona_sale_2(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caso: dict[str, Any] | None,
) -> None:
    await migrar_a_mano(custodia)
    if caso is not None:
        await con_verify(custodia, admin_custodia, **caso)

    resultado = _retirar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path), "--yes"
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_VERIFY in resultado.output
    assert _kek(settings_custodia).is_file()
    assert await _auditoria(custodia) == []


@pytest.mark.parametrize("caso", list(MANIFIESTOS_MALOS.values()), ids=list(MANIFIESTOS_MALOS))
async def test_un_manifiesto_sin_instantanea_valida_sale_2_con_el_mensaje_fijo(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caso: dict[str, Any],
) -> None:
    await _todo_listo(custodia, admin_custodia)

    resultado = _retirar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path, **caso), "--yes"
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_MANIFIESTO in resultado.output
    assert _kek(settings_custodia).is_file()
    assert await _auditoria(custodia) == []


@pytest.mark.parametrize("escrito", ["retirar\n", "SI\n", "RETIRAR YA\n", "\n"])
async def test_una_confirmacion_distinta_de_retirar_sale_2_y_no_borra(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    escrito: str,
) -> None:
    await _todo_listo(custodia, admin_custodia)

    resultado = _retirar(
        settings_custodia,
        monkeypatch,
        admin_custodia,
        manifiesto_bueno(tmp_path),
        entrada=escrito,
    )

    assert resultado.exit_code == 2, resultado.output
    assert MALA_CONFIRMACION in resultado.output
    assert _kek(settings_custodia).is_file()
    assert await _auditoria(custodia) == []


async def test_en_produccion_sin_as_sale_2(
    settings_produccion: Settings,
    custodia: Entorno,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await migrar_a_mano(custodia)

    resultado = ejecutar(
        settings_produccion.model_copy(update={"BACKUP_DIR": tmp_path}),
        monkeypatch,
        "retire-local-kek",
        "--yes",
        env="production",
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_AS_EN_PRODUCCION in resultado.output


# S5-D190: orden seguro del retiro ----------------------------------------------------------------


async def test_una_segunda_corrida_sin_archivo_dice_ya_retirada_y_no_audita_otra_vez(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _todo_listo(custodia, admin_custodia)
    manifiesto = manifiesto_bueno(tmp_path)
    assert (
        _retirar(settings_custodia, monkeypatch, admin_custodia, manifiesto, "--yes").exit_code == 0
    )

    resultado = _retirar(settings_custodia, monkeypatch, admin_custodia, manifiesto, "--yes")

    assert resultado.exit_code == 0, resultado.output
    assert "retire-local-kek: la KEK local ya estaba retirada" in resultado.output
    assert len(await _auditoria(custodia)) == 1


async def test_con_el_candado_de_la_kek_tomado_sale_2_y_no_borra_ni_audita(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    candado_kek_tomado: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _todo_listo(custodia, admin_custodia)

    resultado = _retirar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path), "--yes"
    )

    assert resultado.exit_code == 2, resultado.output
    assert OTRA_OPERACION in resultado.output
    assert _kek(settings_custodia).is_file()
    assert await _auditoria(custodia) == []


async def test_una_fila_que_vuelve_a_local_antes_del_commit_sale_2_sin_borrar_ni_auditar(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`verify_provider` se repite DENTRO de la transacción de la auditoría."""
    await _todo_listo(custodia, admin_custodia)
    respuestas = iter([0, 3])  # la comprobación previa pasa; la repetida ve 3 filas fuera

    async def verify_cambiante(*_a: Any, **_k: Any) -> int:
        return next(respuestas)

    monkeypatch.setattr(migration_mod, "verify_provider", verify_cambiante)

    resultado = _retirar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path), "--yes"
    )

    assert resultado.exit_code == 2, resultado.output
    assert QUEDAN_LOCAL in resultado.output
    assert _kek(settings_custodia).is_file()
    assert await _auditoria(custodia) == []


async def test_si_unlink_falla_tras_el_commit_sale_1_y_la_auditoria_queda(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _todo_listo(custodia, admin_custodia)

    def sin_permiso(_ruta: Any) -> None:
        raise PermissionError

    monkeypatch.setattr(retire_local_kek_mod.os, "unlink", sin_permiso)

    resultado = _retirar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path), "--yes"
    )

    assert resultado.exit_code == 1, resultado.output
    assert UNLINK_FALLO in resultado.output
    assert _kek(settings_custodia).is_file()
    assert len(await _auditoria(custodia)) == 1

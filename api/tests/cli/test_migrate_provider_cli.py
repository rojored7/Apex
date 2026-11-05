"""Rojo B2 · `migrate-provider --from local --to openbao [--as] [--dry-run] [--yes] [--verify]
[--manifest RUTA]` (S5-B2, paso 46; S5-D18, H-1).

Salida (stdout y stderr juntos en `resultado.output`):
- `migrate-provider: total=N` antes de escribir y `migrate-provider: hecho=D/N`; con éxito termina
  en `migrate-provider: migración completa`; sin nada, `migrate-provider: nada que migrar`;
- `--dry-run`: `total=N` y `migrate-provider: dry-run: no se escribió nada`, sin H-1;
- `--verify` (solo lectura): `migrate-provider: fuera_de_destino=N`, exit 1 si N > 0, 0 si no;
- exigencias de H-1 (ver `_apoyo_custodia`) y confirmación `MIGRAR` por stdin o `--yes`: la
  confirmación mala sale 2 con `la confirmación debe ser exactamente MIGRAR`;
- un error al migrar una llave: exit 1, `repita el comando`, nada del texto del proveedor;
- auditoría `update` sobre `crypto.crypto_keys`, `record_id` = id del job y
  `after = {"from", "to", "total", "done"}`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.core.audit import AuditEntry
from app.core.config import Settings
from app.core.crypto import migration as migration_mod
from tests.cli._apoyo_custodia import (
    BASE_OCUPADA,
    MANIFIESTOS_MALOS,
    SIN_AS_EN_PRODUCCION,
    SIN_MANIFIESTO,
    SIN_VERIFY,
    VERIFY_MALOS,
    base_ocupada,
    con_verify,
    ejecutar,
    manifiesto_bueno,
)
from tests.crypto._migracion import (
    Entorno,
    ProveedorEspia,
    instantanea,
    jobs_de,
    llaves_envueltas,
    migrar_a_mano,
    todos_los_jobs,
)

pytestmark = pytest.mark.usefixtures("reloj", "limpiar_demo")

MALA_CONFIRMACION = "la confirmación debe ser exactamente MIGRAR"


def _migrar(
    settings: Settings, mp: pytest.MonkeyPatch, admin: Any, manifiesto: Path, *extra: str, **kw: Any
) -> Any:
    args = [
        "--from",
        "local",
        "--to",
        "openbao",
        "--as",
        admin.email,
        "--manifest",
        str(manifiesto),
    ]
    return ejecutar(settings, mp, "migrate-provider", *args, *extra, **kw)


async def _auditoria(e: Entorno) -> list[AuditEntry]:
    async with e.fabrica() as sesion:
        filas = await sesion.scalars(
            select(AuditEntry).where(
                AuditEntry.action == "update", AuditEntry.table_name == "crypto.crypto_keys"
            )
        )
        return [f for f in filas if (f.after or {}).get("from") is not None]


async def _intacto(e: Entorno, antes: list[Any], jobs: int) -> None:
    assert await instantanea(e.fabrica) == antes
    assert await todos_los_jobs(e.fabrica) == jobs
    assert await _auditoria(e) == []


async def _punto_de_partida(e: Entorno) -> tuple[list[Any], int]:
    return await instantanea(e.fabrica), await todos_los_jobs(e.fabrica)


# Camino feliz ----------------------------------------------------------------------------------


async def test_con_todo_en_orden_y_migrar_por_stdin_migra_y_sale_0(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await con_verify(custodia, admin_custodia)
    total = len(await llaves_envueltas(custodia.fabrica))

    resultado = _migrar(
        settings_custodia,
        monkeypatch,
        admin_custodia,
        manifiesto_bueno(tmp_path),
        entrada="MIGRAR\n",
    )

    assert resultado.exit_code == 0, resultado.output
    assert f"migrate-provider: total={total}" in resultado.output
    assert f"migrate-provider: hecho={total}/{total}" in resultado.output
    assert "migrate-provider: migración completa" in resultado.output
    assert {f.provider for f in await llaves_envueltas(custodia.fabrica)} == {"openbao"}


async def test_yes_evita_la_confirmacion(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await con_verify(custodia, admin_custodia)

    resultado = _migrar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path), "--yes"
    )

    assert resultado.exit_code == 0, resultado.output
    assert "migrate-provider: migración completa" in resultado.output
    assert {f.provider for f in await llaves_envueltas(custodia.fabrica)} == {"openbao"}


async def test_audita_un_update_con_from_to_total_y_done(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await con_verify(custodia, admin_custodia)
    total = len(await llaves_envueltas(custodia.fabrica))

    resultado = _migrar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path), "--yes"
    )

    assert resultado.exit_code == 0, resultado.output
    (entrada,) = await _auditoria(custodia)
    (job,) = await jobs_de(custodia.fabrica, "migrate_provider")
    assert entrada.after == {"from": "local", "to": "openbao", "total": total, "done": total}
    assert entrada.record_id == job.id
    assert entrada.user_id == admin_custodia.id


async def test_la_segunda_corrida_dice_nada_que_migrar_y_sale_0(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await con_verify(custodia, admin_custodia)
    manifiesto = manifiesto_bueno(tmp_path)
    assert (
        _migrar(settings_custodia, monkeypatch, admin_custodia, manifiesto, "--yes").exit_code == 0
    )
    jobs = await todos_los_jobs(custodia.fabrica)
    auditoria = len(await _auditoria(custodia))

    resultado = _migrar(settings_custodia, monkeypatch, admin_custodia, manifiesto, "--yes")

    assert resultado.exit_code == 0, resultado.output
    assert "migrate-provider: nada que migrar" in resultado.output
    assert await todos_los_jobs(custodia.fabrica) == jobs
    assert len(await _auditoria(custodia)) == auditoria


async def test_la_salida_no_trae_material_ni_blobs(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await con_verify(custodia, admin_custodia)

    resultado = _migrar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path), "--yes"
    )

    assert resultado.exit_code == 0, resultado.output
    assert "vault:v" not in resultado.output and "apx1." not in resultado.output
    assert "migrate-provider: total=" in resultado.output


async def test_la_reversa_openbao_a_local_pasa_por_las_mismas_exigencias(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await migrar_a_mano(custodia)
    await con_verify(custodia, admin_custodia)

    resultado = ejecutar(
        settings_custodia,
        monkeypatch,
        "migrate-provider",
        "--from",
        "openbao",
        "--to",
        "local",
        "--as",
        admin_custodia.email,
        "--manifest",
        str(manifiesto_bueno(tmp_path)),
        "--yes",
    )

    assert resultado.exit_code == 0, resultado.output
    assert "migrate-provider: migración completa" in resultado.output
    assert {f.provider for f in await llaves_envueltas(custodia.fabrica)} == {"local"}


# Argumentos ------------------------------------------------------------------------------------


async def test_en_produccion_sin_as_sale_2(
    settings_produccion: Settings,
    custodia: Entorno,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    antes, jobs = await _punto_de_partida(custodia)

    resultado = ejecutar(
        settings_produccion.model_copy(update={"BACKUP_DIR": tmp_path}),
        monkeypatch,
        "migrate-provider",
        "--from",
        "local",
        "--to",
        "openbao",
        "--yes",
        env="production",
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_AS_EN_PRODUCCION in resultado.output
    await _intacto(custodia, antes, jobs)


@pytest.mark.parametrize(
    "origen,destino",
    [("local", "local"), ("openbao", "openbao"), ("nube", "openbao"), ("local", "nube")],
)
async def test_un_par_from_to_invalido_sale_2(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    origen: str,
    destino: str,
) -> None:
    antes, jobs = await _punto_de_partida(custodia)

    resultado = ejecutar(
        settings_custodia,
        monkeypatch,
        "migrate-provider",
        "--from",
        origen,
        "--to",
        destino,
        "--as",
        admin_custodia.email,
        "--manifest",
        str(manifiesto_bueno(tmp_path)),
        "--yes",
    )

    assert resultado.exit_code == 2, resultado.output
    assert "migrate-provider:" in resultado.output
    await _intacto(custodia, antes, jobs)


# Exigencias de H-1 -----------------------------------------------------------------------------


@pytest.mark.parametrize("caso", list(VERIFY_MALOS.values()), ids=list(VERIFY_MALOS))
async def test_sin_un_verify_kek_backup_reciente_de_una_persona_sale_2(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caso: dict[str, Any] | None,
) -> None:
    if caso is not None:
        await con_verify(custodia, admin_custodia, **caso)
    antes, jobs = await _punto_de_partida(custodia)

    resultado = _migrar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path), "--yes"
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_VERIFY in resultado.output
    await _intacto(custodia, antes, jobs)


@pytest.mark.parametrize("caso", list(MANIFIESTOS_MALOS.values()), ids=list(MANIFIESTOS_MALOS))
async def test_un_manifiesto_sin_firma_o_sin_instantanea_valida_sale_2_con_el_mensaje_fijo(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caso: dict[str, Any],
) -> None:
    await con_verify(custodia, admin_custodia)
    antes, jobs = await _punto_de_partida(custodia)

    resultado = _migrar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path, **caso), "--yes"
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_MANIFIESTO in resultado.output
    await _intacto(custodia, antes, jobs)


async def test_sin_latest_json_sale_2_con_el_mensaje_fijo(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await con_verify(custodia, admin_custodia)
    antes, jobs = await _punto_de_partida(custodia)

    resultado = _migrar(
        settings_custodia,
        monkeypatch,
        admin_custodia,
        tmp_path / "no-existe" / "latest.json",
        "--yes",
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_MANIFIESTO in resultado.output
    await _intacto(custodia, antes, jobs)


# Confirmación ----------------------------------------------------------------------------------


@pytest.mark.parametrize("escrito", ["migrar\n", "SI\n", "MIGRAR AHORA\n", "\n"])
async def test_una_confirmacion_distinta_de_migrar_sale_2_sin_escribir(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    escrito: str,
) -> None:
    await con_verify(custodia, admin_custodia)
    antes, jobs = await _punto_de_partida(custodia)

    resultado = _migrar(
        settings_custodia,
        monkeypatch,
        admin_custodia,
        manifiesto_bueno(tmp_path),
        entrada=escrito,
    )

    assert resultado.exit_code == 2, resultado.output
    assert MALA_CONFIRMACION in resultado.output
    await _intacto(custodia, antes, jobs)


# --dry-run y --verify --------------------------------------------------------------------------


async def test_dry_run_imprime_el_plan_sin_exigir_h1_y_sin_escribir(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    antes, jobs = await _punto_de_partida(custodia)
    total = len(await llaves_envueltas(custodia.fabrica))

    resultado = ejecutar(
        settings_custodia,
        monkeypatch,
        "migrate-provider",
        "--from",
        "local",
        "--to",
        "openbao",
        "--as",
        admin_custodia.email,
        "--manifest",
        str(tmp_path / "no-existe.json"),
        "--dry-run",
    )

    assert resultado.exit_code == 0, resultado.output
    assert f"migrate-provider: total={total}" in resultado.output
    assert "migrate-provider: dry-run: no se escribió nada" in resultado.output
    assert custodia.transit.llamadas("/encrypt/") == []
    await _intacto(custodia, antes, jobs)


async def test_verify_sale_1_si_queda_una_fila_local_y_no_escribe(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    antes, jobs = await _punto_de_partida(custodia)
    total = len(await llaves_envueltas(custodia.fabrica))

    resultado = ejecutar(
        settings_custodia,
        monkeypatch,
        "migrate-provider",
        "--from",
        "local",
        "--to",
        "openbao",
        "--as",
        admin_custodia.email,
        "--verify",
    )

    assert resultado.exit_code == 1, resultado.output
    assert f"migrate-provider: fuera_de_destino={total}" in resultado.output
    await _intacto(custodia, antes, jobs)


async def test_verify_sale_0_cuando_todo_esta_en_openbao(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await migrar_a_mano(custodia)

    resultado = ejecutar(
        settings_custodia,
        monkeypatch,
        "migrate-provider",
        "--from",
        "local",
        "--to",
        "openbao",
        "--as",
        admin_custodia.email,
        "--verify",
    )

    assert resultado.exit_code == 0, resultado.output
    assert "migrate-provider: fuera_de_destino=0" in resultado.output


# Errores del proveedor -------------------------------------------------------------------------


async def test_un_fallo_del_proveedor_sale_1_sin_su_texto_y_se_reanuda(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await con_verify(custodia, admin_custodia)
    manifiesto = manifiesto_bueno(tmp_path)
    total = len(await llaves_envueltas(custodia.fabrica))
    sano = custodia.openbao
    custodia.openbao = ProveedorEspia(sano, fallar_wrap_en=3, mensaje="boom-secreto-del-proveedor")

    primera = _migrar(settings_custodia, monkeypatch, admin_custodia, manifiesto, "--yes")

    assert primera.exit_code == 1, primera.output
    assert "repita el comando" in primera.output
    assert "boom-secreto" not in primera.output and "vault:v" not in primera.output
    (job,) = await jobs_de(custodia.fabrica, "migrate_provider")
    assert job.status == "failed"

    custodia.openbao = sano
    segunda = _migrar(settings_custodia, monkeypatch, admin_custodia, manifiesto, "--yes")

    assert segunda.exit_code == 0, segunda.output
    assert f"migrate-provider: hecho={total}/{total}" in segunda.output
    (mismo,) = await jobs_de(custodia.fabrica, "migrate_provider")
    assert (mismo.id, mismo.status) == (job.id, "done")
    entradas = await _auditoria(custodia)
    assert len(entradas) == 2
    parcial = next(e for e in entradas if "failed" in (e.after or {}))
    final = next(e for e in entradas if "failed" not in (e.after or {}))
    assert parcial.after is not None and parcial.after["failed"] is True
    assert final.after == {"from": "local", "to": "openbao", "total": total, "done": total}


# S5-D189: base ocupada y auditoría del fallo parcial ---------------------------------------------


async def test_una_base_ocupada_sale_1_con_el_mensaje_fijo_sin_traza(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await con_verify(custodia, admin_custodia)
    monkeypatch.setattr(migration_mod, "_una_llave", base_ocupada)

    resultado = _migrar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path), "--yes"
    )

    assert resultado.exit_code == 1, resultado.output
    assert BASE_OCUPADA in resultado.output
    assert "Traceback" not in resultado.output and "DBAPIError" not in resultado.output
    (job,) = await jobs_de(custodia.fabrica, "migrate_provider")
    assert (job.status, job.error) == ("failed", "busy")


async def test_un_fallo_parcial_tambien_se_audita_con_failed_true(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await con_verify(custodia, admin_custodia)
    total = len(await llaves_envueltas(custodia.fabrica))
    sano = custodia.openbao
    custodia.openbao = ProveedorEspia(sano, fallar_wrap_en=3)

    primera = _migrar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path), "--yes"
    )

    assert primera.exit_code == 1, primera.output
    (parcial,) = await _auditoria(custodia)
    assert parcial.after == {
        "from": "local",
        "to": "openbao",
        "total": total,
        "done": 2,
        "failed": True,
    }

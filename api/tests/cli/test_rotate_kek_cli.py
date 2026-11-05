"""Rojo B2 · `rotate-kek [--trim] --as <correo> [--manifest RUTA]` (S5-B2, paso 46; S5-D19, D55a).

Parte de filas ya en OpenBao (`migrar_a_mano`). Salida:
- `rotate-kek: version=V` (la versión nueva de Transit), `rotate-kek: total=N`,
  `rotate-kek: hecho=D/N` y, al final, `rotate-kek: llaves re-envueltas`;
- las exigencias de H-1 (ver `_apoyo_custodia`) se revisan ANTES de rotar nada;
- un fallo a mitad: exit 1, `repita el comando`, sin texto del proveedor; reanudar NO rota otra vez;
- auditoría `update` sobre `crypto.crypto_keys` con `record_id` = job y
  `after = {"event": "rotate_kek", "version": V, "total": N, "done": N}`;
- `--trim` exige, en este orden: H-1; `trim_ready` (`TRIM_NO_LISTO`); un respaldo con instantánea
  POSTERIOR a `finished_at` del job `rewrap` (`SIN_SNAPSHOT_POSTERIOR`); la confirmación
  `RECORTAR` por stdin (`la confirmación debe ser exactamente RECORTAR`). Con todo en orden sube
  `min_decryption_version` a la última (`rotate-kek: min_decryption_version=V`) por
  `keys/apex-kek/config`, sin rotar ni re-envolver, y jamás llama a `/trim`.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.cli_ops import rotate_kek as rotate_kek_mod
from app.core.audit import AuditEntry
from app.core.config import Settings
from app.core.crypto import migration as migration_mod
from app.core.crypto.openbao_wire import parse_version
from tests.cli._apoyo_custodia import (
    BASE_OCUPADA,
    MANIFIESTOS_MALOS,
    OTRA_OPERACION,
    SIN_AS_EN_PRODUCCION,
    SIN_MANIFIESTO,
    SIN_SNAPSHOT_POSTERIOR,
    SIN_VERIFY,
    TRIM_CAMBIO,
    TRIM_NO_LISTO,
    VERIFY_MALOS,
    base_ocupada,
    con_verify,
    ejecutar,
    manifiesto_bueno,
)
from tests.conftest import T0
from tests.crypto._migracion import (
    KEK_REF,
    Entorno,
    ProveedorEspia,
    instantanea,
    jobs_de,
    llaves_envueltas,
    migrar_a_mano,
    rewrapear_a_mano,
    todos_los_jobs,
)

pytestmark = pytest.mark.usefixtures("reloj", "limpiar_demo")

MALA_CONFIRMACION = "la confirmación debe ser exactamente RECORTAR"


def _rotar(
    settings: Settings, mp: pytest.MonkeyPatch, admin: Any, manifiesto: Path, *extra: str, **kw: Any
) -> Any:
    args = ["--as", admin.email, "--manifest", str(manifiesto)]
    return ejecutar(settings, mp, "rotate-kek", *args, *extra, **kw)


async def _versiones(e: Entorno) -> list[int]:
    return [parse_version(bytes(f.wrapped_material)) for f in await llaves_envueltas(e.fabrica)]


async def _auditoria(e: Entorno) -> list[AuditEntry]:
    async with e.fabrica() as sesion:
        filas = await sesion.scalars(
            select(AuditEntry).where(
                AuditEntry.action == "update", AuditEntry.table_name == "crypto.crypto_keys"
            )
        )
        return [f for f in filas if (f.after or {}).get("event") == "rotate_kek"]


# Rotar y re-envolver ---------------------------------------------------------------------------


async def test_rota_la_kek_y_re_envuelve_cada_fila_a_la_ultima_version(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await migrar_a_mano(custodia)
    await con_verify(custodia, admin_custodia)
    total = len(await llaves_envueltas(custodia.fabrica))

    resultado = _rotar(settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path))

    assert resultado.exit_code == 0, resultado.output
    assert "rotate-kek: version=2" in resultado.output
    assert f"rotate-kek: total={total}" in resultado.output
    assert f"rotate-kek: hecho={total}/{total}" in resultado.output
    assert "rotate-kek: llaves re-envueltas" in resultado.output
    assert set(await _versiones(custodia)) == {custodia.transit.latest_version(KEK_REF)} == {2}
    assert custodia.transit.llamadas("/rewrap/") == []
    (job,) = await jobs_de(custodia.fabrica, "rewrap")
    assert (job.status, job.total, job.done) == ("done", total, total)


async def test_audita_el_rotate_kek_con_version_total_y_done(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await migrar_a_mano(custodia)
    await con_verify(custodia, admin_custodia)
    total = len(await llaves_envueltas(custodia.fabrica))

    resultado = _rotar(settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path))

    assert resultado.exit_code == 0, resultado.output
    (entrada,) = await _auditoria(custodia)
    (job,) = await jobs_de(custodia.fabrica, "rewrap")
    assert entrada.after == {"event": "rotate_kek", "version": 2, "total": total, "done": total}
    assert entrada.record_id == job.id and entrada.user_id == admin_custodia.id


async def test_la_salida_no_trae_material_ni_blobs(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await migrar_a_mano(custodia)
    await con_verify(custodia, admin_custodia)

    resultado = _rotar(settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path))

    assert resultado.exit_code == 0, resultado.output
    assert "vault:v" not in resultado.output and "apx1." not in resultado.output
    assert "rotate-kek: version=" in resultado.output


async def test_un_fallo_a_mitad_sale_1_y_reanudar_no_rota_otra_vez(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await migrar_a_mano(custodia)
    await con_verify(custodia, admin_custodia)
    manifiesto = manifiesto_bueno(tmp_path)
    total = len(await llaves_envueltas(custodia.fabrica))
    sano = custodia.openbao
    custodia.openbao = ProveedorEspia(sano, fallar_wrap_en=3, mensaje="boom-secreto-del-proveedor")

    primera = _rotar(settings_custodia, monkeypatch, admin_custodia, manifiesto)

    assert primera.exit_code == 1, primera.output
    assert "repita el comando" in primera.output
    assert "boom-secreto" not in primera.output and "vault:v" not in primera.output
    (job,) = await jobs_de(custodia.fabrica, "rewrap")
    assert (job.status, job.done) == ("failed", 2)

    custodia.openbao = sano
    segunda = _rotar(settings_custodia, monkeypatch, admin_custodia, manifiesto)

    assert segunda.exit_code == 0, segunda.output
    assert f"rotate-kek: hecho={total}/{total}" in segunda.output
    (mismo,) = await jobs_de(custodia.fabrica, "rewrap")
    assert (mismo.id, mismo.status) == (job.id, "done")
    assert custodia.transit.latest_version(KEK_REF) == 2
    assert set(await _versiones(custodia)) == {2}


# Exigencias de H-1 (antes de rotar nada) -------------------------------------------------------


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
        "rotate-kek",
        env="production",
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_AS_EN_PRODUCCION in resultado.output
    assert custodia.transit.latest_version(KEK_REF) == 1


@pytest.mark.parametrize("caso", list(VERIFY_MALOS.values()), ids=list(VERIFY_MALOS))
async def test_sin_un_verify_kek_backup_reciente_sale_2_y_no_rota(
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
    antes, jobs = await instantanea(custodia.fabrica), await todos_los_jobs(custodia.fabrica)

    resultado = _rotar(settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path))

    assert resultado.exit_code == 2, resultado.output
    assert SIN_VERIFY in resultado.output
    assert custodia.transit.latest_version(KEK_REF) == 1
    assert await instantanea(custodia.fabrica) == antes
    assert await todos_los_jobs(custodia.fabrica) == jobs


@pytest.mark.parametrize("caso", list(MANIFIESTOS_MALOS.values()), ids=list(MANIFIESTOS_MALOS))
async def test_un_manifiesto_sin_instantanea_valida_sale_2_y_no_rota(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caso: dict[str, Any],
) -> None:
    await migrar_a_mano(custodia)
    await con_verify(custodia, admin_custodia)
    antes, jobs = await instantanea(custodia.fabrica), await todos_los_jobs(custodia.fabrica)

    resultado = _rotar(
        settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path, **caso)
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_MANIFIESTO in resultado.output
    assert custodia.transit.latest_version(KEK_REF) == 1
    assert await instantanea(custodia.fabrica) == antes
    assert await todos_los_jobs(custodia.fabrica) == jobs


# --trim ----------------------------------------------------------------------------------------


async def _listo_para_recortar(custodia: Entorno, reloj: Any) -> None:
    """Filas en OpenBao, KEK en v2, todo re-envuelto y un job `rewrap` terminado 3 h antes de T0."""
    await migrar_a_mano(custodia)
    await custodia.openbao.rotate(KEK_REF)
    await rewrapear_a_mano(custodia, terminado=T0 - timedelta(hours=3))


def _recortar(
    settings: Settings, mp: pytest.MonkeyPatch, admin: Any, manifiesto: Path, **kw: Any
) -> Any:
    return _rotar(settings, mp, admin, manifiesto, "--trim", **kw)


async def test_trim_con_todo_en_orden_y_recortar_sube_la_version_minima(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    reloj: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _listo_para_recortar(custodia, reloj)
    await con_verify(custodia, admin_custodia)
    jobs = await todos_los_jobs(custodia.fabrica)
    versiones = await _versiones(custodia)

    resultado = _recortar(
        settings_custodia,
        monkeypatch,
        admin_custodia,
        manifiesto_bueno(tmp_path, antiguedad=timedelta(hours=1)),
        entrada="RECORTAR\n",
    )

    assert resultado.exit_code == 0, resultado.output
    assert "rotate-kek: min_decryption_version=2" in resultado.output
    assert custodia.transit.min_decryption_version[KEK_REF] == 2
    assert custodia.transit.latest_version(KEK_REF) == 2  # no rota otra vez
    assert await todos_los_jobs(custodia.fabrica) == jobs  # ni re-envuelve
    assert await _versiones(custodia) == versiones
    assert custodia.transit.llamadas("/trim") == []


async def test_trim_sin_trim_ready_sale_2_y_no_toca_transit(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await migrar_a_mano(custodia)
    await custodia.openbao.rotate(KEK_REF)  # rotada pero sin re-envolver
    await con_verify(custodia, admin_custodia)

    resultado = _recortar(
        settings_custodia,
        monkeypatch,
        admin_custodia,
        manifiesto_bueno(tmp_path, antiguedad=timedelta(hours=1)),
        entrada="RECORTAR\n",
    )

    assert resultado.exit_code == 2, resultado.output
    assert TRIM_NO_LISTO in resultado.output
    assert custodia.transit.min_decryption_version.get(KEK_REF, 1) == 1
    assert custodia.transit.llamadas("/config") == []


async def test_trim_con_un_respaldo_anterior_a_la_rotacion_sale_2(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    reloj: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _listo_para_recortar(custodia, reloj)
    await con_verify(custodia, admin_custodia)

    resultado = _recortar(
        settings_custodia,
        monkeypatch,
        admin_custodia,
        manifiesto_bueno(tmp_path, antiguedad=timedelta(hours=5)),  # antes del rewrap (T0 - 3 h)
        entrada="RECORTAR\n",
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_SNAPSHOT_POSTERIOR in resultado.output
    assert custodia.transit.min_decryption_version.get(KEK_REF, 1) == 1


@pytest.mark.parametrize("escrito", ["recortar\n", "SI\n", "\n"])
async def test_trim_con_una_confirmacion_distinta_de_recortar_sale_2(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    reloj: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    escrito: str,
) -> None:
    await _listo_para_recortar(custodia, reloj)
    await con_verify(custodia, admin_custodia)

    resultado = _recortar(
        settings_custodia,
        monkeypatch,
        admin_custodia,
        manifiesto_bueno(tmp_path, antiguedad=timedelta(hours=1)),
        entrada=escrito,
    )

    assert resultado.exit_code == 2, resultado.output
    assert MALA_CONFIRMACION in resultado.output
    assert custodia.transit.min_decryption_version.get(KEK_REF, 1) == 1


async def test_trim_sin_verify_reciente_sale_2(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    reloj: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _listo_para_recortar(custodia, reloj)

    resultado = _recortar(
        settings_custodia,
        monkeypatch,
        admin_custodia,
        manifiesto_bueno(tmp_path, antiguedad=timedelta(hours=1)),
        entrada="RECORTAR\n",
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_VERIFY in resultado.output
    assert custodia.transit.min_decryption_version.get(KEK_REF, 1) == 1


async def test_trim_sin_instantanea_valida_sale_2_con_el_mensaje_fijo(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    reloj: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _listo_para_recortar(custodia, reloj)
    await con_verify(custodia, admin_custodia)

    resultado = _recortar(
        settings_custodia,
        monkeypatch,
        admin_custodia,
        manifiesto_bueno(tmp_path, antiguedad=timedelta(hours=1), snapshot=False),
        entrada="RECORTAR\n",
    )

    assert resultado.exit_code == 2, resultado.output
    assert SIN_MANIFIESTO in resultado.output
    assert custodia.transit.min_decryption_version.get(KEK_REF, 1) == 1


# S5-D188: el recorte repite la comprobación justo antes de `config` ------------------------------


async def test_trim_con_otra_rotacion_entre_la_comprobacion_y_recortar_sale_2_y_no_llama_config(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    reloj: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _listo_para_recortar(custodia, reloj)
    await con_verify(custodia, admin_custodia)

    def rotacion_ajena(palabra: str, *, yes: bool) -> None:
        custodia.transit._material[KEK_REF].append(os.urandom(32))  # otra rotación (v3)
        return None  # el operador sí escribió RECORTAR

    monkeypatch.setattr(rotate_kek_mod, "confirmation_error", rotacion_ajena)

    resultado = _recortar(
        settings_custodia,
        monkeypatch,
        admin_custodia,
        manifiesto_bueno(tmp_path, antiguedad=timedelta(hours=1)),
    )

    assert resultado.exit_code == 2, resultado.output
    assert TRIM_CAMBIO in resultado.output
    assert custodia.transit.llamadas("/config") == []
    assert custodia.transit.min_decryption_version.get(KEK_REF, 1) == 1


async def test_rotate_kek_con_la_base_ocupada_sale_1_con_el_mensaje_fijo(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await migrar_a_mano(custodia)
    await con_verify(custodia, admin_custodia)
    monkeypatch.setattr(migration_mod, "_una_llave", base_ocupada)

    resultado = _rotar(settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path))

    assert resultado.exit_code == 1, resultado.output
    assert BASE_OCUPADA in resultado.output and "Traceback" not in resultado.output


async def test_rotate_kek_con_el_candado_de_la_kek_tomado_sale_2(
    settings_custodia: Settings,
    custodia: Entorno,
    admin_custodia: Any,
    candado_kek_tomado: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await migrar_a_mano(custodia)
    await con_verify(custodia, admin_custodia)

    resultado = _rotar(settings_custodia, monkeypatch, admin_custodia, manifiesto_bueno(tmp_path))

    assert resultado.exit_code == 2, resultado.output
    assert OTRA_OPERACION in resultado.output
    assert custodia.transit.latest_version(KEK_REF) == 1

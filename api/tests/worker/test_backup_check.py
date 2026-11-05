"""Job `backup_check` contra la base real y una carpeta de respaldos temporal (S4B-B2.3).

S4B-D23 a D25, D59, D69, D70, D80, D87, D97. `FrozenClock` en `2026-10-21T12:00:00Z` (07:00 de
Bogotá, `today_bogota` = 2026-10-21); el juego de la fábrica nace a las 07:00Z (`now - 5 h`).
- `ok`: `verify: ok` -> `ok`; `skipped` -> `ok_unverified`; del día anterior -> `stale`;
  directorio vacío o sin `latest.json` -> `missing`; `sha256` o tamaño alterados, nombre que no
  corresponde a `created_at` o `created_at` futuro -> `corrupt`; archivo ausente -> `missing`;
  `failed` -> `undecryptable`.
- `latest.json` es dato no confiable: nombres absolutos o con `..` no se leen (-> `missing`), un
  enlace simbólico no se sigue y un `pre-deploy-*` o `pre-restore-*` no vale como `latest.json`.
- `job_runs` guarda `result` = estado y `details` enteros (`verificado`, `edad_horas` =
  floor((now - created_at) / 3600), `tamano_bytes` = suma de los tamaños, `archivos` = juegos
  `apex-*`; los `pre-*` no cuentan). La segunda corrida del día deja dos intentos.
- Alertas: `backup_unhealthy` (job, result) solo si el estado no es `ok` ni `ok_unverified`; siete
  corridas seguidas `ok_unverified` (la actual incluida) también (S4B-D87), seis no.
- El log `backup_check finished` lleva el nombre del juego y nunca la ruta, `upload_error` ni el
  `sha256` completo (S4B-D70); `job_runs.details` jamás lleva nombres.
- El job no abre `age`.
- S5-B13 (S5-D72, S5-D8): con `BACKUP_SIGN_PUBKEY` verifica `latest.json.minisig` por el bus
  (ausente o inválida -> `corrupt`); `openbao_snapshot` es opcional y, si está, se comprueba
  como cualquier archivo del juego (ver el bloque final).
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import threading
import time
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import alerts
from app.core.alerts import ALERT_CONTEXT_KEYS
from app.core.clock import FrozenClock, reset_clock, set_clock
from app.core.config import Settings
from app.core.crypto import archive
from app.core.jobs import DETAIL_KEYS, JobRun
from app.worker.jobs import JOBS, backup_check
from app.worker.jobs.backup_check import MAX_FILES
from app.worker.runner import JobOutcome, run_job
from tests.factories.backup import BackupSet, make_backup_dir, manifest_bytes
from tests.factories.job_runs import make_job_run
from tests.factories.minisign_signer import SigningKey, make_signing_key

Fabrica = async_sessionmaker[AsyncSession]
NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)
HOY = date(2026, 10, 21)
JOB = "backup_check"
SPEC = next(s for s in JOBS if s.name == JOB)
MALOS = ("stale", "missing", "corrupt", "undecryptable")


class SinkEspia:
    def __init__(self) -> None:
        self.recibidas: list[tuple[str, dict[str, object]]] = []

    def send(self, code: str, context: Mapping[str, object]) -> None:
        self.recibidas.append((code, dict(context)))


@pytest.fixture
def sink_espia() -> Iterator[SinkEspia]:
    foto = list(alerts._sinks)
    espia = SinkEspia()
    alerts._sinks[:] = [espia]
    try:
        yield espia
    finally:
        alerts._sinks[:] = foto


@pytest.fixture
def reloj() -> Iterator[FrozenClock]:
    reloj = FrozenClock(NOW)
    token = set_clock(reloj)
    try:
        yield reloj
    finally:
        reset_clock(token)


async def _correr(fabrica: Fabrica, reloj: FrozenClock) -> JobOutcome:
    return await run_job(SPEC, clock=reloj, session_factory=fabrica)


async def _fila(fabrica: Fabrica) -> JobRun:
    async with fabrica() as sesion:
        return (await sesion.scalars(select(JobRun).where(JobRun.job_name == JOB))).one()


def _sin_intentos(fila: JobRun) -> dict[str, Any]:
    return {k: v for k, v in fila.details.items() if k != "attempts"}


# Los seis estados --------------------------------------------------------------------------------


async def test_el_juego_de_las_siete_verificado_es_ok_con_details_enteros(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    juego = make_backup_dir(backup_dir, NOW, extra_sets=1)

    salida = await _correr(session_factory, reloj)

    fila = await _fila(session_factory)
    assert (salida.result, fila.result, fila.error) == ("ok", "ok", None)
    assert _sin_intentos(fila) == {
        "verificado": 1,
        "edad_horas": 5,
        "tamano_bytes": juego.total_bytes,
        "archivos": 2,
        "firma_verificada": 0,
    }
    assert set(fila.details) - {"attempts"} <= DETAIL_KEYS
    assert all(type(v) is int for k, v in fila.details.items() if k != "attempts")


async def test_verify_skipped_es_ok_unverified_y_sale_ok(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    make_backup_dir(backup_dir, NOW, verify="skipped")

    salida = await _correr(session_factory, reloj)

    fila = await _fila(session_factory)
    assert (salida.result, fila.result, fila.error) == ("ok_unverified", "ok_unverified", None)
    assert fila.details["verificado"] == 0
    assert fila.details["archivos"] == 1


async def test_el_juego_del_dia_anterior_es_stale(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    make_backup_dir(backup_dir, NOW, created_at=NOW - timedelta(hours=29))

    salida = await _correr(session_factory, reloj)

    fila = await _fila(session_factory)
    assert (salida.result, fila.result) == ("stale", "stale")
    assert fila.details["edad_horas"] == 29


async def test_directorio_vacio_es_missing(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    salida = await _correr(session_factory, reloj)

    fila = await _fila(session_factory)
    assert (salida.result, fila.result, fila.error) == ("missing", "missing", None)
    assert set(fila.details) - {"attempts"} <= DETAIL_KEYS


async def test_directorio_inexistente_es_missing_y_no_error(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    os.rmdir(backup_dir)

    salida = await _correr(session_factory, reloj)

    assert (salida.result, salida.error_type) == ("missing", None)


@pytest.mark.parametrize("tamper", ["sha256", "size", "name", "future"])
async def test_manifiesto_o_archivos_alterados_son_corrupt(
    tamper: str, session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    make_backup_dir(backup_dir, NOW, tamper=tamper)

    salida = await _correr(session_factory, reloj)

    assert (salida.result, (await _fila(session_factory)).result) == ("corrupt", "corrupt")


async def test_el_contenido_del_archivo_cambiado_tras_el_manifiesto_es_corrupt(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    juego = make_backup_dir(backup_dir, NOW)
    original = (backup_dir / juego.db_file).read_bytes()
    (backup_dir / juego.db_file).write_bytes(bytes(b ^ 1 for b in original))  # mismo tamaño

    salida = await _correr(session_factory, reloj)

    assert salida.result == "corrupt"


async def test_archivo_uploads_ausente_es_missing(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    make_backup_dir(backup_dir, NOW, tamper="missing_file")

    assert (await _correr(session_factory, reloj)).result == "missing"


async def test_archivo_db_ausente_es_missing(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    juego = make_backup_dir(backup_dir, NOW)
    (backup_dir / juego.db_file).unlink()

    assert (await _correr(session_factory, reloj)).result == "missing"


async def test_verify_failed_es_undecryptable(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    make_backup_dir(backup_dir, NOW, verify="failed")

    salida = await _correr(session_factory, reloj)

    assert (salida.result, (await _fila(session_factory)).result) == (
        "undecryptable",
        "undecryptable",
    )


async def test_la_prioridad_missing_gana_a_undecryptable(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    juego = make_backup_dir(backup_dir, NOW, verify="failed")
    (backup_dir / juego.uploads_file).unlink()

    assert (await _correr(session_factory, reloj)).result == "missing"


# El manifiesto es dato no confiable ---------------------------------------------------------------


@pytest.mark.parametrize("tamper", ["absolute", "dotdot"])
async def test_nombres_absolutos_o_con_dotdot_no_se_leen(
    tamper: str, session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    (backup_dir.parent / "fuera-db.dump.age").write_bytes(b"decoy")
    make_backup_dir(backup_dir, NOW, tamper=tamper)

    assert (await _correr(session_factory, reloj)).result == "missing"


async def test_latest_json_ilegible_o_roto_es_missing(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    (backup_dir / "latest.json").write_bytes(b"{no es json")

    assert (await _correr(session_factory, reloj)).result == "missing"


@pytest.mark.parametrize("prefijo", ["pre-deploy", "pre-restore"])
async def test_un_pre_deploy_o_pre_restore_no_vale_como_latest_json(
    prefijo: str, session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    make_backup_dir(backup_dir, NOW, prefix=prefijo)

    assert (await _correr(session_factory, reloj)).result == "missing"


async def test_latest_json_como_enlace_simbolico_no_se_sigue(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path, tmp_path: Path
) -> None:
    real = make_backup_dir(tmp_path / "otro", NOW)
    try:
        os.symlink(real.latest, backup_dir / "latest.json")
    except (OSError, NotImplementedError):
        pytest.skip("enlaces simbólicos sin privilegios en este equipo; corren en CI/Linux")

    assert (await _correr(session_factory, reloj)).result == "missing"


async def test_los_juegos_pre_no_cuentan_en_archivos(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    make_backup_dir(backup_dir, NOW, extra_sets=2, pre_sets=3)

    await _correr(session_factory, reloj)

    assert (await _fila(session_factory)).details["archivos"] == 3


# Reintento del mismo día ------------------------------------------------------------


async def test_la_segunda_corrida_del_dia_deja_dos_intentos(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    make_backup_dir(backup_dir, NOW)

    await _correr(session_factory, reloj)
    await _correr(session_factory, reloj)

    fila = await _fila(session_factory)
    assert fila.run_date == HOY
    assert len(fila.details["attempts"]) == 2
    assert [a["result"] for a in fila.details["attempts"]] == ["ok", "ok"]


# Alertas ------------------------------------------------------------------------------------------


def _preparar(estado: str, carpeta: Path) -> None:
    if estado == "stale":
        make_backup_dir(carpeta, NOW, created_at=NOW - timedelta(days=2))
    elif estado == "corrupt":
        make_backup_dir(carpeta, NOW, tamper="sha256")
    elif estado == "undecryptable":
        make_backup_dir(carpeta, NOW, verify="failed")
    # `missing`: carpeta vacía


@pytest.mark.parametrize("estado", MALOS)
async def test_un_estado_malo_avisa_backup_unhealthy_una_vez(
    estado: str,
    session_factory: Fabrica,
    reloj: FrozenClock,
    backup_dir: Path,
    sink_espia: SinkEspia,
) -> None:
    _preparar(estado, backup_dir)

    await _correr(session_factory, reloj)

    assert [c for c, _ in sink_espia.recibidas] == ["backup_unhealthy"]
    contexto = sink_espia.recibidas[0][1]
    assert set(contexto) <= ALERT_CONTEXT_KEYS
    assert (contexto["job"], contexto["result"]) == (JOB, estado)


@pytest.mark.parametrize("verify", ["ok", "skipped"])
async def test_ok_y_ok_unverified_no_avisan(
    verify: str,
    session_factory: Fabrica,
    reloj: FrozenClock,
    backup_dir: Path,
    sink_espia: SinkEspia,
) -> None:
    make_backup_dir(backup_dir, NOW, verify=verify)

    await _correr(session_factory, reloj)

    assert sink_espia.recibidas == []


async def _sembrar_racha(fabrica: Fabrica, resultados: list[str]) -> None:
    """Corridas de los días anteriores: `resultados[0]` es la de ayer, la siguiente la de antier."""
    async with fabrica() as sesion:
        for i, resultado in enumerate(resultados, start=1):
            inicio = NOW - timedelta(days=i)
            await make_job_run(
                sesion, JOB, HOY - timedelta(days=i), result=resultado, started_at=inicio
            )


async def test_siete_ok_unverified_seguidos_avisan(
    session_factory: Fabrica,
    reloj: FrozenClock,
    backup_dir: Path,
    sink_espia: SinkEspia,
) -> None:
    await _sembrar_racha(session_factory, ["ok_unverified"] * 6)
    make_backup_dir(backup_dir, NOW, verify="skipped")

    await _correr(session_factory, reloj)

    assert [(c, x["job"], x["result"]) for c, x in sink_espia.recibidas] == [
        ("backup_unhealthy", JOB, "ok_unverified")
    ]


async def test_seis_ok_unverified_seguidos_no_avisan(
    session_factory: Fabrica,
    reloj: FrozenClock,
    backup_dir: Path,
    sink_espia: SinkEspia,
) -> None:
    await _sembrar_racha(session_factory, ["ok_unverified"] * 5)
    make_backup_dir(backup_dir, NOW, verify="skipped")

    await _correr(session_factory, reloj)

    assert sink_espia.recibidas == []


async def test_una_corrida_ok_en_medio_corta_la_racha(
    session_factory: Fabrica,
    reloj: FrozenClock,
    backup_dir: Path,
    sink_espia: SinkEspia,
) -> None:
    await _sembrar_racha(
        session_factory, ["ok_unverified", "ok_unverified", "ok", "ok_unverified"] * 2
    )
    make_backup_dir(backup_dir, NOW, verify="skipped")

    await _correr(session_factory, reloj)

    assert sink_espia.recibidas == []


# Log sin ruta, sin upload_error y sin sha256 completo (S4B-D70) ----------------------------------


def _texto(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(r.getMessage() + " " + str(vars(r)) for r in caplog.records)


async def test_el_log_lleva_el_nombre_y_no_la_ruta_ni_upload_error_ni_el_sha_completo(
    session_factory: Fabrica,
    reloj: FrozenClock,
    backup_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    juego: BackupSet = make_backup_dir(
        backup_dir, NOW, upload="failed", upload_error="rclone: token-secreto-xyz"
    )
    caplog.set_level(logging.DEBUG)

    await _correr(session_factory, reloj)

    registros = [r for r in caplog.records if r.getMessage() == "backup_check finished"]
    assert len(registros) == 1
    texto = _texto(caplog)
    assert juego.name in str(vars(registros[0]))
    assert str(backup_dir) not in texto
    assert backup_dir.as_posix() not in texto
    assert "token-secreto-xyz" not in texto
    assert "upload_error" not in texto
    sha = juego.manifest["files"][0]["sha256"]
    assert sha not in texto


async def test_job_runs_no_guarda_nombres_ni_rutas(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    juego = make_backup_dir(backup_dir, NOW)

    await _correr(session_factory, reloj)

    fila = await _fila(session_factory)
    guardado = str(fila.details) + str(fila.error)
    assert juego.name not in guardado
    assert str(backup_dir) not in guardado


# El worker no abre age (S4B-D59) ------------------------------------------------------------------


async def test_el_job_no_abre_age_ni_lanza_procesos(
    session_factory: Fabrica,
    reloj: FrozenClock,
    backup_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    make_backup_dir(backup_dir, NOW)
    monkeypatch.setattr(archive, "AGE_BINARY", str(backup_dir / "no-existe" / "age"))

    def _prohibido(*_a: object, **_k: object) -> None:
        raise AssertionError("backup_check no debe lanzar procesos")

    monkeypatch.setattr(subprocess, "run", _prohibido)
    monkeypatch.setattr(subprocess, "Popen", _prohibido)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _prohibido)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", _prohibido)

    salida = await _correr(session_factory, reloj)

    assert (salida.result, salida.error_type) == ("ok", None)


# S4B-B2 (revisión de seguridad): FIFO, tope de archivos, unicidad, prefijo y tope de lectura -----

sin_fifo = pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="mkfifo no existe en Windows")


@sin_fifo
async def test_latest_json_como_fifo_es_missing_sin_colgar(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    fifo = backup_dir / "latest.json"
    os.mkfifo(fifo)
    liberador = threading.Timer(3, lambda: os.close(os.open(fifo, os.O_WRONLY)))
    liberador.start()
    try:
        inicio = time.perf_counter()
        salida = await _correr(session_factory, reloj)
        assert time.perf_counter() - inicio < 2
    finally:
        liberador.cancel()

    assert salida.result == "missing"


async def test_latest_json_como_directorio_es_missing(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    (backup_dir / "latest.json").mkdir()

    assert (await _correr(session_factory, reloj)).result == "missing"


@sin_fifo
async def test_un_archivo_del_juego_que_es_fifo_es_corrupt_sin_colgar(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    juego = make_backup_dir(backup_dir, NOW)
    (backup_dir / juego.uploads_file).unlink()
    os.mkfifo(backup_dir / juego.uploads_file)

    assert (await _correr(session_factory, reloj)).result == "corrupt"


async def test_un_archivo_del_juego_que_es_directorio_es_corrupt(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    juego = make_backup_dir(backup_dir, NOW)
    (backup_dir / juego.uploads_file).unlink()
    (backup_dir / juego.uploads_file).mkdir()

    assert (await _correr(session_factory, reloj)).result == "corrupt"


def _reescribir(juego: BackupSet, cambio: Any) -> None:
    datos = juego.manifest
    cambio(datos)
    (juego.folder / "latest.json").write_bytes(manifest_bytes(datos))


def _con_n_archivos(datos: dict[str, Any], total: int) -> None:
    base = datos["files"][0]
    datos["files"] = [{**base, "name": f"{datos['name']}-extra{i}.age"} for i in range(total)]


def test_max_files_es_8() -> None:
    assert MAX_FILES == 8


@pytest.mark.parametrize(("total", "esperado"), [(8, "missing"), (9, "corrupt")])
async def test_mas_de_ocho_archivos_es_corrupt(
    total: int, esperado: str, session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    """Con 8 archivos coherentes pero inexistentes sigue siendo `missing`: la regla es el tope."""
    juego = make_backup_dir(backup_dir, NOW)
    _reescribir(juego, lambda d: _con_n_archivos(d, total))

    assert (await _correr(session_factory, reloj)).result == esperado


async def test_nombres_de_archivo_repetidos_son_corrupt(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    juego = make_backup_dir(backup_dir, NOW)
    _reescribir(juego, lambda d: d["files"].append(dict(d["files"][0])))

    assert (await _correr(session_factory, reloj)).result == "corrupt"


async def test_un_archivo_que_no_empieza_por_el_nombre_del_juego_es_corrupt(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    juego = make_backup_dir(backup_dir, NOW)
    (backup_dir / "ajeno-db.dump.age").write_bytes((backup_dir / juego.db_file).read_bytes())
    _reescribir(juego, lambda d: d["files"][0].__setitem__("name", "ajeno-db.dump.age"))

    assert (await _correr(session_factory, reloj)).result == "corrupt"


async def test_el_hash_se_lee_con_tope_igual_al_tamano_declarado(
    session_factory: Fabrica,
    reloj: FrozenClock,
    backup_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    juego = make_backup_dir(backup_dir, NOW)
    topes: dict[str, int | None] = {}
    real = backup_check.digest_file

    def espia(ruta: Path, *args: Any, **kwargs: Any) -> str:
        topes[ruta.name] = kwargs.get("max_bytes")
        return real(ruta, *args, **kwargs)

    monkeypatch.setattr(backup_check, "digest_file", espia)

    assert (await _correr(session_factory, reloj)).result == "ok"
    assert topes == {juego.db_file: juego.db_size, juego.uploads_file: juego.uploads_size}


async def test_un_archivo_que_crecio_tras_el_manifiesto_es_corrupt(
    session_factory: Fabrica,
    reloj: FrozenClock,
    backup_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    make_backup_dir(backup_dir, NOW)

    def crecido(ruta: Path, *_a: Any, **_k: Any) -> str:
        raise OSError("archivo más grande que el declarado")

    monkeypatch.setattr(backup_check, "digest_file", crecido)

    assert (await _correr(session_factory, reloj)).result == "corrupt"


# S5-B13 (S5-D72, S5-D8): firma `minisign` verificada por el bus e instantánea de OpenBao
#
# Con `Settings.BACKUP_SIGN_PUBKEY` el job verifica `latest.json.minisig` por
# `bus.verify_signed_manifest`: firma ausente o inválida -> `corrupt`. Sin esa llave no hay con qué
# verificar y el job se comporta como antes (no degrada). `openbao_snapshot` es opcional: ausente
# no cambia nada; presente se comprueba como cualquier archivo del juego (`sha256` o tamaño
# malos -> `corrupt`, archivo ausente -> `missing`, nombre con `..` -> `missing` como el resto).

LLAVE_JOB = make_signing_key(31)


@pytest.fixture
def con_pubkey(
    backup_dir: Path, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> SigningKey:
    ajustes = settings_prueba.model_copy(
        update={"BACKUP_DIR": backup_dir, "BACKUP_SIGN_PUBKEY": LLAVE_JOB.pubkey}
    )
    monkeypatch.setattr(backup_check, "get_settings", lambda: ajustes)
    return LLAVE_JOB


async def test_con_pubkey_y_firma_valida_el_juego_es_ok(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path, con_pubkey: SigningKey
) -> None:
    make_backup_dir(backup_dir, NOW, sign=con_pubkey)

    salida = await _correr(session_factory, reloj)

    assert salida.result == "ok"


async def test_con_pubkey_una_firma_con_un_bit_cambiado_es_corrupt(
    session_factory: Fabrica,
    reloj: FrozenClock,
    backup_dir: Path,
    con_pubkey: SigningKey,
    sink_espia: SinkEspia,
) -> None:
    make_backup_dir(backup_dir, NOW, sign=con_pubkey, tamper="signature")

    salida = await _correr(session_factory, reloj)

    fila = await _fila(session_factory)
    assert (salida.result, fila.result) == ("corrupt", "corrupt")
    assert [c for c, _ in sink_espia.recibidas] == ["backup_unhealthy"]


async def test_con_pubkey_un_manifiesto_alterado_despues_de_firmar_es_corrupt(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path, con_pubkey: SigningKey
) -> None:
    juego = make_backup_dir(backup_dir, NOW, sign=con_pubkey)
    juego.latest.write_bytes(juego.latest.read_bytes() + b"\n")

    salida = await _correr(session_factory, reloj)

    assert salida.result == "corrupt"


async def test_con_pubkey_la_firma_de_otra_llave_es_corrupt(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path, con_pubkey: SigningKey
) -> None:
    make_backup_dir(backup_dir, NOW, sign=make_signing_key(32))

    salida = await _correr(session_factory, reloj)

    assert salida.result == "corrupt"


async def test_con_pubkey_sin_minisig_es_corrupt(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path, con_pubkey: SigningKey
) -> None:
    make_backup_dir(backup_dir, NOW)  # sin firma

    salida = await _correr(session_factory, reloj)

    assert salida.result == "corrupt"


async def test_con_pubkey_un_minisig_que_es_un_enlace_no_se_sigue(
    session_factory: Fabrica,
    reloj: FrozenClock,
    backup_dir: Path,
    con_pubkey: SigningKey,
    tmp_path: Path,
) -> None:
    make_backup_dir(backup_dir, NOW, sign=con_pubkey)
    real = tmp_path / "firma-real"
    real.write_bytes((backup_dir / "latest.json.minisig").read_bytes())
    (backup_dir / "latest.json.minisig").unlink()
    try:
        (backup_dir / "latest.json.minisig").symlink_to(real)
    except OSError:
        pytest.skip("enlaces simbólicos sin privilegios en este equipo; corren en CI/Linux")

    salida = await _correr(session_factory, reloj)

    assert salida.result == "corrupt"


async def test_sin_pubkey_configurada_el_job_no_verifica_la_firma_como_antes(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    make_backup_dir(backup_dir, NOW, sign=make_signing_key(33), tamper="signature")

    salida = await _correr(session_factory, reloj)

    assert salida.result == "ok"


async def test_sin_openbao_snapshot_no_se_degrada(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path, con_pubkey: SigningKey
) -> None:
    make_backup_dir(backup_dir, NOW, sign=con_pubkey, snapshot=False)

    assert (await _correr(session_factory, reloj)).result == "ok"


async def test_con_openbao_snapshot_correcto_es_ok(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path, con_pubkey: SigningKey
) -> None:
    juego = make_backup_dir(backup_dir, NOW, sign=con_pubkey, snapshot=True)

    salida = await _correr(session_factory, reloj)

    fila = await _fila(session_factory)
    assert (salida.result, fila.result, fila.error) == ("ok", "ok", None)
    assert set(fila.details) - {"attempts"} <= DETAIL_KEYS
    assert juego.manifest["openbao_snapshot"]["verified"] is True


async def test_openbao_snapshot_sin_firma_ni_pubkey_tambien_se_comprueba(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    make_backup_dir(backup_dir, NOW, snapshot=True, tamper="snapshot_sha256")

    assert (await _correr(session_factory, reloj)).result == "corrupt"


@pytest.mark.parametrize(
    ("tamper", "esperado"),
    [
        ("snapshot_sha256", "corrupt"),
        ("snapshot_size", "corrupt"),
        ("snapshot_missing", "missing"),
    ],
)
async def test_openbao_snapshot_con_defecto_degrada(
    session_factory: Fabrica,
    reloj: FrozenClock,
    backup_dir: Path,
    con_pubkey: SigningKey,
    sink_espia: SinkEspia,
    tamper: str,
    esperado: str,
) -> None:
    make_backup_dir(backup_dir, NOW, sign=con_pubkey, snapshot=True, tamper=tamper)

    salida = await _correr(session_factory, reloj)

    assert salida.result == esperado
    assert [c for c, _ in sink_espia.recibidas] == ["backup_unhealthy"]


async def test_openbao_snapshot_con_nombre_con_traversal_no_se_lee(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    juego = make_backup_dir(backup_dir, NOW, snapshot=True)
    datos = dict(juego.manifest)
    datos["openbao_snapshot"] = dict(datos["openbao_snapshot"], name="../fuera-openbao.snap.age")
    juego.latest.write_bytes(manifest_bytes(datos))

    assert (await _correr(session_factory, reloj)).result == "missing"


async def test_openbao_snapshot_con_forma_invalida_es_missing(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path
) -> None:
    juego = make_backup_dir(backup_dir, NOW, snapshot=True)
    datos = dict(juego.manifest)
    datos["openbao_snapshot"] = dict(datos["openbao_snapshot"], sha256="corto", extra=1)
    juego.latest.write_bytes(manifest_bytes(datos))

    assert (await _correr(session_factory, reloj)).result == "missing"


def test_parse_manifest_acepta_openbao_snapshot_opcional_y_lo_expone(tmp_path: Path) -> None:
    juego = make_backup_dir(tmp_path, NOW, snapshot=True)

    manifiesto = backup_check.parse_manifest(juego.latest.read_bytes())

    assert manifiesto is not None
    assert manifiesto.openbao_snapshot is not None
    assert manifiesto.openbao_snapshot.name == juego.manifest["openbao_snapshot"]["name"]
    sin = make_backup_dir(tmp_path / "sin", NOW)
    sin_manifiesto = backup_check.parse_manifest(sin.latest.read_bytes())
    assert sin_manifiesto is not None
    assert sin_manifiesto.openbao_snapshot is None


async def test_con_pubkey_el_manifiesto_se_abre_una_sola_vez_y_se_parsean_los_bytes_firmados(
    session_factory: Fabrica,
    reloj: FrozenClock,
    backup_dir: Path,
    con_pubkey: SigningKey,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S5-D178: no hay segunda lectura entre la firma y el uso (TOCTOU)."""
    from app.core.crypto import minisign

    make_backup_dir(backup_dir, NOW, sign=con_pubkey)
    latest = backup_dir / "latest.json"
    abiertos: list[Path] = []
    original = minisign._read_regular

    def espia(path: Path, limit: int) -> bytes | None:
        abiertos.append(path)
        return original(path, limit)

    monkeypatch.setattr(minisign, "_read_regular", espia)
    lecturas_directas: list[Path] = []
    leer = backup_check._leer_manifiesto
    monkeypatch.setattr(
        backup_check, "_leer_manifiesto", lambda c: lecturas_directas.append(c) or leer(c)
    )

    salida = await _correr(session_factory, reloj)

    assert salida.result == "ok"
    assert abiertos.count(latest) == 1
    assert lecturas_directas == []


async def test_con_pubkey_y_sin_latest_json_sigue_siendo_missing(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path, con_pubkey: SigningKey
) -> None:
    assert (await _correr(session_factory, reloj)).result == "missing"


async def test_con_pubkey_y_latest_json_ilegible_firmado_o_no_es_missing(
    session_factory: Fabrica, reloj: FrozenClock, backup_dir: Path, con_pubkey: SigningKey
) -> None:
    (backup_dir / "latest.json").write_bytes(b"{no es json")

    assert (await _correr(session_factory, reloj)).result == "missing"

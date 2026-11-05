"""Rojo B2 · `rotate_kek`, `rewrap_all`, `trim_ready`, `trim_kek` y la DEK en ceros de
`rotate_index` (S5-B2, paso 45; S5-D19, S5-D55a, S5-D151).

S5-D55a: `transit/rewrap` no conserva el AAD, así que el re-envuelto es `unwrap` + `wrap` por fila
(jamás `provider.rewrap`), con la versión nueva comprobada contra `latest_version` y la DEK
comparada ANTES de cualquier `UPDATE`. El recorte sube `min_decryption_version` por
`keys/apex-kek/config`; `transit/keys/.../trim` no se llama nunca.
"""

from __future__ import annotations

import os
import re
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.context import actor_scope
from app.core.crypto import service
from app.core.crypto.errors import CryptoError
from app.core.crypto.migration import MigrationInProgress, MigrationResult
from app.core.crypto.models import CryptoJob
from app.core.crypto.openbao_wire import parse_version
from app.core.crypto.provider import configure_provider
from app.core.crypto.rotation import (
    TrimNotReady,
    rewrap_all,
    rotate_kek,
    trim_kek,
    trim_kek_checked,
    trim_ready,
    trim_ready_version,
)
from app.core.crypto.service import RotationInProgress
from tests.crypto._migracion import (
    ACTOR,
    KEK_REF,
    Entorno,
    ProveedorEspia,
    Sembrada,
    TransitCorrupto,
    TransitVersionVieja,
    instantanea,
    jobs_de,
    llaves_envueltas,
    migrar_a_mano,
    todos_los_jobs,
    volver_a_envoltura,
)
from tests.crypto._rotacion import CLASE_ROTADA, blobs_de_rotacion, indices_de_rotacion
from tests.crypto._rotacion_flujo import MOTIVO

pytestmark = pytest.mark.usefixtures("reloj")

CODIGO = re.compile(r"^[a-z_]+$")


async def _con_kek_rotada(sembrada: Sembrada) -> Entorno:
    """Filas ya en OpenBao (v1) y la KEK de Transit rotada a v2."""
    await migrar_a_mano(sembrada.entorno)
    await sembrada.entorno.openbao.rotate(KEK_REF)
    return sembrada.entorno


async def _rewrapear(e: Entorno, **cambios: Any) -> MigrationResult:
    resolver = cambios.pop("resolver", None) or e.resolver()
    with actor_scope(ACTOR):
        return await rewrap_all(e.fabrica, resolver=resolver, actor=ACTOR)


async def _versiones(e: Entorno) -> list[int]:
    return [parse_version(bytes(f.wrapped_material)) for f in await llaves_envueltas(e.fabrica)]


# rotate_kek ------------------------------------------------------------------------------------


async def test_rotate_kek_devuelve_la_version_nueva_y_rota_transit(sembrada: Sembrada) -> None:
    e = sembrada.entorno
    assert e.transit.latest_version(KEK_REF) == 1

    assert await rotate_kek(e.openbao) == 2
    assert e.transit.latest_version(KEK_REF) == 2
    assert await rotate_kek(e.openbao) == 3


# rewrap_all ------------------------------------------------------------------------------------


async def test_rewrap_all_deja_cada_fila_en_la_ultima_version_con_la_misma_dek(
    sembrada: Sembrada,
) -> None:
    e = await _con_kek_rotada(sembrada)
    total = len(await llaves_envueltas(e.fabrica))
    assert set(await _versiones(e)) == {1}

    resultado = await _rewrapear(e)

    assert resultado == MigrationResult(total=total, done=total, skipped=0, failed_key_id=None)
    assert set(await _versiones(e)) == {e.transit.latest_version(KEK_REF)}
    for fila in await llaves_envueltas(e.fabrica):
        assert fila.provider == "openbao"
        assert await e.openbao.unwrap(bytes(fila.wrapped_material)) == sembrada.deks[fila.id]
    (job,) = await jobs_de(e.fabrica, "rewrap")
    assert (job.status, job.data_class, job.total, job.done) == ("done", None, total, total)


async def test_rewrap_all_deja_los_blobs_y_los_indices_intactos(sembrada: Sembrada) -> None:
    e = await _con_kek_rotada(sembrada)
    async with e.fabrica() as sesion:
        indices = await indices_de_rotacion(sesion)

    await _rewrapear(e)

    async with e.fabrica() as sesion:
        assert await blobs_de_rotacion(sesion) == sembrada.blobs
        assert await indices_de_rotacion(sesion) == indices


async def test_rewrap_all_usa_unwrap_mas_wrap_y_nunca_el_rewrap_de_transit(
    sembrada: Sembrada,
) -> None:
    e = await _con_kek_rotada(sembrada)
    total = len(await llaves_envueltas(e.fabrica))
    descifrados = len(e.transit.llamadas("/decrypt/"))
    cifrados = len(e.transit.llamadas("/encrypt/"))

    await _rewrapear(e)

    assert e.transit.llamadas("/rewrap/") == []
    assert len(e.transit.llamadas("/decrypt/")) - descifrados >= 2 * total  # viejo y verificación
    assert len(e.transit.llamadas("/encrypt/")) - cifrados == total


async def test_rewrap_all_no_escribe_si_la_dek_verificada_no_coincide(sembrada: Sembrada) -> None:
    e = sembrada.entorno.con_transit(TransitCorrupto())
    await migrar_a_mano(e)
    await e.openbao.rotate(KEK_REF)
    antes = await instantanea(e.fabrica)
    primera = (await llaves_envueltas(e.fabrica))[0]

    resultado = await _rewrapear(e)

    assert resultado.done == 0 and resultado.failed_key_id == primera.id
    assert await instantanea(e.fabrica) == antes
    (job,) = await jobs_de(e.fabrica, "rewrap")
    assert job.status == "failed" and job.error is not None and CODIGO.match(job.error)


async def test_rewrap_all_no_escribe_si_la_version_nueva_no_es_la_ultima(
    sembrada: Sembrada,
) -> None:
    e = sembrada.entorno.con_transit(TransitVersionVieja())
    await migrar_a_mano(e)
    await e.openbao.rotate(KEK_REF)
    antes = await instantanea(e.fabrica)

    resultado = await _rewrapear(e)

    assert resultado.done == 0 and resultado.failed_key_id is not None
    assert await instantanea(e.fabrica) == antes
    (job,) = await jobs_de(e.fabrica, "rewrap")
    assert job.status == "failed"


async def test_rewrap_all_se_reanuda_con_el_mismo_job_hasta_done_igual_a_total(
    sembrada: Sembrada,
) -> None:
    e = await _con_kek_rotada(sembrada)
    total = len(await llaves_envueltas(e.fabrica))
    caido = ProveedorEspia(e.openbao, fallar_wrap_en=3)

    primera = await _rewrapear(e, resolver=e.resolver(openbao=caido))

    assert (primera.total, primera.done) == (total, 2) and primera.failed_key_id is not None
    assert sorted(await _versiones(e)) == [1] * (total - 2) + [2] * 2
    (job,) = await jobs_de(e.fabrica, "rewrap")
    assert (job.status, job.done) == ("failed", 2)

    segunda = await _rewrapear(e)

    assert segunda == MigrationResult(total=total, done=total, skipped=0, failed_key_id=None)
    (mismo,) = await jobs_de(e.fabrica, "rewrap")
    assert (mismo.id, mismo.status) == (job.id, "done")
    assert set(await _versiones(e)) == {2}
    assert e.transit.latest_version(KEK_REF) == 2  # reanudar no rota otra vez


async def test_rewrap_all_sin_filas_viejas_no_cifra_nada(sembrada: Sembrada) -> None:
    e = await _con_kek_rotada(sembrada)
    await _rewrapear(e)
    cifrados = len(e.transit.llamadas("/encrypt/"))

    resultado = await _rewrapear(e)

    assert resultado == MigrationResult(total=0, done=0, skipped=0, failed_key_id=None)
    assert len(e.transit.llamadas("/encrypt/")) == cifrados


# trim_ready y trim_kek -------------------------------------------------------------------------


async def _listo(e: Entorno) -> bool:
    return await trim_ready(e.fabrica, resolver=e.resolver())


async def test_trim_ready_es_falso_si_nunca_se_re_envolvio(sembrada: Sembrada) -> None:
    e = await _con_kek_rotada(sembrada)

    assert await _listo(e) is False


async def test_trim_ready_es_falso_sin_rotacion_ni_job(sembrada: Sembrada) -> None:
    await migrar_a_mano(sembrada.entorno)

    assert await _listo(sembrada.entorno) is False


async def test_trim_ready_es_verdadero_con_todo_en_la_ultima_version_y_el_job_done(
    sembrada: Sembrada,
) -> None:
    e = await _con_kek_rotada(sembrada)
    await _rewrapear(e)

    assert await _listo(e) is True


async def test_trim_ready_es_falso_si_queda_una_fila_vieja(sembrada: Sembrada) -> None:
    e = await _con_kek_rotada(sembrada)
    vieja = (await llaves_envueltas(e.fabrica))[0]
    anterior = bytes(vieja.wrapped_material)
    await _rewrapear(e)
    assert await _listo(e) is True

    await volver_a_envoltura(e, vieja.id, anterior)

    assert await _listo(e) is False


async def test_trim_ready_es_falso_si_el_ultimo_job_rewrap_no_esta_en_done(
    sembrada: Sembrada,
) -> None:
    e = await _con_kek_rotada(sembrada)
    await _rewrapear(e)
    with actor_scope(ACTOR):
        async with e.fabrica() as sesion, sesion.begin():
            sesion.add(
                CryptoJob(kind="rewrap", data_class=None, status="running", created_by=ACTOR)
            )

    assert await _listo(e) is False


async def test_trim_ready_es_falso_tras_un_rewrap_a_medias(sembrada: Sembrada) -> None:
    e = await _con_kek_rotada(sembrada)
    await _rewrapear(e, resolver=e.resolver(openbao=ProveedorEspia(e.openbao, fallar_wrap_en=2)))

    assert await _listo(e) is False


async def test_trim_kek_sube_la_version_minima_y_las_envolturas_viejas_dejan_de_abrir(
    sembrada: Sembrada,
) -> None:
    e = await _con_kek_rotada(sembrada)
    vieja = (await llaves_envueltas(e.fabrica))[0]
    anterior = bytes(vieja.wrapped_material)
    await _rewrapear(e)

    assert await trim_kek(e.openbao) == 2

    assert e.transit.min_decryption_version[KEK_REF] == 2
    with pytest.raises(CryptoError):
        await e.openbao.unwrap(anterior)
    for fila in await llaves_envueltas(e.fabrica):
        assert await e.openbao.unwrap(bytes(fila.wrapped_material)) == sembrada.deks[fila.id]


async def test_ningun_camino_llama_a_trim_de_transit(sembrada: Sembrada) -> None:
    e = await _con_kek_rotada(sembrada)
    await _rewrapear(e)
    await _listo(e)
    await trim_kek(e.openbao)

    assert e.transit.llamadas("/trim") == []
    assert len(e.transit.llamadas("/config")) >= 1


# D151: rotate_index deja la DEK en ceros -------------------------------------------------------


async def test_rotate_index_pone_la_dek_en_ceros_al_terminar(sembrada: Sembrada) -> None:
    e = sembrada.entorno
    espia = ProveedorEspia(e.local)
    configure_provider(espia)
    try:
        with actor_scope(ACTOR):
            async with e.fabrica() as sesion, sesion.begin():
                filas = await service.rotate_index(sesion, CLASE_ROTADA, MOTIVO, ACTOR)
    finally:
        configure_provider(None)

    assert filas == 30
    assert len(espia.wrap_args) == 1
    dek = espia.wrap_args[0]
    assert isinstance(dek, bytearray), "la DEK de rotate_index debe vivir en un bytearray"
    assert any(espia.instantaneas[0]) and not any(dek)


# S5-D188: el recorte repite la comprobación bajo el candado `apex:rotate:kek` ------------------


async def _lista_para_recortar(sembrada: Sembrada) -> tuple[Entorno, int]:
    e = await _con_kek_rotada(sembrada)
    await _rewrapear(e)
    version = await trim_ready_version(e.fabrica, resolver=e.resolver())
    assert version == 2
    return e, version


async def test_trim_ready_version_devuelve_la_version_validada_o_none(
    sembrada: Sembrada,
) -> None:
    e = await _con_kek_rotada(sembrada)
    assert await trim_ready_version(e.fabrica, resolver=e.resolver()) is None

    await _rewrapear(e)

    assert await trim_ready_version(e.fabrica, resolver=e.resolver()) == 2


async def test_trim_checked_sube_la_version_validada(sembrada: Sembrada) -> None:
    e, version = await _lista_para_recortar(sembrada)

    assert await trim_kek_checked(e.fabrica, resolver=e.resolver(), version=version) == 2

    assert e.transit.min_decryption_version[KEK_REF] == 2


async def test_trim_checked_con_otra_rotacion_entre_la_comprobacion_y_el_recorte_no_llama_config(
    sembrada: Sembrada,
) -> None:
    e, version = await _lista_para_recortar(sembrada)
    await e.openbao.rotate(KEK_REF)  # otra rotación ocurre tras la comprobación (v3)

    with pytest.raises(TrimNotReady):
        await trim_kek_checked(e.fabrica, resolver=e.resolver(), version=version)

    assert e.transit.llamadas("/config") == []


async def test_trim_checked_con_una_fila_que_volvio_a_una_version_vieja_no_llama_config(
    sembrada: Sembrada,
) -> None:
    e = await _con_kek_rotada(sembrada)
    vieja = (await llaves_envueltas(e.fabrica))[0]
    anterior = bytes(vieja.wrapped_material)
    await _rewrapear(e)
    assert await trim_ready_version(e.fabrica, resolver=e.resolver()) == 2
    await volver_a_envoltura(e, vieja.id, anterior)

    with pytest.raises(TrimNotReady):
        await trim_kek_checked(e.fabrica, resolver=e.resolver(), version=2)

    assert e.transit.llamadas("/config") == []


async def test_trim_checked_con_el_candado_de_la_kek_tomado_lanza_rotationinprogress(
    sembrada: Sembrada, engine: AsyncEngine
) -> None:
    e, version = await _lista_para_recortar(sembrada)
    async with engine.connect() as conexion:
        clave = {"c": "apex:rotate:kek"}
        assert await conexion.scalar(text("SELECT pg_try_advisory_lock(hashtext(:c))"), clave)
        try:
            with pytest.raises(RotationInProgress):
                await trim_kek_checked(e.fabrica, resolver=e.resolver(), version=version)
        finally:
            await conexion.execute(text("SELECT pg_advisory_unlock(hashtext(:c))"), clave)

    assert e.transit.llamadas("/config") == []


# S5-D189 (L4): un rewrap sin filas viejas deja un job `done` con total 0 ------------------------


async def test_rewrap_all_sin_filas_viejas_deja_un_job_done_con_total_cero(
    sembrada: Sembrada,
) -> None:
    e = await _con_kek_rotada(sembrada)
    await _rewrapear(e)
    jobs = await todos_los_jobs(e.fabrica)

    resultado = await _rewrapear(e)

    assert resultado == MigrationResult(total=0, done=0, skipped=0, failed_key_id=None)
    assert await todos_los_jobs(e.fabrica) == jobs + 1
    ultimo = (await jobs_de(e.fabrica, "rewrap"))[-1]
    assert (ultimo.status, ultimo.total, ultimo.done) == ("done", 0, 0)
    assert await trim_ready(e.fabrica, resolver=e.resolver()) is True


# S5-D190: exclusión con la rotación de llaves de datos -----------------------------------------


@pytest.mark.parametrize("kind", ["migrate_provider", "rewrap"])
async def test_start_rotation_rechaza_si_hay_una_migracion_o_un_rewrap_abierto(
    sembrada: Sembrada, kind: str
) -> None:
    e = sembrada.entorno
    with actor_scope(ACTOR):
        async with e.fabrica() as sesion, sesion.begin():
            sesion.add(CryptoJob(kind=kind, data_class=None, status="running", created_by=ACTOR))
    llaves = await instantanea(e.fabrica)

    with pytest.raises(RotationInProgress):
        with actor_scope(ACTOR):
            async with e.fabrica() as sesion, sesion.begin():
                await service.start_rotation(sesion, CLASE_ROTADA, MOTIVO, ACTOR)

    assert await instantanea(e.fabrica) == llaves


@pytest.mark.parametrize("kind", ["rotate", "reencrypt"])
async def test_rewrap_rechaza_si_hay_una_rotacion_de_datos_abierta(
    sembrada: Sembrada, kind: str
) -> None:
    e = await _con_kek_rotada(sembrada)
    with actor_scope(ACTOR):
        async with e.fabrica() as sesion, sesion.begin():
            sesion.add(
                CryptoJob(
                    kind=kind, data_class="member.document", status="failed", created_by=ACTOR
                )
            )

    with pytest.raises(MigrationInProgress):
        await _rewrapear(e)


# OpenBao real (S5-D185): `config` con `min_decryption_version` recorta de verdad ----------------


@pytest.mark.openbao
async def test_real_set_min_decryption_version_deja_de_abrir_las_envolturas_viejas(
    openbao_real: Any,
) -> None:
    viejo = await openbao_real.wrap(os.urandom(32))
    info = await openbao_real.rotate(KEK_REF)

    await openbao_real.set_min_decryption_version(KEK_REF, info.version)

    with pytest.raises(CryptoError):
        await openbao_real.unwrap(viejo)
    nuevo = await openbao_real.wrap(os.urandom(32))
    assert parse_version(nuevo) == info.version
    assert (await openbao_real.key_info(KEK_REF)).version == info.version

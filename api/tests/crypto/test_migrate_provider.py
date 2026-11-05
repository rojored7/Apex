"""Rojo B2 · `migrate_provider` (S5-B2, paso 45; S5-D18, S5-D131).

Plan puro, migración reanudable con verificación previa al `UPDATE`, ceros en la DEK, un solo job
abierto, `--dry-run` sin escrituras y reversa `openbao -> local`. La base de pruebas es la de
`rotacion_lista` (llaves `local` reales, tabla de prueba con `document` cifrado); el destino es un
`OpenBaoProvider` sobre `FakeTransit`.

Decisión de contrato (S5-D183, corrige al Rojo): el plan NO incluye las filas `sign`; guardan una
referencia (S5-D9), no material envuelto con la KEK, así que no migran con ella. `verify_provider`
también cuenta solo `encrypt|index`.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.context import actor_scope
from app.core.crypto import migration as migration_mod
from app.core.crypto.keyring import Keyring, configure_keyring
from app.core.crypto.migration import (
    KeyRowView,
    MigrationInProgress,
    MigrationResult,
    migrate_provider,
    plan_provider_migration,
    verify_provider,
)
from app.core.crypto.models import CryptoJob, CryptoKey, CryptoOp
from tests.crypto._migracion import (
    ACTOR,
    Entorno,
    ProveedorEspia,
    Sembrada,
    TransitCorrupto,
    _actualizar,
    filas_de_llaves,
    instantanea,
    jobs_de,
    llaves_envueltas,
    migrar_a_mano,
    todos_los_jobs,
)
from tests.crypto._rotacion import cuenta_de_ops
from tests.crypto._rotacion_flujo import todo_se_lee

pytestmark = pytest.mark.usefixtures("reloj")

CODIGO = re.compile(r"^[a-z_]+$")


def _fila(
    purpose: str, clase: str, version: int, state: str = "active", provider: str = "local"
) -> KeyRowView:
    return KeyRowView(uuid4(), purpose, clase, version, state, provider)


# Plan puro -------------------------------------------------------------------------------------


def test_el_plan_incluye_active_decrypt_only_y_retired_de_encrypt_e_index() -> None:
    filas = [
        _fila("encrypt", "member.document", 3, "active"),
        _fila("encrypt", "member.document", 2, "decrypt_only"),
        _fila("encrypt", "member.document", 1, "retired"),
        _fila("index", "member.document", 2, "active"),
        _fila("index", "member.document", 1, "retired"),
    ]

    plan = plan_provider_migration(filas, "local")

    assert set(plan) == {f.id for f in filas}


def test_el_plan_excluye_las_filas_sign_por_s5_d183() -> None:
    firma = _fila("sign", "audit.log", 1)
    cifrado = _fila("encrypt", "member.document", 1)

    plan = plan_provider_migration([firma, cifrado], "local")

    assert plan == (cifrado.id,)


def test_el_plan_ordena_por_clase_proposito_y_version() -> None:
    desordenadas = [
        _fila("index", "member.phone", 1),
        _fila("encrypt", "member.phone", 2, "decrypt_only"),
        _fila("encrypt", "member.document", 1),
        _fila("encrypt", "member.phone", 1, "retired"),
        _fila("index", "member.document", 2),
        _fila("index", "member.document", 1, "decrypt_only"),
    ]
    esperado = tuple(
        f.id for f in sorted(desordenadas, key=lambda f: (f.data_class, f.purpose, f.version))
    )

    assert plan_provider_migration(desordenadas, "local") == esperado


def test_el_plan_solo_toma_las_filas_del_origen() -> None:
    en_local = _fila("encrypt", "member.document", 1, provider="local")
    en_openbao = _fila("encrypt", "member.phone", 1, provider="openbao")

    assert plan_provider_migration([en_local, en_openbao], "local") == (en_local.id,)
    assert plan_provider_migration([en_local, en_openbao], "openbao") == (en_openbao.id,)


def test_un_plan_sin_filas_del_origen_es_vacio() -> None:
    assert plan_provider_migration([], "local") == ()
    assert (
        plan_provider_migration(
            [_fila("encrypt", "member.document", 1, provider="openbao")], "local"
        )
        == ()
    )


# Migración -------------------------------------------------------------------------------------


async def _migrar(
    entorno: Entorno,
    *,
    de: str = "local",
    a: str = "openbao",
    dry_run: bool = False,
    **cambios: Any,
) -> MigrationResult:
    resolver = cambios.pop("resolver", None) or entorno.resolver()
    with actor_scope(ACTOR):
        return await migrate_provider(
            entorno.fabrica, from_=de, to=a, resolver=resolver, actor=ACTOR, dry_run=dry_run
        )


async def test_migra_todas_las_llaves_a_openbao_y_cierra_el_job(sembrada: Sembrada) -> None:
    e = sembrada.entorno
    total = len(await llaves_envueltas(e.fabrica))

    resultado = await _migrar(e)

    assert resultado == MigrationResult(total=total, done=total, skipped=0, failed_key_id=None)
    filas = await llaves_envueltas(e.fabrica)
    assert {f.provider for f in filas} == {"openbao"}
    assert all(bytes(f.wrapped_material).startswith(b"vault:v1:") for f in filas)
    (job,) = await jobs_de(e.fabrica, "migrate_provider")
    assert (job.status, job.data_class, job.total, job.done) == ("done", None, total, total)
    assert job.started_at is not None and job.finished_at is not None


async def test_la_dek_en_claro_no_cambia_con_la_migracion(sembrada: Sembrada) -> None:
    e = sembrada.entorno

    await _migrar(e)

    for fila in await llaves_envueltas(e.fabrica):
        assert await e.openbao.unwrap(bytes(fila.wrapped_material)) == sembrada.deks[fila.id]


async def test_los_blobs_cifrados_quedan_identicos_byte_a_byte(sembrada: Sembrada) -> None:
    from tests.crypto._rotacion import blobs_de_rotacion

    e = sembrada.entorno

    await _migrar(e)

    async with e.fabrica() as sesion:
        assert await blobs_de_rotacion(sesion) == sembrada.blobs


async def test_sin_la_kek_local_el_keyring_carga_y_todo_se_descifra(sembrada: Sembrada) -> None:
    e = sembrada.entorno
    await _migrar(e)

    async with e.fabrica() as sesion:
        keyring = Keyring()
        await keyring.load_all(sesion, e.resolver_sin_local())
        configure_keyring(keyring)
        await todo_se_lee(sesion, sembrada.ids, sembrada.blobs)


async def test_deja_unwrap_y_wrap_por_llave_con_el_batch_id_del_job(sembrada: Sembrada) -> None:
    e = sembrada.entorno
    esperadas = sorted(f.id for f in await llaves_envueltas(e.fabrica))

    await _migrar(e)

    (job,) = await jobs_de(e.fabrica, "migrate_provider")
    async with e.fabrica() as sesion:
        ops = (await sesion.scalars(select(CryptoOp).where(CryptoOp.batch_id == job.id))).all()
    assert sorted({o.key_id for o in ops if o.verb == "unwrap"}) == esperadas
    assert sorted({o.key_id for o in ops if o.verb == "wrap"}) == esperadas
    assert {o.user_id for o in ops} == {ACTOR}
    assert {o.result for o in ops} == {"ok"}


async def test_la_segunda_corrida_no_tiene_nada_que_migrar(sembrada: Sembrada) -> None:
    e = sembrada.entorno
    await _migrar(e)
    antes = await instantanea(e.fabrica)
    jobs = await todos_los_jobs(e.fabrica)
    async with e.fabrica() as sesion:
        ops = await cuenta_de_ops(sesion, "wrap")

    resultado = await _migrar(e)

    assert resultado == MigrationResult(total=0, done=0, skipped=0, failed_key_id=None)
    assert await instantanea(e.fabrica) == antes
    assert await todos_los_jobs(e.fabrica) == jobs
    async with e.fabrica() as sesion:
        assert await cuenta_de_ops(sesion, "wrap") == ops


async def test_una_interrupcion_a_la_mitad_se_reanuda_hasta_done_igual_a_total(
    sembrada: Sembrada,
) -> None:
    e = sembrada.entorno
    orden = [f.id for f in await llaves_envueltas(e.fabrica)]
    caido = ProveedorEspia(e.openbao, fallar_wrap_en=3)

    primera = await _migrar(e, resolver=e.resolver(openbao=caido))

    assert (primera.total, primera.done) == (len(orden), 2)
    assert primera.failed_key_id == orden[2]
    filas = await llaves_envueltas(e.fabrica)
    assert [f.provider for f in filas] == ["openbao"] * 2 + ["local"] * (len(orden) - 2)
    (job,) = await jobs_de(e.fabrica, "migrate_provider")
    assert (job.status, job.done, job.total) == ("failed", 2, len(orden))
    assert job.error is not None and CODIGO.match(job.error)

    segunda = await _migrar(e)

    assert segunda == MigrationResult(
        total=len(orden), done=len(orden), skipped=0, failed_key_id=None
    )
    (mismo,) = await jobs_de(e.fabrica, "migrate_provider")
    assert (mismo.id, mismo.status, mismo.done) == (job.id, "done", len(orden))
    assert {f.provider for f in await llaves_envueltas(e.fabrica)} == {"openbao"}


async def test_el_error_del_proveedor_queda_como_codigo_nunca_como_texto(
    sembrada: Sembrada,
) -> None:
    e = sembrada.entorno
    e.transit.responder("encrypt", 500, ["boom-secreto-del-proveedor"])

    resultado = await _migrar(e)

    assert resultado.done == 0 and resultado.failed_key_id is not None
    (job,) = await jobs_de(e.fabrica, "migrate_provider")
    assert job.status == "failed"
    assert job.error is not None and CODIGO.match(job.error)
    assert "boom" not in job.error


async def test_con_un_transit_corrupto_no_hay_update_porque_compare_digest_falla(
    sembrada: Sembrada,
) -> None:
    e = sembrada.entorno.con_transit(TransitCorrupto())
    antes = await instantanea(e.fabrica)
    primera = (await llaves_envueltas(e.fabrica))[0]

    resultado = await _migrar(e)

    assert resultado.done == 0 and resultado.failed_key_id == primera.id
    assert await instantanea(e.fabrica) == antes
    (job,) = await jobs_de(e.fabrica, "migrate_provider")
    assert job.status == "failed" and job.error is not None and CODIGO.match(job.error)


async def test_la_dek_se_pasa_a_wrap_como_bytearray_y_queda_en_ceros(sembrada: Sembrada) -> None:
    e = sembrada.entorno
    espia = ProveedorEspia(e.openbao)

    await _migrar(e, resolver=e.resolver(openbao=espia))

    assert len(espia.wrap_args) == len(await llaves_envueltas(e.fabrica))
    for objeto, copia in zip(espia.wrap_args, espia.instantaneas, strict=True):
        assert isinstance(objeto, bytearray)
        assert any(copia), "la DEK entregada a wrap no era la DEK"
        assert not any(objeto), "la DEK no quedó en ceros"


async def test_la_dek_queda_en_ceros_tambien_cuando_wrap_falla(sembrada: Sembrada) -> None:
    e = sembrada.entorno
    espia = ProveedorEspia(e.openbao, fallar_wrap_en=2)

    await _migrar(e, resolver=e.resolver(openbao=espia))

    assert len(espia.wrap_args) == 2
    assert all(isinstance(o, bytearray) and not any(o) for o in espia.wrap_args)


async def test_otro_job_abierto_impide_migrar_a_la_vez(sembrada: Sembrada) -> None:
    e = sembrada.entorno
    with actor_scope(ACTOR):
        async with e.fabrica() as sesion, sesion.begin():
            sesion.add(
                CryptoJob(kind="rewrap", data_class=None, status="running", created_by=ACTOR)
            )
    antes = await instantanea(e.fabrica)

    with pytest.raises(MigrationInProgress):
        await _migrar(e)

    assert await instantanea(e.fabrica) == antes
    assert await jobs_de(e.fabrica, "migrate_provider") == []


async def test_dry_run_no_escribe_nada(sembrada: Sembrada) -> None:
    e = sembrada.entorno
    total = len(await llaves_envueltas(e.fabrica))
    antes = await instantanea(e.fabrica)
    jobs = await todos_los_jobs(e.fabrica)
    async with e.fabrica() as sesion:
        ops = (await sesion.scalars(select(CryptoOp.id))).all()

    resultado = await _migrar(e, dry_run=True)

    assert resultado == MigrationResult(total=total, done=0, skipped=0, failed_key_id=None)
    assert await instantanea(e.fabrica) == antes
    assert await todos_los_jobs(e.fabrica) == jobs
    assert e.transit.llamadas("/encrypt/") == []
    async with e.fabrica() as sesion:
        assert (await sesion.scalars(select(CryptoOp.id))).all() == ops


async def test_la_reversa_openbao_a_local_funciona_con_el_mismo_codigo(sembrada: Sembrada) -> None:
    e = sembrada.entorno
    await migrar_a_mano(e)

    resultado = await _migrar(e, de="openbao", a="local")

    total = len(await llaves_envueltas(e.fabrica))
    assert resultado == MigrationResult(total=total, done=total, skipped=0, failed_key_id=None)
    for fila in await llaves_envueltas(e.fabrica):
        assert fila.provider == "local"
        assert not bytes(fila.wrapped_material).startswith(b"vault:")
        assert await e.local.unwrap(bytes(fila.wrapped_material)) == sembrada.deks[fila.id]
    (job,) = await jobs_de(e.fabrica, "migrate_provider")
    assert job.status == "done"


# verify_provider -------------------------------------------------------------------------------


async def test_verify_cuenta_las_filas_fuera_del_proveedor_esperado(sembrada: Sembrada) -> None:
    e = sembrada.entorno
    total = len(await llaves_envueltas(e.fabrica))

    assert await verify_provider(e.fabrica, expected="openbao") == total
    assert await verify_provider(e.fabrica, expected="local") == 0

    await migrar_a_mano(e)

    assert await verify_provider(e.fabrica, expected="openbao") == 0
    assert await verify_provider(e.fabrica, expected="local") == total


async def test_verify_ignora_las_filas_sign_que_guardan_una_referencia(sembrada: Sembrada) -> None:
    e = sembrada.entorno
    await migrar_a_mano(e)
    with actor_scope(ACTOR):
        async with e.fabrica() as sesion, sesion.begin():
            sesion.add(
                CryptoKey(
                    id=UUID(int=99),
                    purpose="sign",
                    data_class="audit.log",
                    algorithm="Ed25519",
                    provider="local",
                    version=1,
                    state="active",
                    wrapped_material=b"ed25519-ref",
                    created_by=ACTOR,
                )
            )

    assert await verify_provider(e.fabrica, expected="openbao") == 0
    assert len(await filas_de_llaves(e.fabrica)) > len(await llaves_envueltas(e.fabrica))


async def test_verify_no_escribe(sembrada: Sembrada) -> None:
    e = sembrada.entorno
    antes = await instantanea(e.fabrica)
    jobs = await todos_los_jobs(e.fabrica)

    await verify_provider(e.fabrica, expected="openbao")

    assert await instantanea(e.fabrica) == antes
    assert await todos_los_jobs(e.fabrica) == jobs


# S5-D189: reanudar un job `running`, no sostener el candado durante la red, DBAPIError ----------


class ProveedorQueCambiaLaFila(ProveedorEspia):
    """En su primera `wrap` otro proceso re-envuelve la fila (con una envoltura `local` nueva)."""

    def __init__(self, interno: Any, entorno: Entorno, fila: CryptoKey) -> None:
        super().__init__(interno)
        self._entorno, self._fila = entorno, fila
        self.cambiada: bytes | None = None

    async def wrap(self, dek: bytes | bytearray) -> bytes:
        if not self.wrap_args:
            dek_nueva = await self._entorno.local.wrap(bytes(dek))
            await _actualizar(self._entorno.fabrica, self._fila.id, "local", dek_nueva)
            self.cambiada = dek_nueva
        return await super().wrap(dek)


async def test_un_job_running_del_mismo_tipo_se_reanuda_no_bloquea(sembrada: Sembrada) -> None:
    e = sembrada.entorno
    total = len(await llaves_envueltas(e.fabrica))
    with actor_scope(ACTOR):
        async with e.fabrica() as sesion, sesion.begin():
            sesion.add(
                CryptoJob(
                    kind="migrate_provider",
                    data_class=None,
                    status="running",
                    total=total,
                    done=0,
                    created_by=ACTOR,
                )
            )

    resultado = await _migrar(e)

    assert resultado.done == total and resultado.failed_key_id is None
    (job,) = await jobs_de(e.fabrica, "migrate_provider")
    assert (job.status, job.done) == ("done", total)


async def test_una_excepcion_base_deja_el_job_failed_y_se_relanza(sembrada: Sembrada) -> None:
    e = sembrada.entorno

    class Abortado(BaseException):
        """Como una interrupción: no es `Exception`."""

    class Interrumpido(ProveedorEspia):
        async def wrap(self, dek: bytes | bytearray) -> bytes:
            raise Abortado

    with pytest.raises(Abortado):
        await _migrar(e, resolver=e.resolver(openbao=Interrumpido(e.openbao)))

    (job,) = await jobs_de(e.fabrica, "migrate_provider")
    assert job.status == "failed" and job.error is not None and CODIGO.match(job.error)


async def test_una_fila_cambiada_entre_la_lectura_y_el_update_se_salta_sin_escribir(
    sembrada: Sembrada,
) -> None:
    e = sembrada.entorno
    filas = await llaves_envueltas(e.fabrica)
    espia = ProveedorQueCambiaLaFila(e.openbao, e, filas[0])

    resultado = await _migrar(e, resolver=e.resolver(openbao=espia))

    assert resultado.skipped == 1 and resultado.failed_key_id is None
    despues = {f.id: f for f in await llaves_envueltas(e.fabrica)}
    assert despues[filas[0].id].provider == "local"
    assert bytes(despues[filas[0].id].wrapped_material) == espia.cambiada
    assert {f.provider for f in despues.values() if f.id != filas[0].id} == {"openbao"}

    segunda = await _migrar(e)  # la fila saltada se reevalúa en la corrida siguiente

    assert segunda.total == 1 and segunda.failed_key_id is None
    assert {f.provider for f in await llaves_envueltas(e.fabrica)} == {"openbao"}


async def test_no_hay_candado_de_fila_mientras_se_habla_con_el_proveedor(
    sembrada: Sembrada, engine: AsyncEngine
) -> None:
    """Durante `wrap` la fila no está bloqueada: otra conexión la bloquea con NOWAIT."""
    e = sembrada.entorno
    fila = (await llaves_envueltas(e.fabrica))[0]
    resultados: list[bool] = []

    class Sondeo(ProveedorEspia):
        async def wrap(self, dek: bytes | bytearray) -> bytes:
            if not self.wrap_args:
                async with engine.connect() as conexion:
                    try:
                        await conexion.execute(
                            text(
                                "SELECT 1 FROM crypto.crypto_keys WHERE id = :i FOR UPDATE NOWAIT"
                            ),
                            {"i": fila.id},
                        )
                        resultados.append(True)
                    except DBAPIError:
                        resultados.append(False)
            return await super().wrap(dek)

    await _migrar(e, resolver=e.resolver(openbao=Sondeo(e.openbao)))

    assert resultados == [True]


async def test_un_dbapierror_de_ocupada_deja_el_job_failed_con_codigo_busy(
    sembrada: Sembrada, monkeypatch: pytest.MonkeyPatch
) -> None:
    e = sembrada.entorno

    async def ocupada(*_a: Any, **_k: Any) -> bool:
        orig = type("Orig", (Exception,), {"sqlstate": "55P03"})()
        raise DBAPIError("SELECT 1", {}, orig)

    monkeypatch.setattr(migration_mod, "_una_llave", ocupada)

    resultado = await _migrar(e)

    assert resultado.error == "busy" and resultado.failed_key_id is not None
    (job,) = await jobs_de(e.fabrica, "migrate_provider")
    assert (job.status, job.error) == ("failed", "busy")


# S5-D190: exclusión con las rotaciones de llave de datos -----------------------------------------


@pytest.mark.parametrize("kind", ["rotate", "reencrypt"])
async def test_un_job_de_rotacion_abierto_impide_migrar(sembrada: Sembrada, kind: str) -> None:
    e = sembrada.entorno
    with actor_scope(ACTOR):
        async with e.fabrica() as sesion, sesion.begin():
            sesion.add(
                CryptoJob(
                    kind=kind,
                    data_class="member.document",
                    status="failed",
                    created_by=ACTOR,
                )
            )
    antes = await instantanea(e.fabrica)

    with pytest.raises(MigrationInProgress):
        await _migrar(e)

    assert await instantanea(e.fabrica) == antes
    assert await jobs_de(e.fabrica, "migrate_provider") == []

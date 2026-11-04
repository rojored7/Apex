"""Rotación de llave reanudable sobre 1.200 filas (S4B-B3b, US-030; S4B-D39, D40, D63).

`rotacion_lista` da el bus con commit real, la tabla de prueba y el registro apuntado a ella; las
pruebas hacen lo que hará el comando (`_rotacion_flujo.rotar`): iniciar, recifrar de a 500 y
cerrar. La llave anterior termina en `decrypt_only` (nunca `retired`; eso es `retire-key`).
La auditoría con el motivo la escribe el CLI (`tests/cli/test_rotate_key_cli.py`).
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.clock import FrozenClock
from app.core.crypto import bus
from app.core.crypto.errors import CryptoError
from app.core.crypto.models import CryptoJob
from app.core.crypto.service import start_rotation, validate_reason
from tests.crypto._rotacion import (
    CLASE_ROTADA,
    Fabrica,
    blobs_de_rotacion,
    filas_rotacion,
    llave_activa,
    llaves_de,
)
from tests.crypto._rotacion_flujo import (
    ACTOR,
    MOTIVO,
    cerrar,
    iniciar,
    job_de,
    leer,
    rotar,
    todo_se_lee,
    un_lote,
    vaciar_ops,
)

pytestmark = pytest.mark.usefixtures("reloj")

ANTERIOR = (
    "SELECT count(*) FROM test_crypto.crypto_test_person WHERE split_part(document, '.', 2) = :k"
)
ACTUALIZADAS = "SELECT id, updated_at FROM test_crypto.crypto_test_person ORDER BY id"


async def _con_llave(fabrica: Fabrica, key_id: object) -> int:
    async with fabrica() as sesion:
        return int(await sesion.scalar(text(ANTERIOR), {"k": str(key_id)}) or 0)


async def test_rotacion_completa_deja_v2_activa_y_v1_en_decrypt_only(
    rotacion_lista: Fabrica, reloj: FrozenClock
) -> None:
    async with rotacion_lista() as sesion:
        ids = await filas_rotacion(sesion)
        vieja = await llave_activa(sesion)

    corrida = await rotar(rotacion_lista)

    assert corrida.lotes == [500, 500, 200]
    assert corrida.cerrada is True
    job = await job_de(rotacion_lista, corrida.job_id)
    assert (job.kind, job.status, job.data_class) == ("rotate", "done", CLASE_ROTADA)
    assert (job.total, job.done) == (1200, 1200)
    assert job.finished_at is not None
    async with rotacion_lista() as sesion:
        v1, v2 = await llaves_de(sesion)
        assert (v1.version, v1.state) == (1, "decrypt_only")
        assert (v2.version, v2.state) == (2, "active")
        assert v1.id == vieja.id
        assert v1.rotated_by == ACTOR
        assert v1.rotated_at == reloj.now_utc()
        blobs = await blobs_de_rotacion(sesion)
        await todo_se_lee(sesion, ids, blobs)
        assert all(b.split(".")[1] == str(v2.id) for b in blobs.values())
    assert await _con_llave(rotacion_lista, v1.id) == 0


async def test_la_rotacion_nunca_deja_retired_a_la_llave_anterior(rotacion_lista: Fabrica) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 30)

    await rotar(rotacion_lista)

    async with rotacion_lista() as sesion:
        assert [k.state for k in await llaves_de(sesion)] == ["decrypt_only", "active"]


async def test_los_datos_se_leen_durante_el_recifrado(rotacion_lista: Fabrica) -> None:
    async with rotacion_lista() as sesion:
        ids = await filas_rotacion(sesion)
    job_id = await iniciar(rotacion_lista)

    assert await un_lote(rotacion_lista, job_id) == 500

    async with rotacion_lista() as sesion:
        blobs = await blobs_de_rotacion(sesion)
        await todo_se_lee(sesion, ids, blobs)
        v1, v2 = await llaves_de(sesion)
    assert {await _con_llave(rotacion_lista, v1.id), await _con_llave(rotacion_lista, v2.id)} == {
        700,
        500,
    }


async def test_interrumpida_tras_el_lote_1_se_reanuda_sin_version_3_ni_recifrar_lo_migrado(
    rotacion_lista: Fabrica,
) -> None:
    async with rotacion_lista() as sesion:
        ids = await filas_rotacion(sesion)
    primero = await iniciar(rotacion_lista)
    assert await un_lote(rotacion_lista, primero) == 500
    async with rotacion_lista() as sesion:
        nueva = str((await llaves_de(sesion))[1].id)
        migrados = {
            i: b for i, b in (await blobs_de_rotacion(sesion)).items() if b.split(".")[1] == nueva
        }
    assert len(migrados) == 500

    reanudado = await iniciar(rotacion_lista)  # "otro proceso" que repite el comando

    assert reanudado == primero
    async with rotacion_lista() as sesion:
        assert [k.version for k in await llaves_de(sesion)] == [1, 2]
    assert await un_lote(rotacion_lista, reanudado) == 500
    assert await un_lote(rotacion_lista, reanudado) == 200
    assert await cerrar(rotacion_lista, reanudado) is True
    async with rotacion_lista() as sesion:
        despues = await blobs_de_rotacion(sesion)
        await todo_se_lee(sesion, ids, despues)
        assert [k.version for k in await llaves_de(sesion)] == [1, 2]
    assert all(despues[i] == b for i, b in migrados.items()), "lo migrado se recifró de nuevo"


async def test_falla_inyectada_en_el_lote_2_deja_failed_y_repetir_reanuda_ese_job(
    rotacion_lista: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.crypto import service

    async with rotacion_lista() as sesion:
        ids = await filas_rotacion(sesion)
    job_id = await iniciar(rotacion_lista)
    original = bus.decrypt
    llamadas = 0

    def falla_en_el_lote_2(*args: object, **kwargs: object) -> bytes:
        nonlocal llamadas
        llamadas += 1
        if llamadas > 500:
            raise CryptoError("decrypt_failed", "falla inyectada")
        return original(*args, **kwargs)  # type: ignore[arg-type]

    with monkeypatch.context() as parche:
        parche.setattr(bus, "decrypt", falla_en_el_lote_2)
        assert await un_lote(rotacion_lista, job_id) == 500
        with pytest.raises(Exception):  # noqa: B017 - el tipo lo decide el Verde
            await un_lote(rotacion_lista, job_id)
    await service.fail_job(job_id, "decrypt_failed")

    job = await job_de(rotacion_lista, job_id)
    assert job.status == "failed"
    assert job.error == "decrypt_failed"
    assert job.done == 500
    async with rotacion_lista() as sesion:
        v1, v2 = await llaves_de(sesion)
        assert (v1.state, v2.state) == ("decrypt_only", "active")
        await todo_se_lee(sesion, ids, await blobs_de_rotacion(sesion))

    reanudado = await iniciar(rotacion_lista)
    assert reanudado == job_id, "repetir debe reanudar el job failed, no abrir otro"
    assert await un_lote(rotacion_lista, reanudado) == 500
    assert await un_lote(rotacion_lista, reanudado) == 200
    assert await cerrar(rotacion_lista, reanudado) is True
    async with rotacion_lista() as sesion:
        trabajos = await sesion.scalar(select(func.count()).select_from(CryptoJob))
        assert trabajos == 1
        assert [k.version for k in await llaves_de(sesion)] == [1, 2]
    assert (await job_de(rotacion_lista, job_id)).status == "done"


async def test_finish_rotation_no_cierra_si_quedan_filas_con_la_llave_anterior(
    rotacion_lista: Fabrica,
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 600)
    job_id = await iniciar(rotacion_lista)
    assert await un_lote(rotacion_lista, job_id) == 500

    assert await cerrar(rotacion_lista, job_id) is False

    assert (await job_de(rotacion_lista, job_id)).status != "done"


async def test_crypto_ops_deja_una_fila_rotate_y_filas_de_lote_con_count(
    rotacion_lista: Fabrica, engine: AsyncEngine
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion)
    await vaciar_ops(engine)

    await rotar(rotacion_lista)

    async with rotacion_lista() as sesion:
        filas = (
            await sesion.execute(
                text(
                    "SELECT verb, count, key_version FROM crypto.crypto_ops "
                    "WHERE data_class = :c AND verb IN ('rotate', 'encrypt', 'decrypt')"
                ),
                {"c": CLASE_ROTADA},
            )
        ).all()
    por_verbo: dict[str, list[tuple[int, int | None]]] = {}
    for verbo, cuenta, version in filas:
        por_verbo.setdefault(verbo, []).append((cuenta, version))
    assert len(por_verbo["rotate"]) == 1
    assert sum(c for c, _ in por_verbo["encrypt"]) == 1200
    assert all(v == 2 for _, v in por_verbo["encrypt"])
    assert len(por_verbo["encrypt"]) < 100, "las 1.200 operaciones se agrupan por lote"
    assert sum(c for c, _ in por_verbo["decrypt"]) == 1200


async def test_ninguna_fila_de_bitacora_ni_la_llave_repr_llevan_material(
    rotacion_lista: Fabrica, engine: AsyncEngine
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 20)
    await vaciar_ops(engine)
    await rotar(rotacion_lista)

    async with rotacion_lista() as sesion:
        volcado = str((await sesion.execute(text("SELECT * FROM crypto.crypto_ops"))).all())
        textos = [repr(k) for k in await llaves_de(sesion)]
        material = [bytes(k.wrapped_material) for k in await llaves_de(sesion)]
        job = repr((await sesion.execute(select(CryptoJob))).scalars().all())
    assert "apx1." not in volcado + job
    for m in material:
        assert m.hex() not in volcado + job + "".join(textos)
    assert all("wrapped_material" not in t for t in textos)


async def test_updated_at_de_las_filas_queda_intacto(rotacion_lista: Fabrica) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 700)
        antes = (await sesion.execute(text(ACTUALIZADAS))).all()

    await rotar(rotacion_lista)

    async with rotacion_lista() as sesion:
        despues = (await sesion.execute(text(ACTUALIZADAS))).all()
    assert despues == antes


async def test_rotar_otra_vez_tras_cerrar_crea_la_version_3(rotacion_lista: Fabrica) -> None:
    async with rotacion_lista() as sesion:
        ids = await filas_rotacion(sesion, 40)
    await rotar(rotacion_lista)

    segunda = await rotar(rotacion_lista, motivo="segunda rotación")

    assert segunda.lotes == [40]
    async with rotacion_lista() as sesion:
        llaves = await llaves_de(sesion)
        assert [(k.version, k.state) for k in llaves] == [
            (1, "decrypt_only"),
            (2, "decrypt_only"),
            (3, "active"),
        ]
        blobs = await blobs_de_rotacion(sesion)
        await todo_se_lee(sesion, ids, blobs)
        assert all(b.split(".")[1] == str(llaves[2].id) for b in blobs.values())
    assert leer(blobs[ids[0]], ids[0]) == "doc-00000"


# reason --------------------------------------------------------------------------------------

MOTIVOS_INVALIDOS = {
    "201 caracteres": "x" * 201,
    "salto de línea": "primera\nsegunda",
    "tabulador": "con\ttab",
    "carácter de control": "con\x00nulo",
    "correo": "por filtración de correo@x.y",
    "siete dígitos": "documento 1234567",
    "seis dígitos": "ticket 123456",
    "vacío": "",
    "solo espacios": "   ",
}


@pytest.mark.parametrize("motivo", list(MOTIVOS_INVALIDOS.values()), ids=list(MOTIVOS_INVALIDOS))
async def test_un_reason_invalido_lanza_value_error_antes_de_tocar_llaves(
    rotacion_lista: Fabrica, motivo: str
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 10)

    with pytest.raises(ValueError):
        async with rotacion_lista() as sesion, sesion.begin():
            await start_rotation(sesion, CLASE_ROTADA, motivo, ACTOR)

    async with rotacion_lista() as sesion:
        assert [(k.version, k.state) for k in await llaves_de(sesion)] == [(1, "active")]
        assert await sesion.scalar(select(func.count()).select_from(CryptoJob)) == 0


@pytest.mark.parametrize(
    "motivo",
    [MOTIVO, "x" * 200, "ticket 12345", "rotación 2026-Q4"],
)
def test_un_reason_valido_se_acepta(motivo: str) -> None:
    assert validate_reason(motivo) == motivo.strip()


@pytest.mark.parametrize("motivo", list(MOTIVOS_INVALIDOS.values()), ids=list(MOTIVOS_INVALIDOS))
def test_validate_reason_rechaza_lo_que_start_rotation_rechaza(motivo: str) -> None:
    with pytest.raises(ValueError):
        validate_reason(motivo)

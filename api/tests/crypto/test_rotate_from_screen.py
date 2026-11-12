"""`POST /crypto/keys/{id}/rotate` (S6-R1, US-145; S6-D43, S6-D61, S6-D69, E5, E7). Rojo R1.

La app real con commit real (`pantalla`), 1.200 filas cifradas con `member.document` (modelo de
`rotacion_lista`) y la puerta de lotes (`puerta`) para observar la rotación entre lote y lote.

Contratos que el Rojo asume (el Verde puede discutirlos con una nota numerada):
- el `POST` confirma la transacción ANTES de lanzar la tarea, y la deja en
  `app.state.rotation_task`; `run_rotation` y `resume_running_jobs` llaman a
  `service.reencrypt_batch` por atributo de módulo;
- la fila de auditoría `update` sobre `crypto.crypto_keys` la escribe el router por la puerta
  `set_audit_writer` en la MISMA transacción, con `record_id` = la llave del camino,
  `after = {reason, data_class, state}` y nunca material ni referencias;
- repetir el `POST` sobre la llave `active` de una clase con un job `failed` reanuda ese job
  (no crea otra versión); `rotation_running` es solo para un job `pending` o `running` o un
  rotador en vuelo en el proceso (`ROTATION_SLOTS`).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text

from app.core.clock import FrozenClock
from app.core.crypto import reencryptor, rotate_job
from app.core.crypto.errors import CryptoError, CryptoUnavailable
from app.core.crypto.keyring import configure_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.registry import DataClassSpec, override_registry
from tests.conftest import CLAVE_PRUEBA
from tests.crypto._rotacion import (
    CLASE_ROTADA,
    blobs_de_rotacion,
    filas_rotacion,
    llave_activa,
    llaves_de,
    registro_de_rotacion,
)
from tests.crypto._rotacion_flujo import todo_se_lee, vaciar_ops
from tests.crypto._rotacion_pantalla import Pantalla, PuertaDeLotes
from tests.crypto.conftest import CLASE_FIRMA, fila_sign

pytestmark = pytest.mark.usefixtures("reloj")

LOTES = [500, 500, 200]
JOB_FALLIDO = "batch_failed"


async def _sembrar(pantalla: Pantalla) -> tuple[list[Any], Any]:
    async with pantalla.fabrica() as sesion:
        ids = await filas_rotacion(sesion)
        activa = (await llave_activa(sesion)).id
    return ids, activa


async def _blobs(pantalla: Pantalla) -> dict[Any, str]:
    async with pantalla.fabrica() as sesion:
        return await blobs_de_rotacion(sesion)


async def _lotes_de_ops(pantalla: Pantalla, verbo: str) -> list[int]:
    async with pantalla.fabrica() as sesion:
        filas = await sesion.execute(
            text(
                "SELECT batch_id, sum(count) AS n FROM crypto.crypto_ops WHERE verb = :v "
                "AND data_class = :c AND batch_id IS NOT NULL GROUP BY batch_id"
            ),
            {"v": verbo, "c": CLASE_ROTADA},
        )
        return sorted(int(f.n) for f in filas.all())


# 202 y transacción inicial ---


async def test_el_post_responde_202_con_los_tres_ids_y_deja_todo_en_la_misma_transaccion(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    _, vieja = await _sembrar(pantalla)
    await vaciar_ops(pantalla.engine)

    r = await pantalla.rotar(vieja)

    assert r.status_code == 202, r.text
    cuerpo = r.json()
    assert set(cuerpo) == {"job_id", "new_key_id", "previous_key_id"}
    assert cuerpo["previous_key_id"] == str(vieja)
    await puerta.llega()  # la rotación espera ANTES del primer lote: nada se recifró aún
    llaves = await pantalla.llaves()
    assert [(k.version, k.state) for k in llaves] == [(1, "decrypt_only"), (2, "active")]
    assert cuerpo["new_key_id"] == str(llaves[1].id)
    job = await pantalla.job(cuerpo["job_id"])
    assert (job.kind, job.data_class, job.status, job.total, job.done) == (
        "rotate",
        CLASE_ROTADA,
        "running",
        1200,
        0,
    )
    fila = await pantalla.filas_de_auditoria()
    assert [(f["action"], str(f["record_id"])) for f in fila] == [("update", str(vieja))]
    despues = fila[0]["after"]
    assert {"reason", "data_class", "state"} <= set(despues)
    assert despues["reason"] == "sospecha" and despues["data_class"] == CLASE_ROTADA
    assert despues["state"] == "decrypt_only"
    puerta.abrir()
    await pantalla.terminar()


async def test_la_auditoria_no_lleva_material_ni_referencias_y_es_una_sola_fila(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    _, vieja = await _sembrar(pantalla)
    puerta.abrir()

    r = await pantalla.rotar(vieja)
    await pantalla.terminar()

    assert r.status_code == 202, r.text
    filas = await pantalla.filas_de_auditoria()
    assert len(filas) == 1
    texto = str(filas[0])
    for prohibido in ("wrapped_material", "vault:", "apex-sign-audit", "apxw1", "apx1."):
        assert prohibido not in texto, prohibido


# Lectura y progreso durante el recifrado ---


async def test_durante_el_recifrado_las_filas_viejas_y_nuevas_se_descifran_y_percent_crece(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    ids, vieja = await _sembrar(pantalla)
    r = await pantalla.rotar(vieja)
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    porcentajes: list[int] = []

    for numero in (1, 2, 3):
        assert await puerta.llega() == numero
        (job,) = await pantalla.jobs(data_class=CLASE_ROTADA)
        assert job["id"] == job_id and job["status"] == "running"
        porcentajes.append(job["percent"])
        if numero == 2:  # a mitad de camino: 500 filas con la llave nueva y 700 con la vieja
            blobs = await _blobs(pantalla)
            nueva = str((await pantalla.llaves())[1].id)
            assert sum(1 for b in blobs.values() if b.split(".")[1] == nueva) == 500
            async with pantalla.fabrica() as sesion:
                await todo_se_lee(sesion, ids, blobs)
        puerta.pasa()
    await pantalla.terminar()

    (job,) = await pantalla.jobs(data_class=CLASE_ROTADA)
    porcentajes.append(job["percent"])
    assert porcentajes == [0, 41, 83, 100]
    assert job["status"] == "done"


async def test_al_terminar_el_job_esta_done_sin_pendientes_y_en_tres_lotes_de_500(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    ids, vieja = await _sembrar(pantalla)
    await vaciar_ops(pantalla.engine)
    puerta.abrir()

    r = await pantalla.rotar(vieja)
    await pantalla.terminar()

    job = await pantalla.job(r.json()["job_id"])
    assert (job.status, job.done, job.total, job.error) == ("done", 1200, 1200, None)
    assert job.finished_at is not None
    llaves = await pantalla.llaves()
    assert [(k.version, k.state) for k in llaves] == [(1, "decrypt_only"), (2, "active")]
    blobs = await _blobs(pantalla)
    assert {b.split(".")[1] for b in blobs.values()} == {str(llaves[1].id)}
    async with pantalla.fabrica() as sesion:
        await todo_se_lee(sesion, ids, blobs)
    assert await _lotes_de_ops(pantalla, "encrypt") == sorted(LOTES)
    assert await _lotes_de_ops(pantalla, "decrypt") == sorted(LOTES)


# 409 ---


async def test_409_key_not_active_para_una_llave_decrypt_only(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    _, vieja = await _sembrar(pantalla)
    puerta.abrir()
    assert (await pantalla.rotar(vieja)).status_code == 202
    await pantalla.terminar()

    r = await pantalla.rotar(vieja)

    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "key_not_active"
    assert len(await pantalla.llaves()) == 2


async def test_409_purpose_not_rotatable_para_index_y_sign(
    pantalla: Pantalla, proveedor_local: LocalFileProvider
) -> None:
    async with pantalla.fabrica() as sesion, sesion.begin():
        firma = await fila_sign(sesion, proveedor_local, CLASE_FIRMA)
        firma_id = firma.id
        indice = (await llaves_de(sesion, "index", CLASE_ROTADA))[0].id

    for llave in (indice, firma_id):
        r = await pantalla.rotar(llave)
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "purpose_not_rotatable"
    async with pantalla.fabrica() as sesion:
        assert len(await llaves_de(sesion, "index", CLASE_ROTADA)) == 1
    assert await pantalla.jobs() == []


async def test_409_rotation_running_con_un_job_abierto_de_la_clase(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    _, vieja = await _sembrar(pantalla)
    primero = await pantalla.rotar(vieja)
    assert primero.status_code == 202, primero.text
    await puerta.llega()

    r = await pantalla.rotar(primero.json()["new_key_id"])

    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "rotation_running"
    assert len(await pantalla.llaves()) == 2
    puerta.abrir()
    await pantalla.terminar()


async def test_409_rotation_running_con_el_rotador_ocupado_por_otra_clase(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    """`ROTATION_SLOTS = 1`: mientras `member.document` rota, un `POST` de cualquier otra clase
    responde 409 sin crear llave ni job."""
    assert rotate_job.ROTATION_SLOTS == 1
    _, vieja = await _sembrar(pantalla)
    assert (await pantalla.rotar(vieja)).status_code == 202
    await puerta.llega()
    async with pantalla.fabrica() as sesion:
        telefono = (await llaves_de(sesion, "encrypt", "member.phone"))[0].id

    r = await pantalla.rotar(telefono)

    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "rotation_running"
    async with pantalla.fabrica() as sesion:
        assert len(await llaves_de(sesion, "encrypt", "member.phone")) == 1
    puerta.abrir()
    await pantalla.terminar()


async def test_409_rotation_not_supported_para_una_clase_sin_columnas_ni_puerto(
    pantalla: Pantalla, proveedor_local: LocalFileProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    clase = DataClassSpec("attachment.sensitive", True, None, False, "str", ())
    monkeypatch.setattr(reencryptor, "_registered", {})  # la app registró el puerto real
    with override_registry({**registro_de_rotacion(), clase.name: clase}):
        async with pantalla.fabrica() as sesion, sesion.begin():
            from app.core.context import SYSTEM_USER_ID, actor_scope
            from app.core.crypto.bootstrap import ensure_keys

            with actor_scope(SYSTEM_USER_ID):
                await ensure_keys(sesion, proveedor_local, lambda _n: proveedor_local)
        async with pantalla.fabrica() as sesion:
            llave = (await llaves_de(sesion, "encrypt", clase.name))[0].id

        r = await pantalla.rotar(llave)

    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "rotation_not_supported"
    assert await pantalla.jobs() == []


# 404, 422, 429, 503 ---


async def test_404_para_una_llave_inexistente(pantalla: Pantalla) -> None:
    r = await pantalla.rotar("00000000-0000-0000-0000-00000000dead")

    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] in {"not_found", "key_not_found"}


@pytest.mark.parametrize(
    ("cuerpo", "campo"),
    [
        ({"reason": "sospecha", "confirm": "rotar"}, "confirm"),
        ({"reason": "sospecha", "confirm": " ROTAR"}, "confirm"),
        ({"reason": "sospecha", "confirm": "ROTAR "}, "confirm"),
        ({"reason": "sospecha", "confirm": ""}, "confirm"),
        ({"reason": "", "confirm": "ROTAR"}, "reason"),
        ({"reason": "   ", "confirm": "ROTAR"}, "reason"),
        ({"reason": "x" * 201, "confirm": "ROTAR"}, "reason"),
        ({"reason": "escribió a ana@correo.test", "confirm": "ROTAR"}, "reason"),
        ({"reason": "cédula 1234567890", "confirm": "ROTAR"}, "reason"),
    ],
    ids=[
        "minusculas",
        "espacio_antes",
        "espacio_despues",
        "vacio",
        "reason_vacio",
        "blancos",
        "201",
        "con_correo",
        "con_numero_largo",
    ],
)
async def test_422_con_el_campo_que_falla_y_sin_tocar_llaves(
    pantalla: Pantalla, cuerpo: dict[str, str], campo: str
) -> None:
    _, vieja = await _sembrar(pantalla)

    r = await pantalla.rotar(vieja, cuerpo=cuerpo)

    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert error["code"] == "validation_error" and error["field"] == campo
    assert cuerpo["confirm"] not in error["message"] or cuerpo["confirm"] == ""
    assert [(k.version, k.state) for k in await pantalla.llaves()] == [(1, "active")]
    assert await pantalla.jobs() == []


async def test_422_con_campos_extra_o_faltantes(pantalla: Pantalla) -> None:
    _, vieja = await _sembrar(pantalla)
    for cuerpo in ({"reason": "x"}, {"reason": "x", "confirm": "ROTAR", "algoritmo": "x"}):
        r = await pantalla.rotar(vieja, cuerpo=cuerpo)
        assert r.status_code == 422, (cuerpo, r.text)


async def test_un_motivo_de_200_caracteres_se_acepta(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    _, vieja = await _sembrar(pantalla)
    puerta.abrir()

    r = await pantalla.rotar(vieja, reason="m" * 200)  # S6-D122: tope 200, como el CLI
    await pantalla.terminar()

    assert r.status_code == 202, r.text


@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_solo_el_admin_rota(pantalla: Pantalla, rol: str) -> None:
    _, vieja = await _sembrar(pantalla)
    # `usuario_real` usa la sesión de savepoint; aquí hace falta uno con commit real.
    from app.core.security import create_access_token
    from tests.conftest import UsuarioPrueba
    from tests.factories.users import make_user

    async with pantalla.fabrica() as sesion:
        otro = await make_user(sesion, role=rol, password=CLAVE_PRUEBA)
    token = create_access_token(otro.id, rol, otro.member_id, _reloj())
    quien = UsuarioPrueba(otro, otro.id, otro.email, rol, "", token)

    r = await pantalla.rotar(vieja, usuario=quien)

    assert r.status_code == 403, r.text
    assert [(k.version, k.state) for k in await pantalla.llaves()] == [(1, "active")]


def _reloj() -> Any:
    from app.core.clock import current_clock

    return current_clock()


async def test_sin_token_401(pantalla: Pantalla) -> None:
    _, vieja = await _sembrar(pantalla)
    r = await pantalla.http.post(
        f"/api/v1/crypto/keys/{vieja}/rotate", json={"reason": "x", "confirm": "ROTAR"}
    )
    assert r.status_code == 401, r.text


async def test_503_crypto_unavailable_si_el_custodio_no_envuelve_y_no_queda_nada(
    pantalla: Pantalla, proveedor_local: LocalFileProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, vieja = await _sembrar(pantalla)

    async def sellado(_dek: Any) -> bytes:
        raise CryptoUnavailable("sealed", "http://openbao:8200 s.secreto")

    monkeypatch.setattr(proveedor_local, "wrap", sellado)

    r = await pantalla.rotar(vieja)

    assert r.status_code == 503, r.text
    assert r.json()["error"]["code"] == "crypto_unavailable"
    assert "openbao" not in r.text and "secreto" not in r.text
    assert [(k.version, k.state) for k in await pantalla.llaves()] == [(1, "active")]
    assert await pantalla.jobs() == []
    assert await pantalla.filas_de_auditoria() == []


async def test_el_cuarto_post_del_minuto_da_429_en_keys_rotate(pantalla: Pantalla) -> None:
    fantasma = "00000000-0000-0000-0000-00000000dead"
    for numero in range(3):
        r = await pantalla.rotar(fantasma)
        assert r.status_code == 404, (numero, r.text)

    r = await pantalla.rotar(fantasma)

    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1


# Fallos, reanudación y tiempo máximo ---


async def test_un_error_de_lote_deja_failed_con_un_codigo_y_la_anterior_en_decrypt_only(
    pantalla: Pantalla, puerta: PuertaDeLotes, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, vieja = await _sembrar(pantalla)
    real = puerta.real

    async def falla_en_el_segundo(session: Any, job: Any, tamano: int = 500) -> int:
        if puerta.contador == 2:
            raise CryptoError("decrypt_failed", "detalle interno con material@secreto.test")
        return int(await real(session, job, tamano))

    puerta.real = falla_en_el_segundo
    puerta.abrir()

    r = await pantalla.rotar(vieja)
    await pantalla.terminar()

    job = await pantalla.job(r.json()["job_id"])
    assert job.status == "failed"
    assert job.error and len(job.error) <= 100 and "secreto" not in job.error
    assert job.done == 500
    assert [(k.version, k.state) for k in await pantalla.llaves()] == [
        (1, "decrypt_only"),
        (2, "active"),
    ]
    (listado,) = await pantalla.jobs(data_class=CLASE_ROTADA)
    assert listado["status"] == "failed" and "error" not in listado


async def test_repetir_el_post_sobre_la_activa_reanuda_el_job_fallido(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    ids, vieja = await _sembrar(pantalla)
    real = puerta.real
    fallos = {"restan": 1}

    async def falla_una_vez(session: Any, job: Any, tamano: int = 500) -> int:
        if puerta.contador == 2 and fallos["restan"]:
            fallos["restan"] -= 1
            raise CryptoError("decrypt_failed", "x")
        return int(await real(session, job, tamano))

    puerta.real = falla_una_vez
    puerta.abrir()
    primero = await pantalla.rotar(vieja)
    await pantalla.terminar()
    assert (await pantalla.job(primero.json()["job_id"])).status == "failed"
    activa = primero.json()["new_key_id"]

    r = await pantalla.rotar(activa)
    await pantalla.terminar()

    assert r.status_code == 202, r.text
    assert r.json() == {
        "job_id": primero.json()["job_id"],
        "new_key_id": activa,
        "previous_key_id": str(vieja),
    }
    job = await pantalla.job(primero.json()["job_id"])
    assert (job.status, job.done, job.total) == ("done", 1200, 1200)
    assert len(await pantalla.llaves()) == 2  # no nació una versión 3
    async with pantalla.fabrica() as sesion:
        await todo_se_lee(sesion, ids, await blobs_de_rotacion(sesion))


async def test_pasar_de_rotation_max_s_deja_failed_con_timeout(
    pantalla: Pantalla, puerta: PuertaDeLotes, reloj: FrozenClock
) -> None:
    assert rotate_job.ROTATION_MAX_S == 3600
    _, vieja = await _sembrar(pantalla)
    real = puerta.real

    async def lento(session: Any, job: Any, tamano: int = 500) -> int:
        hechas = int(await real(session, job, tamano))
        reloj.advance(hours=1, minutes=1)  # el reloj inyectado: pasó más de ROTATION_MAX_S
        return hechas

    puerta.real = lento
    puerta.abrir()

    r = await pantalla.rotar(vieja)
    await pantalla.terminar()

    job = await pantalla.job(r.json()["job_id"])
    assert (job.status, job.error) == ("failed", "timeout")
    assert 0 < job.done < job.total
    assert reloj.now_utc() - job.started_at > timedelta(seconds=rotate_job.ROTATION_MAX_S)


# Reinicio: resume_running_jobs ---


async def _job_huerfano(pantalla: Pantalla) -> tuple[Any, list[Any]]:
    """Un job `running` con la llave ya rotada y NADA recifrado (el api murió tras el `POST`)."""
    from app.core.context import actor_scope
    from app.core.crypto import inventory

    ids, vieja = await _sembrar(pantalla)
    async with pantalla.fabrica() as sesion:
        with actor_scope(pantalla.admin.id):
            async with sesion.begin():
                inicio = await inventory.start_from_screen(
                    sesion, vieja, reason=MOTIVO_HUERFANO, by=pantalla.admin.id
                )
    return inicio, ids


MOTIVO_HUERFANO = "reinicio"


async def test_resume_running_jobs_termina_el_job_si_el_keyring_esta_cargado(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    inicio, ids = await _job_huerfano(pantalla)
    puerta.abrir()
    assert (await pantalla.job(inicio.job_id)).status == "running"

    await rotate_job.resume_running_jobs(pantalla.fabrica)

    job = await pantalla.job(inicio.job_id)
    assert (job.status, job.done, job.total) == ("done", 1200, 1200)
    blobs = await _blobs(pantalla)
    assert {b.split(".")[1] for b in blobs.values()} == {str(inicio.new_key_id)}
    async with pantalla.fabrica() as sesion:
        await todo_se_lee(sesion, ids, blobs)


async def test_resume_running_jobs_sin_keyring_lo_anota_y_no_toca_nada(
    pantalla: Pantalla, caplog: pytest.LogCaptureFixture
) -> None:
    inicio, _ = await _job_huerfano(pantalla)
    antes = await _blobs(pantalla)
    configure_keyring(None)
    caplog.set_level(logging.INFO)

    await rotate_job.resume_running_jobs(pantalla.fabrica)

    job = await pantalla.job(inicio.job_id)
    assert (job.status, job.done) == ("running", 0)
    assert await _blobs(pantalla) == antes
    assert any(r.levelno >= logging.WARNING for r in caplog.records), "debía anotarlo en el log"
    assert "secreto" not in caplog.text


async def test_el_post_lanza_la_tarea_solo_despues_de_confirmar(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    """La tarea lee el job con su propia sesión: si arrancara antes del commit del request no lo
    vería. Con la puerta cerrada, al primer lote el job ya es visible desde otra sesión."""
    _, vieja = await _sembrar(pantalla)

    r = await pantalla.rotar(vieja)
    await puerta.llega()

    assert (await pantalla.job(r.json()["job_id"])).status == "running"
    puerta.abrir()
    await pantalla.terminar()
    assert (await pantalla.job(r.json()["job_id"])).status == "done"


# S6-R1 (revisiones): huérfano, custodia y rastro ---


async def test_un_job_running_sin_tarea_se_reanuda_con_el_post(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    """DB M3: el job `running` huérfano (la tarea murió o el api se apagó) no bloquea la pantalla:
    con el cupo libre, el `POST` sobre la `active` lo reanuda (mismo `job_id`, sin versión 3)."""
    inicio, ids = await _job_huerfano(pantalla)
    puerta.abrir()

    r = await pantalla.rotar(inicio.new_key_id)
    await pantalla.terminar()

    assert r.status_code == 202, r.text
    assert r.json()["job_id"] == str(inicio.job_id)
    job = await pantalla.job(inicio.job_id)
    assert (job.status, job.done, job.total) == ("done", 1200, 1200)
    assert len(await pantalla.llaves()) == 2
    async with pantalla.fabrica() as sesion:
        await todo_se_lee(sesion, ids, await blobs_de_rotacion(sesion))


async def test_409_rotation_running_con_una_migracion_de_proveedor_abierta(
    pantalla: Pantalla,
) -> None:
    """S5-D190: ni la rotación nueva ni la reanudación conviven con `migrate_provider`/`rewrap`."""
    from app.core.context import actor_scope
    from app.core.crypto.models import CryptoJob

    _, vieja = await _sembrar(pantalla)
    async with pantalla.fabrica() as sesion:
        with actor_scope(pantalla.admin.id):
            async with sesion.begin():
                sesion.add(
                    CryptoJob(
                        kind="migrate_provider",
                        status="running",
                        total=0,
                        done=0,
                        created_by=pantalla.admin.id,
                    )
                )

    r = await pantalla.rotar(vieja)

    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "rotation_running"
    assert [(k.version, k.state) for k in await pantalla.llaves()] == [(1, "active")]


async def test_el_post_deja_los_verbos_rotate_y_wrap_en_crypto_ops(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    _, vieja = await _sembrar(pantalla)
    await vaciar_ops(pantalla.engine)
    puerta.abrir()

    r = await pantalla.rotar(vieja)
    await pantalla.terminar()

    assert r.status_code == 202, r.text
    async with pantalla.fabrica() as sesion:
        verbos = {
            f.verb
            for f in await sesion.execute(
                text("SELECT DISTINCT verb FROM crypto.crypto_ops WHERE data_class = :c"),
                {"c": CLASE_ROTADA},
            )
        }
    assert {"rotate", "wrap"} <= verbos, verbos

"""La fila de auditoría de una rotación desde la pantalla (S6-R1, US-145; S6-D61, E5). Rojo R1.

`crypto.crypto_keys` NO es `__audited__` (su bitácora propia es `crypto_ops`) y entrar en
`AUDITABLE_TABLES` no activa el hook de auditoría: una rotación completa deja EXACTAMENTE UNA fila
`update` sobre `crypto.crypto_keys` en `audit_log`, la que el router escribe por la puerta
`set_audit_writer` en la misma transacción que el cambio de llaves. No lleva material, referencias
ni blobs; `record_id` es la llave del camino; `GET /audit?table=crypto.crypto_keys` la devuelve.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.modules.audit.queries import AUDITABLE_TABLES
from tests.audit._apoyo import AUDIT, CAMPOS_ROW, ruta_entrada
from tests.crypto._rotacion import CLASE_ROTADA, filas_rotacion, llave_activa
from tests.crypto._rotacion_pantalla import Pantalla, PuertaDeLotes

pytestmark = pytest.mark.usefixtures("reloj")

TABLA = "crypto.crypto_keys"
CONTEO = (
    "SELECT count(*) FROM audit.audit_log WHERE table_name = 'crypto.crypto_keys' "
    "AND action = 'update'"
)


async def _rotar_completa(pantalla: Pantalla, puerta: PuertaDeLotes) -> tuple[str, str]:
    async with pantalla.fabrica() as sesion:
        await filas_rotacion(sesion, 1200)
        vieja = (await llave_activa(sesion)).id
    puerta.abrir()
    r = await pantalla.rotar(vieja)
    assert r.status_code == 202, r.text
    await pantalla.terminar()
    return str(vieja), r.json()["new_key_id"]


async def _cuenta(pantalla: Pantalla) -> int:
    async with pantalla.fabrica() as sesion:
        return int(await sesion.scalar(text(CONTEO)) or 0)


def test_crypto_keys_es_auditable_para_el_filtro_de_get_audit() -> None:
    assert TABLA in AUDITABLE_TABLES


async def test_una_rotacion_completa_deja_exactamente_una_fila_update(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    antes = await _cuenta(pantalla)

    vieja, _ = await _rotar_completa(pantalla, puerta)

    assert await _cuenta(pantalla) - antes == 1  # ni una por lote, ni una por la llave nueva
    (fila,) = await pantalla.filas_de_auditoria(TABLA)
    assert fila["action"] == "update" and str(fila["record_id"]) == vieja
    assert fila["user_id"] == pantalla.admin.id


async def test_la_fila_no_lleva_material_vault_ni_referencias(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    await _rotar_completa(pantalla, puerta)

    (fila,) = await pantalla.filas_de_auditoria(TABLA)

    contenido = str({"before": fila["before"], "after": fila["after"]})
    for prohibido in ("wrapped_material", "vault:", "apex-sign-audit", "apx1.", "\\x"):
        assert prohibido not in contenido, prohibido
    assert fila["after"]["reason"] == "sospecha"
    assert fila["after"]["data_class"] == CLASE_ROTADA
    assert fila["after"]["state"] == "decrypt_only"


async def test_get_audit_con_table_devuelve_la_fila_de_la_rotacion(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    vieja, _ = await _rotar_completa(pantalla, puerta)

    r = await pantalla.http.get(AUDIT, params={"table": TABLA}, headers=pantalla._h())

    assert r.status_code == 200, r.text
    filas = [f for f in r.json()["items"] if f["table_name"] == TABLA]
    assert [(f["action"], f["record_id"]) for f in filas] == [("update", vieja)]
    assert set(filas[0]) == CAMPOS_ROW
    detalle = await pantalla.http.get(ruta_entrada(filas[0]["seq"]), headers=pantalla._h())
    assert detalle.status_code == 200, detalle.text
    for prohibido in ("wrapped_material", "vault:", "apx1."):
        assert prohibido not in detalle.text, prohibido


async def test_un_post_rechazado_no_deja_fila_de_auditoria(pantalla: Pantalla) -> None:
    antes = await _cuenta(pantalla)

    r = await pantalla.rotar("00000000-0000-0000-0000-00000000dead")

    assert r.status_code == 404, r.text
    assert await _cuenta(pantalla) == antes


async def test_reanudar_deja_una_fila_resume_sin_material(
    pantalla: Pantalla, puerta: PuertaDeLotes
) -> None:
    """Seg L4: la reanudación audita `update` con `after = {event: resume, job_id}`."""
    from app.core.crypto.errors import CryptoError

    async with pantalla.fabrica() as sesion:
        await filas_rotacion(sesion, 1200)
        vieja = (await llave_activa(sesion)).id
    real = puerta.real
    fallos = {"restan": 1}

    async def falla_una_vez(session: object, job: object, tamano: int = 500) -> int:
        if puerta.contador == 2 and fallos["restan"]:
            fallos["restan"] -= 1
            raise CryptoError("decrypt_failed", "x")
        return int(await real(session, job, tamano))

    puerta.real = falla_una_vez
    puerta.abrir()
    primero = await pantalla.rotar(vieja)
    await pantalla.terminar()
    activa = primero.json()["new_key_id"]

    r = await pantalla.rotar(activa)
    await pantalla.terminar()

    assert r.status_code == 202, r.text
    filas = await pantalla.filas_de_auditoria(TABLA)
    assert [f["action"] for f in filas] == ["update", "update"]
    assert str(filas[1]["record_id"]) == activa
    assert filas[1]["after"] == {"event": "resume", "job_id": primero.json()["job_id"]}
    assert "wrapped_material" not in str(filas[1])

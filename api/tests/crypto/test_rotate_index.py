"""`rotate_index` (`rotate-key --index`): nueva llave de índice ciego y `*_idx` recalculados
(S4B-B3b; S4B-D39).

Una sola transacción: la llave `index` activa pasa a `decrypt_only`, nace la versión 2 y se
recalcula `document_idx` de cada fila a partir de `document` (descifrado). La llave `encrypt` y
los blobs no cambian. Se niega sobre `MAX_INDEX_ROWS` filas (50.000); aquí se baja el tope con
`monkeypatch` en vez de insertar 50.001 filas.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.context import actor_scope
from app.core.crypto import bus, service
from app.core.crypto.models import CryptoOp
from app.core.crypto.service import rotate_index
from tests.crypto._rotacion import (
    CLASE_ROTADA,
    Fabrica,
    blobs_de_rotacion,
    filas_rotacion,
    indices_de_rotacion,
    llaves_de,
)
from tests.crypto._rotacion_flujo import ACTOR, MOTIVO, esperado, recargar, vaciar_ops

pytestmark = pytest.mark.usefixtures("reloj")

POR_INDICE = "SELECT id FROM test_crypto.crypto_test_person WHERE document_idx = :i"


async def _rotar_indice(fabrica: Fabrica, motivo: str = MOTIVO) -> int:
    with actor_scope(ACTOR):
        async with fabrica() as sesion, sesion.begin():
            return await rotate_index(sesion, CLASE_ROTADA, motivo, ACTOR)


async def test_rotate_index_cambia_todos_los_document_idx(rotacion_lista: Fabrica) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 60)
        antes = await indices_de_rotacion(sesion)

    filas = await _rotar_indice(rotacion_lista)

    assert filas == 60
    async with rotacion_lista() as sesion:
        despues = await indices_de_rotacion(sesion)
    assert set(despues) == set(antes)
    assert all(despues[i] is not None and despues[i] != antes[i] for i in antes)
    assert len(set(despues.values())) == 60


async def test_la_busqueda_por_el_valor_normalizado_encuentra_con_la_llave_nueva(
    rotacion_lista: Fabrica,
) -> None:
    async with rotacion_lista() as sesion:
        ids = await filas_rotacion(sesion, 25)
        viejo = bus.blind_index(CLASE_ROTADA, esperado(7))
    await _rotar_indice(rotacion_lista)

    async with rotacion_lista() as sesion:
        await recargar(sesion)
        nuevo = bus.blind_index(CLASE_ROTADA, esperado(7))
        encontradas = (await sesion.execute(text(POR_INDICE), {"i": nuevo})).scalars().all()
        perdidas = (await sesion.execute(text(POR_INDICE), {"i": viejo})).scalars().all()

    assert nuevo != viejo
    assert list(encontradas) == [ids[7]]
    assert list(perdidas) == []


async def test_la_llave_index_anterior_queda_decrypt_only_y_la_de_cifrado_no_cambia(
    rotacion_lista: Fabrica,
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 10)
        blobs_antes = await blobs_de_rotacion(sesion)

    await _rotar_indice(rotacion_lista)

    async with rotacion_lista() as sesion:
        indices = await llaves_de(sesion, purpose="index")
        cifrado = await llaves_de(sesion, purpose="encrypt")
        assert [(k.version, k.state) for k in indices] == [(1, "decrypt_only"), (2, "active")]
        assert [(k.version, k.state) for k in cifrado] == [(1, "active")]
        assert indices[0].rotated_by == ACTOR
        assert await blobs_de_rotacion(sesion) == blobs_antes


async def test_sin_datos_funciona_y_deja_la_llave_nueva(rotacion_lista: Fabrica) -> None:
    filas = await _rotar_indice(rotacion_lista)

    assert filas == 0
    async with rotacion_lista() as sesion:
        indices = await llaves_de(sesion, purpose="index")
    assert [(k.version, k.state) for k in indices] == [(1, "decrypt_only"), (2, "active")]


async def test_registra_una_fila_rotate_en_crypto_ops(
    rotacion_lista: Fabrica, engine: AsyncEngine
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 10)
    await vaciar_ops(engine)

    await _rotar_indice(rotacion_lista)

    async with rotacion_lista() as sesion:
        filas = (
            await sesion.scalars(
                select(CryptoOp).where(
                    CryptoOp.verb == "rotate", CryptoOp.data_class == CLASE_ROTADA
                )
            )
        ).all()
    assert len(filas) == 1
    assert filas[0].user_id == ACTOR


async def test_mas_del_tope_de_filas_se_niega_sin_cambiar_nada(
    rotacion_lista: Fabrica, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "MAX_INDEX_ROWS", 10)
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 11)
        antes = await indices_de_rotacion(sesion)

    with pytest.raises(ValueError):
        await _rotar_indice(rotacion_lista)

    async with rotacion_lista() as sesion:
        assert await indices_de_rotacion(sesion) == antes
        indices = await llaves_de(sesion, purpose="index")
    assert [(k.version, k.state) for k in indices] == [(1, "active")]


def test_el_tope_por_defecto_es_50000() -> None:
    assert service.MAX_INDEX_ROWS == 50_000


@pytest.mark.parametrize("motivo", ["", "con\nsalto", "a@b.co", "1234567", "x" * 201])
async def test_un_reason_invalido_lanza_value_error_sin_tocar_las_llaves(
    rotacion_lista: Fabrica, motivo: str
) -> None:
    async with rotacion_lista() as sesion:
        await filas_rotacion(sesion, 5)

    with pytest.raises(ValueError):
        await _rotar_indice(rotacion_lista, motivo)

    async with rotacion_lista() as sesion:
        indices = await llaves_de(sesion, purpose="index")
    assert [(k.version, k.state) for k in indices] == [(1, "active")]

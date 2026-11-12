"""`current_photo_id` y `list_for_owner` (S6-C1, US-147/US-148; S6-D22, S6-D25, G-04).

La foto vigente es la más reciente por `created_at DESC, id DESC`; una foto nueva no borra la
anterior. `current_photo_id(session, owner_table, owner_ids)` resuelve un lote de ids con UNA
consulta por cada 200 (`ID_BATCH`, el patrón de `any_uuids`): lo usa la lista de socios para no
hacer N+1. `list_for_owner` pagina sin devolver nunca `filename_random` ni `key_id`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.modules.attachments import service
from app.modules.attachments.storage.local import LocalDiskStorage
from tests.attachments._apoyo import insertar, subir
from tests.conftest import ContadorDeConsultas
from tests.factories import files

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
TABLA = "attachments.attachments"


async def test_gana_la_mas_reciente_por_created_at_aunque_su_id_sea_menor(
    listo: AsyncSession,
) -> None:
    dueno = uuid4()
    vieja = await insertar(listo, owner=dueno, created_at=T0, id_=UUID(int=900))
    nueva = await insertar(listo, owner=dueno, created_at=T0 + timedelta(hours=2), id_=UUID(int=1))
    await insertar(listo, owner=dueno, created_at=T0 + timedelta(hours=1), id_=UUID(int=999))

    resultado = await service.current_photo_id(listo, "members", [dueno])

    assert resultado == {dueno: nueva} and nueva != vieja


async def test_con_el_mismo_created_at_gana_el_id_mayor(listo: AsyncSession) -> None:
    dueno = uuid4()
    await insertar(listo, owner=dueno, created_at=T0, id_=UUID(int=1))
    mayor = await insertar(listo, owner=dueno, created_at=T0, id_=UUID(int=2))

    assert (await service.current_photo_id(listo, "members", [dueno]))[dueno] == mayor


async def test_solo_cuentan_las_fotos_y_solo_las_del_dueno(listo: AsyncSession) -> None:
    dueno, otro = uuid4(), uuid4()
    foto = await insertar(listo, owner=dueno, created_at=T0)
    await insertar(listo, owner=dueno, kind="consent", created_at=T0 + timedelta(days=1))
    await insertar(listo, owner=dueno, kind="other", created_at=T0 + timedelta(days=2))
    await insertar(listo, owner=otro, created_at=T0 + timedelta(days=3))

    resultado = await service.current_photo_id(listo, "members", [dueno])

    assert resultado == {dueno: foto}


async def test_un_dueno_sin_foto_devuelve_none_y_la_respuesta_trae_todos_los_pedidos(
    listo: AsyncSession,
) -> None:
    con, sin_fotos, sin_nada = uuid4(), uuid4(), uuid4()
    foto = await insertar(listo, owner=con)
    await insertar(listo, owner=sin_fotos, kind="consent")

    resultado = await service.current_photo_id(listo, "members", [con, sin_fotos, sin_nada])

    assert resultado == {con: foto, sin_fotos: None, sin_nada: None}


async def test_una_lista_vacia_no_consulta_nada(
    listo: AsyncSession, contador_de_consultas: ContadorDeConsultas
) -> None:
    with contador_de_consultas.midiendo():
        assert await service.current_photo_id(listo, "members", []) == {}
    assert contador_de_consultas.de(TABLA) == 0


@pytest.mark.parametrize(("cuantos", "consultas"), [(1, 1), (200, 1), (201, 2), (450, 3)])
async def test_una_consulta_por_lote_de_200_ids(
    listo: AsyncSession,
    contador_de_consultas: ContadorDeConsultas,
    cuantos: int,
    consultas: int,
) -> None:
    ids = [uuid4() for _ in range(cuantos)]
    esperada = await insertar(listo, owner=ids[-1])

    with contador_de_consultas.midiendo():
        resultado = await service.current_photo_id(listo, "members", ids)

    assert contador_de_consultas.de(TABLA) == consultas
    assert len(resultado) == cuantos and resultado[ids[-1]] == esperada
    assert all(v is None for k, v in resultado.items() if k != ids[-1])


async def test_la_consulta_no_manda_un_parametro_por_id(
    listo: AsyncSession, contador_de_consultas: ContadorDeConsultas
) -> None:
    """Una sola sentencia de 200 ids no puede llevar 200 marcadores: el lote va como arreglo."""
    ids = [uuid4() for _ in range(200)]
    with contador_de_consultas.midiendo():
        await service.current_photo_id(listo, "members", ids)
    (sql,) = [s for s in contador_de_consultas.sentencias if TABLA in s]
    assert sql.count("$") < 20 and sql.count("%(") < 20, sql[:300]


async def test_dos_subidas_de_foto_conservan_las_dos_y_la_vigente_es_la_mas_reciente(
    listo: AsyncSession, almacen: LocalDiskStorage, por: UUID
) -> None:
    dueno = uuid4()
    primera = await subir(listo, por, "photo", files.jpeg(1000), dueno=dueno)
    segunda = await subir(listo, por, "photo", files.png(1000), dueno=dueno)

    pagina = await service.list_for_owner(listo, "members", dueno, PageParams(limit=10, offset=0))
    vigente = (await service.current_photo_id(listo, "members", [dueno]))[dueno]

    assert pagina.total == 2 and {i.id for i in pagina.items} == {primera.id, segunda.id}
    mas_reciente = max((primera, segunda), key=lambda a: (a.created_at, a.id))
    assert vigente == mas_reciente.id
    assert len(list(almacen.root.iterdir())) == 2  # la anterior no se borra


async def test_list_for_owner_ordena_pagina_y_nunca_devuelve_el_nombre_del_archivo(
    listo: AsyncSession,
) -> None:
    dueno, otro = uuid4(), uuid4()
    ids = [
        await insertar(
            listo, owner=dueno, created_at=T0 + timedelta(minutes=i), id_=UUID(int=i + 1)
        )
        for i in range(5)
    ]
    await insertar(listo, owner=otro, created_at=T0)

    primera = await service.list_for_owner(listo, "members", dueno, PageParams(limit=2, offset=0))
    ultima = await service.list_for_owner(listo, "members", dueno, PageParams(limit=2, offset=4))

    assert primera.total == 5 and (primera.limit, primera.offset) == (2, 0)
    assert [i.id for i in primera.items] == [ids[4], ids[3]]  # created_at DESC
    assert [i.id for i in ultima.items] == [ids[0]]
    for item in primera.items + ultima.items:
        volcado = item.model_dump()
        assert "filename_random" not in volcado and "key_id" not in volcado
        assert item.owner_id == dueno and item.owner_table == "members"

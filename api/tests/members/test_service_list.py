"""`members.service.list`, `search_ids` y `names_for` con PostgreSQL real (S2-B8; US-070
criterios 3 a 8; RN-13, RN-14, N-01, N-20; blueprint B8).

- Se encuentra a "Laura Gómez" por `"1.020.304"` (guardada como `1020304`), por teléfono con y
  sin `+57` y con espacios, por correo en mayúsculas, y por `"góm"`, `"Góm"`, `"gom"` (sin
  tilde, como la búsqueda de planes de US-079) y `"laura gó"` (nombre y apellido juntos).
- Sin `status` excluye a los dados de baja; `status=deleted` muestra solo a los dados de baja;
  `active` e `inactive` miran solo a los vivos con ese estado.
- Cada `sort` ordena; `%` y `_` del término no actúan como comodines.
- Paginación con `limit`, `offset` y `total` sin repetir ni omitir filas.
- Las filas no traen ningún campo sensible (N-01); un socio sin membresías lleva
  `membership_status == "none"` y `plan_name` y `membership_end_date` nulos (S3-B9b, D22:
  la página se decora con `status_for`; sin entrada, `none`).
- Listar nunca descifra: cero filas `decrypt` nuevas en `crypto_ops`; una búsqueda deja como
  mucho 3 filas `index` (una por clase, agregadas en un lote `bus.batch`) y una por nombre ninguna.
- `search_ids` y `names_for` hacen una sola consulta (sin N+1) y `names_for` incluye a los dados
  de baja.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring
from app.core.pagination import Page, PageParams
from app.modules.members import service
from app.modules.members.models import Member
from app.modules.members.schemas import MemberListQuery, MemberName, MemberRowOut
from tests.conftest import T0
from tests.factories.members import KNOWN_NORMALIZED, make_member, make_members, unique_document
from tests.members._apoyo import CAMPOS_FILA, operaciones

SENSIBLES = ("document", "phone", "email", "birth_date", "emergency_contact")


async def listar(
    session: AsyncSession, *, limit: int = 25, offset: int = 0, **filtros: Any
) -> Page[MemberRowOut]:
    """Una petición: `service.list` bajo un actor y el commit de `get_session`."""
    with actor_scope(SYSTEM_USER_ID):
        pagina = await service.list(
            session, MemberListQuery(**filtros), PageParams(limit=limit, offset=offset)
        )
        await session.commit()
    return pagina


def ids(pagina: Page[MemberRowOut]) -> list[UUID]:
    return [fila.id for fila in pagina.items]


async def laura(session: AsyncSession, **cambios: Any) -> Member:
    """El socio de los escenarios BDD de US-070."""
    valores: dict[str, Any] = {
        "first_name": "Laura",
        "last_name": "Gómez",
        "document": "1020304",
        "phone": "3001234567",
        "email": "laura.gomez@correo.co",
        "sex": "f",
    }
    valores.update(cambios)
    return await make_member(session, **valores)


async def otro(session: AsyncSession, first_name: str, last_name: str, **cambios: Any) -> Member:
    """Socio sin teléfono ni correo y con documento único."""
    valores: dict[str, Any] = {
        "first_name": first_name,
        "last_name": last_name,
        "document": unique_document(),
        "phone": None,
        "email": None,
    }
    valores.update(cambios)
    return await make_member(session, **valores)


@contextmanager
def contar_sentencias(engine: AsyncEngine) -> Iterator[list[str]]:
    """Sentencias SQL enviadas por el motor, sin las de savepoint de la fixture `session`."""
    sentencias: list[str] = []

    def anotar(_conn: Any, _cursor: Any, sql: str, *_args: Any) -> None:
        if not sql.lstrip().upper().startswith(("SAVEPOINT", "RELEASE", "ROLLBACK TO")):
            sentencias.append(sql)

    event.listen(engine.sync_engine, "before_cursor_execute", anotar)
    try:
        yield sentencias
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", anotar)


# Búsqueda por índice ciego --------------------------------------------------------------


async def test_encuentra_por_documento_con_puntos(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    socio = await laura(session)
    await make_members(session, 3, last_name="Ruiz")
    assert ids(await listar(session, q="1.020.304")) == [socio.id]
    assert ids(await listar(session, q="1020304")) == [socio.id]


@pytest.mark.parametrize("telefono", ["300 123 4567", "+57 300 123 4567", "3001234567"])
async def test_encuentra_por_telefono_con_y_sin_prefijo(
    session: AsyncSession, bus_listo: Keyring, telefono: str
) -> None:
    socio = await laura(session)
    await make_members(session, 3, last_name="Ruiz")
    assert ids(await listar(session, q=telefono)) == [socio.id]


async def test_encuentra_por_correo_sin_distinguir_mayusculas(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    socio = await laura(session)
    conocida = await make_member(session)  # KNOWN: Lucía Gómez, "Lucia.Gomez@Correo.co"
    assert ids(await listar(session, q="LAURA.GOMEZ@CORREO.CO")) == [socio.id]
    assert ids(await listar(session, q="lucia.gomez@correo.co")) == [conocida.id]
    assert ids(await listar(session, q="Lucia.Gomez@Correo.co")) == [conocida.id]


async def test_un_termino_que_no_coincide_da_la_pagina_vacia(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    await laura(session)
    pagina = await listar(session, q="9.999.999")
    assert pagina.items == []
    assert pagina.total == 0


# Búsqueda por nombre ---------------------------------------------------------------------


@pytest.mark.parametrize("termino", ["góm", "Góm", "GÓMEZ", "gom", "laura gó"])
async def test_encuentra_por_nombre_y_apellido_sin_mayusculas_ni_tildes(
    session: AsyncSession, bus_listo: Keyring, termino: str
) -> None:
    socio = await laura(session)
    await make_members(session, 3, last_name="Ruiz")
    encontrados = ids(await listar(session, q=termino))
    assert encontrados == [socio.id]


async def test_la_busqueda_por_nombre_trae_a_todos_los_que_coinciden(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    socio = await laura(session)
    conocida = await make_member(session)  # Lucía Gómez
    await otro(session, "Pedro", "Ruiz")
    assert set(ids(await listar(session, q="góm"))) == {socio.id, conocida.id}


@pytest.mark.parametrize(
    ("termino", "esperado"),
    [("l_v", "guion"), ("n%f", "porcentaje"), ("%", "porcentaje"), ("_", "guion")],
)
async def test_porcentaje_y_guion_bajo_no_son_comodines(
    session: AsyncSession, bus_listo: Keyring, termino: str, esperado: str
) -> None:
    socios = {
        "guion": await otro(session, "Ana", "Del_Valle"),
        "sin-guion": await otro(session, "Ana", "DelXValle"),
        "porcentaje": await otro(session, "Ana", "Cien%Fuegos"),
        "sin-porcentaje": await otro(session, "Ana", "CienXFuegos"),
    }
    assert ids(await listar(session, q=termino)) == [socios[esperado].id]


# Estado ----------------------------------------------------------------------------------


async def _padron(session: AsyncSession) -> dict[str, Member]:
    return {
        "activo": await otro(session, "Ana", "Activa"),
        "inactivo": await otro(session, "Bea", "Inactiva", status="inactive"),
        "baja": await otro(session, "Pedro", "Ruiz", deleted_at=T0),
        "baja-inactiva": await otro(
            session, "Raúl", "Ruiz", status="inactive", deleted_at=T0 - timedelta(days=1)
        ),
    }


async def test_sin_status_excluye_a_los_dados_de_baja(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    padron = await _padron(session)
    pagina = await listar(session)
    assert set(ids(pagina)) == {padron["activo"].id, padron["inactivo"].id}
    assert pagina.total == 2


async def test_status_deleted_muestra_solo_a_los_dados_de_baja(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    padron = await _padron(session)
    pagina = await listar(session, status="deleted")
    assert set(ids(pagina)) == {padron["baja"].id, padron["baja-inactiva"].id}
    assert all(fila.deleted_at is not None for fila in pagina.items)


@pytest.mark.parametrize(("estado", "clave"), [("active", "activo"), ("inactive", "inactivo")])
async def test_status_active_e_inactive_miran_solo_a_los_vivos(
    session: AsyncSession, bus_listo: Keyring, estado: str, clave: str
) -> None:
    padron = await _padron(session)
    pagina = await listar(session, status=estado)
    assert ids(pagina) == [padron[clave].id]
    assert pagina.items[0].status == estado


async def test_un_dado_de_baja_no_aparece_al_buscarlo_salvo_con_status_deleted(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    baja = await laura(session, deleted_at=T0)
    assert ids(await listar(session, q="1.020.304")) == []
    assert ids(await listar(session, q="góm")) == []
    assert ids(await listar(session, q="1.020.304", status="deleted")) == [baja.id]


# Orden y paginación ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("orden", "esperado"),
    [
        ("last_name", ["carlos", "beatriz", "ana"]),
        ("-last_name", ["ana", "beatriz", "carlos"]),
        ("first_name", ["ana", "beatriz", "carlos"]),
        ("-first_name", ["carlos", "beatriz", "ana"]),
        ("created_at", ["beatriz", "carlos", "ana"]),
        ("-created_at", ["ana", "carlos", "beatriz"]),
    ],
)
async def test_cada_sort_ordena(
    session: AsyncSession, bus_listo: Keyring, orden: str, esperado: list[str]
) -> None:
    socios = {
        "ana": await otro(session, "Ana", "Zapata", created_at=T0 + timedelta(minutes=3)),
        "beatriz": await otro(session, "Beatriz", "Mejía", created_at=T0 + timedelta(minutes=1)),
        "carlos": await otro(session, "Carlos", "Arango", created_at=T0 + timedelta(minutes=2)),
    }
    propios = {s.id: nombre for nombre, s in socios.items()}
    orden_real = [propios[i] for i in ids(await listar(session, sort=orden)) if i in propios]
    assert orden_real == esperado


async def test_el_orden_por_defecto_es_por_apellido(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    zapata = await otro(session, "Ana", "Zapata")
    arango = await otro(session, "Carlos", "Arango")
    assert MemberListQuery().sort == "last_name"
    assert ids(await listar(session)) == [arango.id, zapata.id]


async def test_pagina_con_limit_offset_y_total_sin_repetir_ni_omitir(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    socios = await make_members(session, 7, last_name="Paginado")
    await otro(session, "Pedro", "Ruiz")
    primera = await listar(session, q="paginado", limit=3, offset=0)
    segunda = await listar(session, q="paginado", limit=3, offset=3)
    tercera = await listar(session, q="paginado", limit=3, offset=6)
    assert (primera.total, segunda.total, tercera.total) == (7, 7, 7)
    assert (primera.limit, primera.offset) == (3, 0)
    assert (tercera.limit, tercera.offset) == (3, 6)
    assert [len(p.items) for p in (primera, segunda, tercera)] == [3, 3, 1]
    vistos = ids(primera) + ids(segunda) + ids(tercera)
    assert len(vistos) == len(set(vistos)) == 7
    assert set(vistos) == {s.id for s in socios}
    fuera = await listar(session, q="paginado", limit=3, offset=50)
    assert fuera.items == [] and fuera.total == 7


# Filas sin datos sensibles y sin descifrar -----------------------------------------------


async def test_las_filas_no_traen_campos_sensibles_ni_enmascarados(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    conocida = await make_member(session, sex="f")
    pagina = await listar(session, q="Lucia.Gomez@Correo.co")
    assert ids(pagina) == [conocida.id]
    fila = pagina.items[0].model_dump(mode="json")
    assert set(fila) == CAMPOS_FILA
    assert fila["first_name"] == "Lucía" and fila["last_name"] == "Gómez"
    assert fila["sex"] == "f" and fila["status"] == "active" and fila["deleted_at"] is None
    assert fila["membership_status"] == "none"
    assert fila["plan_name"] is None and fila["membership_end_date"] is None
    texto = pagina.model_dump_json()
    for valor in (*KNOWN_NORMALIZED, "apx1.", "•"):
        assert valor not in texto, valor


async def test_listar_y_buscar_no_descifran_y_agrupan_los_indices_en_un_lote(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    await laura(session)
    await make_member(session)
    await make_members(session, 3, last_name="Ruiz")
    descifrados = len(await operaciones(session, verb="decrypt"))
    for termino, minimo in (("1.020.304", 1), ("+57 300 765 4321", 1), ("LAURA@X.CO", 1)):
        antes = {o["id"] for o in await operaciones(session, verb="index")}
        await listar(session, q=termino)
        nuevas = [o for o in await operaciones(session, verb="index") if o["id"] not in antes]
        assert minimo <= len(nuevas) <= 3, (termino, nuevas)
        assert len({o["data_class"] for o in nuevas}) == len(nuevas), termino
        lotes = {o["batch_id"] for o in nuevas}
        assert len(lotes) == 1 and None not in lotes, (termino, lotes)
        assert all(o["user_id"] == SYSTEM_USER_ID for o in nuevas)
    antes = len(await operaciones(session, verb="index"))
    await listar(session, q="góm")
    await listar(session)
    await listar(session, status="deleted", sort="-created_at")
    assert len(await operaciones(session, verb="index")) == antes  # el nombre no indexa
    assert len(await operaciones(session, verb="decrypt")) == descifrados


# Contratos para otros módulos ------------------------------------------------------------


async def test_search_ids_busca_en_una_consulta_y_respeta_los_dados_de_baja(
    session: AsyncSession, engine: AsyncEngine, bus_listo: Keyring
) -> None:
    viva = await laura(session)
    baja = await otro(session, "Lorena", "Gómez", deleted_at=T0)
    await otro(session, "Pedro", "Ruiz")
    with actor_scope(SYSTEM_USER_ID), contar_sentencias(engine) as sentencias:
        encontrados = await service.search_ids(session, "góm")
    assert encontrados == {viva.id}
    assert len(sentencias) == 1, sentencias
    with actor_scope(SYSTEM_USER_ID):
        assert await service.search_ids(session, "góm", include_deleted=True) == {
            viva.id,
            baja.id,
        }
        assert await service.search_ids(session, "+57 300 123 4567") == {viva.id}
        assert await service.search_ids(session, "1.020.304") == {viva.id}
        assert await service.search_ids(session, "   ") == set()


async def test_names_for_trae_nombres_y_sexo_en_una_consulta_incluidos_los_dados_de_baja(
    session: AsyncSession, engine: AsyncEngine, bus_listo: Keyring
) -> None:
    viva = await laura(session)
    baja = await otro(session, "Pedro", "Ruiz", sex="m", deleted_at=T0)
    await make_members(session, 5, last_name="Relleno")
    inexistente = uuid4()
    with contar_sentencias(engine) as sentencias:
        nombres = await service.names_for(session, [viva.id, baja.id, inexistente])
    assert len(sentencias) == 1, sentencias
    assert nombres == {
        viva.id: MemberName(id=viva.id, first_name="Laura", last_name="Gómez", sex="f"),
        baja.id: MemberName(id=baja.id, first_name="Pedro", last_name="Ruiz", sex="m"),
    }
    assert await service.names_for(session, []) == {}


async def test_names_for_acepta_cualquier_iterable_de_ids(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    socios = await make_members(session, 4, last_name="Iterable")
    nombres = await service.names_for(session, (s.id for s in socios))
    assert set(nombres) == {s.id for s in socios}
    assert all(isinstance(n, MemberName) for n in nombres.values())
    for campo in SENSIBLES:
        assert not hasattr(next(iter(nombres.values())), campo)

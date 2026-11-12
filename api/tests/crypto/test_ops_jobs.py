"""`GET /api/v1/crypto/ops` y `GET /api/v1/crypto/jobs` (S6-B2, US-144; S6-D16). Rojo B2.

Bitacora de `crypto_ops` y trabajos de `crypto_jobs`, solo lectura, solo admin (`staff-read`,
`no-store`). Filtros de la bitacora: `from`/`to` (`check_instant_range` y como mucho 366 dias),
`verb`, `data_class`, `key_id`, `user_id`, `result`, `batch_id`, `q`; orden `at DESC, id DESC`.
Filtros de los trabajos: `status`, `kind` (solo `JOB_KINDS`), `data_class`, `q`; `percent` sale de
`job_percent`. Ninguna respuesta lleva material, referencias ni el texto `error` del proveedor.
Los instantes son relativos a `T0` (el reloj congelado de la app de pruebas).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto.inventory import job_percent
from app.core.crypto.models import JOB_KINDS, JOB_STATUSES, OP_VERBS, CryptoOp
from tests.conftest import T0, Cabeceras, CrearUsuario
from tests.crypto._bitacora import (
    ERROR_DEL_PROVEEDOR,
    JOBS_URL,
    LLAVE_A,
    LLAVE_B,
    LOTE,
    OPS_URL,
    REGISTRO,
    USUARIO_1,
    USUARIO_2,
    JobsSembrados,
    OpsSembradas,
    iso,
    sembrar_jobs,
    sembrar_muchas_ops,
    sembrar_muchos_jobs,
    sembrar_ops,
)
from tests.crypto.conftest import ClienteAdmin

LIMITE_DE_LECTURAS = 120
CLAVES_DE_OP = {
    "id",
    "at",
    "user_id",
    "verb",
    "data_class",
    "key_id",
    "key_version",
    "record_id",
    "result",
    "batch_id",
}
CLAVES_PERMITIDAS_DE_OP = CLAVES_DE_OP | {"purpose", "count", "request_id"}
CLAVES_DE_JOB = {
    "id",
    "kind",
    "data_class",
    "status",
    "total",
    "done",
    "percent",
    "started_at",
    "finished_at",
}
CLAVES_PERMITIDAS_DE_JOB = CLAVES_DE_JOB | {"created_at"}
PROHIBIDAS_EN_TEXTO = ("wrapped_material", "vault:", "local:", "apex-sign-audit", "key_ref")


@pytest.fixture
async def ops(session: AsyncSession, cliente_admin: ClienteAdmin) -> OpsSembradas:
    return await sembrar_ops(session)


@pytest.fixture
async def jobs(session: AsyncSession, cliente_admin: ClienteAdmin) -> JobsSembrados:
    return await sembrar_jobs(session)


def ids_de(cuerpo: dict[str, Any]) -> list[UUID]:
    return [UUID(item["id"]) for item in cuerpo["items"]]


async def pedir(cliente: ClienteAdmin, ruta: str, **params: object) -> dict[str, Any]:
    r = await cliente.get(ruta, **params)
    assert r.status_code == 200, (params, r.text)
    cuerpo: dict[str, Any] = r.json()
    return cuerpo


async def contar_ops(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count(CryptoOp.id))) or 0)


# Bitacora: forma, orden y contenido -------------------------------------------------------------


async def test_la_bitacora_responde_page_con_el_orden_at_desc_id_desc(
    cliente_admin: ClienteAdmin, ops: OpsSembradas
) -> None:
    cuerpo = await pedir(cliente_admin, OPS_URL)

    assert set(cuerpo) == {"items", "total", "limit", "offset"}
    assert (cuerpo["total"], cuerpo["limit"], cuerpo["offset"]) == (6, 25, 0)
    assert ids_de(cuerpo) == ops.orden_por_defecto()


async def test_cada_operacion_expone_sus_campos_y_ninguno_de_material(
    cliente_admin: ClienteAdmin, ops: OpsSembradas
) -> None:
    cuerpo = await pedir(cliente_admin, OPS_URL, verb="decrypt")

    (item,) = cuerpo["items"]
    assert CLAVES_DE_OP <= set(item) <= CLAVES_PERMITIDAS_DE_OP, set(item)
    assert item["id"] == str(ops.ids[2])
    assert item["verb"] == "decrypt"
    assert item["data_class"] == "member.document"
    assert item["key_id"] == str(LLAVE_A)
    assert item["key_version"] == 1
    assert item["record_id"] == str(REGISTRO)
    assert item["user_id"] == str(USUARIO_1)
    assert item["result"] == "ok"
    assert item["batch_id"] is None
    assert datetime.fromisoformat(item["at"]) == T0 - timedelta(days=5)


async def test_una_operacion_sin_clase_ni_llave_trae_nulos_y_no_se_pierde(
    cliente_admin: ClienteAdmin, ops: OpsSembradas
) -> None:
    cuerpo = await pedir(cliente_admin, OPS_URL, verb="export")

    (item,) = cuerpo["items"]
    assert (item["data_class"], item["key_id"], item["key_version"]) == (None, None, None)


# Bitacora: filtros ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "esperadas"),
    [
        ({"verb": "rotate"}, (3, 4)),
        ({"verb": "sign"}, (5,)),
        ({"data_class": "member.document"}, (1, 2)),
        ({"data_class": "audit.signature"}, (5,)),
        ({"key_id": str(LLAVE_A)}, (1, 2)),
        ({"key_id": str(LLAVE_B)}, (3, 4, 5)),
        ({"user_id": str(USUARIO_1)}, (1, 2, 6)),
        ({"user_id": str(USUARIO_2)}, (3, 4, 5)),
        ({"result": "error"}, (4,)),
        ({"result": "ok"}, (1, 2, 3, 5, 6)),
        ({"batch_id": str(LOTE)}, (3, 4)),
        ({"q": "phone"}, (3, 4)),
        ({"q": "DOCUMENT"}, (1, 2)),
        ({"verb": "rotate", "result": "ok"}, (3,)),
        ({"user_id": str(USUARIO_2), "data_class": "audit.signature"}, (5,)),
    ],
    ids=str,
)
async def test_cada_filtro_de_la_bitacora_recorta_el_resultado(
    cliente_admin: ClienteAdmin,
    ops: OpsSembradas,
    params: dict[str, object],
    esperadas: tuple[int, ...],
) -> None:
    cuerpo = await pedir(cliente_admin, OPS_URL, **params)

    assert set(ids_de(cuerpo)) == ops.de(*esperadas), params
    assert cuerpo["total"] == len(esperadas)


@pytest.mark.parametrize("q", ["%", "_", "member.%", "no-existe", str(USUARIO_1), "101"])
async def test_q_busca_en_la_clase_y_nunca_en_ids_ni_comodines(
    cliente_admin: ClienteAdmin, ops: OpsSembradas, q: str
) -> None:
    """`q` es texto libre sobre `data_class`: el LIKE escapa `%` y `_`, y un `user_id` no se
    encuentra por texto (sin ids ajenos en la busqueda libre)."""
    cuerpo = await pedir(cliente_admin, OPS_URL, q=q)

    assert cuerpo["items"] == [] and cuerpo["total"] == 0


async def test_el_rango_from_to_es_semiabierto_desde_inclusive_hasta_exclusive(
    cliente_admin: ClienteAdmin, ops: OpsSembradas
) -> None:
    dentro = await pedir(
        cliente_admin,
        OPS_URL,
        **{"from": iso(T0 - timedelta(days=6)), "to": iso(T0 - timedelta(days=2))},
    )
    hasta_exclusive = await pedir(
        cliente_admin,
        OPS_URL,
        **{"from": iso(T0 - timedelta(days=6)), "to": iso(T0 - timedelta(days=3))},
    )
    desde_inclusive = await pedir(
        cliente_admin,
        OPS_URL,
        **{"from": iso(T0 - timedelta(days=3)), "to": iso(T0)},
    )

    assert set(ids_de(dentro)) == ops.de(2, 3, 4)
    assert set(ids_de(hasta_exclusive)) == ops.de(2)
    assert set(ids_de(desde_inclusive)) == ops.de(3, 4, 5)


async def test_from_solo_y_to_solo_son_validos(
    cliente_admin: ClienteAdmin, ops: OpsSembradas
) -> None:
    desde = await pedir(cliente_admin, OPS_URL, **{"from": iso(T0 - timedelta(days=4))})
    hasta = await pedir(cliente_admin, OPS_URL, to=iso(T0 - timedelta(days=4)))

    assert set(ids_de(desde)) == ops.de(3, 4, 5)
    assert set(ids_de(hasta)) == ops.de(1, 2, 6)


async def test_un_rango_de_exactamente_366_dias_es_valido(
    cliente_admin: ClienteAdmin, ops: OpsSembradas
) -> None:
    cuerpo = await pedir(
        cliente_admin,
        OPS_URL,
        **{"from": iso(T0 - timedelta(days=366)), "to": iso(T0)},
    )

    assert set(ids_de(cuerpo)) == ops.de(1, 2, 3, 4, 5)  # la 6 (T0-400d) queda fuera


# Bitacora: 422 ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "campo"),
    [
        ({"from": iso(T0 - timedelta(days=1)), "to": iso(T0 - timedelta(days=2))}, "to"),
        ({"from": iso(T0 - timedelta(days=1)), "to": iso(T0 - timedelta(days=1))}, "to"),
        ({"from": iso(T0 - timedelta(days=367)), "to": iso(T0)}, "to"),
        ({"from": iso(T0 - timedelta(days=400)), "to": iso(T0 - timedelta(days=30))}, "to"),
        ({"from": "2019-12-31T00:00:00Z"}, "from"),
        ({"from": "0001-01-01T00:00:00Z"}, "from"),
        ({"from": "2026-01-01T00:00:00"}, "from"),
        ({"to": iso(T0 + timedelta(days=2))}, "to"),
        ({"to": "9999-12-31T23:59:59Z"}, "to"),
    ],
    ids=[
        "invertido",
        "vacio",
        "367-dias",
        "370-dias",
        "from-bajo-piso",
        "from-anio-1",
        "from-sin-zona",
        "to-sobre-techo",
        "to-9999",
    ],
)
async def test_un_rango_invalido_da_422_con_el_campo_y_sin_el_valor(
    cliente_admin: ClienteAdmin, ops: OpsSembradas, params: dict[str, str], campo: str
) -> None:
    r = await cliente_admin.get(OPS_URL, **params)

    assert r.status_code == 422, (params, r.status_code, r.text)
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", campo)
    for valor in params.values():
        assert valor not in error["message"]


@pytest.mark.parametrize(
    "params",
    [
        {"verb": "hash"},
        {"verb": "ROTATE"},
        {"result": "maybe"},
        {"data_class": "sin_punto"},
        {"data_class": "Member.Document"},
        {"key_id": "no-es-uuid"},
        {"user_id": "no-es-uuid"},
        {"batch_id": "123"},
        {"q": "x" * 101},
        {"q": "ana\x00"},
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
        {"offset": 1_000_001},
    ],
    ids=str,
)
async def test_filtros_invalidos_de_la_bitacora_dan_422_nunca_500(
    cliente_admin: ClienteAdmin, ops: OpsSembradas, params: dict[str, object]
) -> None:
    r = await cliente_admin.get(OPS_URL, **params)

    assert r.status_code == 422, (params, r.status_code, r.text)
    assert r.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("verbo", OP_VERBS)
async def test_todos_los_verbos_del_modelo_son_filtros_validos(
    cliente_admin: ClienteAdmin, ops: OpsSembradas, verbo: str
) -> None:
    r = await cliente_admin.get(OPS_URL, verb=verbo)

    assert r.status_code == 200, (verbo, r.text)


# Trabajos ---------------------------------------------------------------------------------------


async def test_los_trabajos_responden_page_en_orden_de_creacion_descendente(
    cliente_admin: ClienteAdmin, jobs: JobsSembrados
) -> None:
    cuerpo = await pedir(cliente_admin, JOBS_URL)

    assert set(cuerpo) == {"items", "total", "limit", "offset"}
    assert (cuerpo["total"], cuerpo["limit"], cuerpo["offset"]) == (5, 25, 0)
    assert ids_de(cuerpo) == jobs.orden_por_defecto()


async def test_cada_trabajo_trae_su_porcentaje_de_job_percent_y_no_el_error(
    cliente_admin: ClienteAdmin, jobs: JobsSembrados
) -> None:
    cuerpo = await pedir(cliente_admin, JOBS_URL)

    por_id = {UUID(i["id"]): i for i in cuerpo["items"]}
    for numero, porcentaje in {1: 100, 2: 33, 3: 100, 4: 44, 5: 0}.items():
        item = por_id[jobs.ids[numero]]
        assert CLAVES_DE_JOB <= set(item) <= CLAVES_PERMITIDAS_DE_JOB, set(item)
        assert item["percent"] == porcentaje, numero
        assert item["percent"] == job_percent(item["total"], item["done"])
        assert "error" not in item
    en_curso = por_id[jobs.ids[2]]
    assert (en_curso["kind"], en_curso["status"], en_curso["data_class"]) == (
        "reencrypt",
        "running",
        "member.phone",
    )
    assert (en_curso["total"], en_curso["done"]) == (3, 1)
    assert en_curso["finished_at"] is None
    sin_clase = por_id[jobs.ids[3]]
    assert (sin_clase["kind"], sin_clase["data_class"]) == ("migrate_provider", None)
    assert ERROR_DEL_PROVEEDOR.split()[0] not in str(cuerpo)
    assert "SECRETO" not in str(cuerpo)


@pytest.mark.parametrize(
    ("params", "esperados"),
    [
        ({"status": "running"}, (2,)),
        ({"status": "done"}, (1, 3)),
        ({"status": "failed"}, (4,)),
        ({"status": "pending"}, (5,)),
        ({"kind": "rotate"}, (1, 5)),
        ({"kind": "rewrap"}, (4,)),
        ({"kind": "migrate_provider"}, (3,)),
        ({"data_class": "member.phone"}, (2,)),
        ({"q": "phone"}, (2,)),
        ({"q": "MEMBER"}, (1, 2, 5)),
        ({"kind": "rotate", "status": "done"}, (1,)),
    ],
    ids=str,
)
async def test_cada_filtro_de_los_trabajos_recorta_el_resultado(
    cliente_admin: ClienteAdmin,
    jobs: JobsSembrados,
    params: dict[str, object],
    esperados: tuple[int, ...],
) -> None:
    cuerpo = await pedir(cliente_admin, JOBS_URL, **params)

    assert set(ids_de(cuerpo)) == jobs.de(*esperados), params
    assert cuerpo["total"] == len(esperados)


@pytest.mark.parametrize("q", ["%", "_", "vault", "SECRETO", "rotate"])
async def test_q_de_trabajos_busca_en_la_clase_y_no_en_el_error_ni_con_comodines(
    cliente_admin: ClienteAdmin, jobs: JobsSembrados, q: str
) -> None:
    cuerpo = await pedir(cliente_admin, JOBS_URL, q=q)

    assert cuerpo["items"] == [] and cuerpo["total"] == 0


@pytest.mark.parametrize("tipo", JOB_KINDS)
async def test_cada_kind_de_job_kinds_es_un_filtro_valido(
    cliente_admin: ClienteAdmin, jobs: JobsSembrados, tipo: str
) -> None:
    r = await cliente_admin.get(JOBS_URL, kind=tipo)

    assert r.status_code == 200, (tipo, r.text)


@pytest.mark.parametrize("estado", JOB_STATUSES)
async def test_cada_estado_de_job_statuses_es_un_filtro_valido(
    cliente_admin: ClienteAdmin, jobs: JobsSembrados, estado: str
) -> None:
    r = await cliente_admin.get(JOBS_URL, status=estado)

    assert r.status_code == 200, (estado, r.text)


@pytest.mark.parametrize(
    "params",
    [
        {"kind": "delete"},
        {"kind": "ROTATE"},
        {"kind": "rotate;drop"},
        {"kind": ""},
        {"status": "cancelled"},
        {"status": "RUNNING"},
        {"data_class": "sin_punto"},
        {"data_class": "Member.Document"},
        {"q": "x" * 101},
        {"q": "a\x00"},
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
    ],
    ids=str,
)
async def test_filtros_invalidos_de_los_trabajos_dan_422_nunca_500(
    cliente_admin: ClienteAdmin, jobs: JobsSembrados, params: dict[str, object]
) -> None:
    r = await cliente_admin.get(JOBS_URL, **params)

    assert r.status_code == 422, (params, r.status_code, r.text)
    assert r.json()["error"]["code"] == "validation_error"


# Paginacion -------------------------------------------------------------------------------------


async def test_la_bitacora_pagina_25_por_defecto_y_no_repite_ni_omite_filas(
    session: AsyncSession, cliente_admin: ClienteAdmin
) -> None:
    ids = await sembrar_muchas_ops(session, 30)

    primera = await pedir(cliente_admin, OPS_URL)
    segunda = await pedir(cliente_admin, OPS_URL, offset=25)
    completa = await pedir(cliente_admin, OPS_URL, limit=200)

    assert (primera["total"], primera["limit"], len(primera["items"])) == (30, 25, 25)
    assert (segunda["offset"], len(segunda["items"])) == (25, 5)
    assert ids_de(primera) + ids_de(segunda) == ids  # la de T0 primero: at DESC
    assert (completa["limit"], len(completa["items"])) == (200, 30)


async def test_los_trabajos_paginan_25_por_defecto_y_no_repiten_ni_omiten_filas(
    session: AsyncSession, cliente_admin: ClienteAdmin
) -> None:
    ids = await sembrar_muchos_jobs(session, 30)

    primera = await pedir(cliente_admin, JOBS_URL)
    segunda = await pedir(cliente_admin, JOBS_URL, offset=25, limit=25)

    assert (primera["total"], primera["limit"], len(primera["items"])) == (30, 25, 25)
    assert ids_de(primera) + ids_de(segunda) == ids
    assert {i["percent"] for i in primera["items"]} == {100}


# Solo lectura -----------------------------------------------------------------------------------


async def test_leer_la_bitacora_y_los_trabajos_no_escribe_crypto_ops(
    session: AsyncSession, cliente_admin: ClienteAdmin, ops: OpsSembradas, jobs: JobsSembrados
) -> None:
    antes = await contar_ops(session)

    await pedir(cliente_admin, OPS_URL)
    await pedir(cliente_admin, OPS_URL, verb="rotate", q="phone")
    await pedir(cliente_admin, JOBS_URL)
    await pedir(cliente_admin, JOBS_URL, status="running")

    assert antes == 6
    assert await contar_ops(session) == antes


# Roles, no-store y limite -----------------------------------------------------------------------


@pytest.mark.parametrize("ruta", [OPS_URL, JOBS_URL])
async def test_las_respuestas_llevan_no_store(
    cliente_admin: ClienteAdmin, ops: OpsSembradas, jobs: JobsSembrados, ruta: str
) -> None:
    r = await cliente_admin.get(ruta)

    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("ruta", [OPS_URL, JOBS_URL])
@pytest.mark.parametrize("rol", ["coach", "member"])
async def test_coach_y_socio_reciben_403(
    app_http: object, usuario_real: CrearUsuario, cabeceras: Cabeceras, ruta: str, rol: str
) -> None:
    quien = await usuario_real(rol)

    r = await app_http.get(ruta, headers=cabeceras(quien))  # type: ignore[attr-defined]

    assert r.status_code == 403, r.text


@pytest.mark.parametrize("ruta", [OPS_URL, JOBS_URL])
async def test_sin_token_401(app_http: object, ruta: str) -> None:
    r = await app_http.get(ruta)  # type: ignore[attr-defined]

    assert r.status_code == 401, r.text


async def test_la_121_del_minuto_da_429_y_las_dos_rutas_comparten_staff_read(
    cliente_admin: ClienteAdmin, ops: OpsSembradas, jobs: JobsSembrados
) -> None:
    for numero in range(LIMITE_DE_LECTURAS):
        ruta = OPS_URL if numero % 2 == 0 else JOBS_URL
        r = await cliente_admin.get(ruta, limit=1)
        assert r.status_code == 200, (numero, r.text)

    for ruta in (OPS_URL, JOBS_URL):
        r = await cliente_admin.get(ruta, limit=1)

        assert r.status_code == 429, (ruta, r.text)
        assert r.json()["error"]["code"] == "rate_limited"
        assert int(r.headers["retry-after"]) >= 1


# Sin material -----------------------------------------------------------------------------------


@pytest.mark.parametrize("ruta", [OPS_URL, JOBS_URL])
async def test_las_respuestas_no_traen_material_ni_referencias(
    cliente_admin: ClienteAdmin, ops: OpsSembradas, jobs: JobsSembrados, ruta: str
) -> None:
    r = await cliente_admin.get(ruta, limit=200)

    assert r.status_code == 200, r.text
    for prohibido in PROHIBIDAS_EN_TEXTO:
        assert prohibido not in r.text, prohibido

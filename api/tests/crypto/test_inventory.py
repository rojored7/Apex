"""Inventario de llaves sin material (S6-B1, US-143; S6-D13, S6-D14, S6-D54). Rojo B1.

`inventory.list_keys(session, filters, page)`, `inventory.summary(session)`,
`inventory.records_count(session, data_class)` e `inventory.age_days(created_at, rotated_at, now)`
sobre la base de prueba (sin HTTP: el contrato HTTP está en `test_router_keys.py`).

- campos de `CryptoKeyOut` (D13) y ninguno de material o referencia;
- `records_count`: por `discovery.encrypted_columns` (`member.document`), por el puerto
  `Reencryptor` (gana sobre las columnas), nulo sin columnas ni puerto (`kek.backup`,
  `audit.signature`);
- filtros `purpose`, `state`, `provider`, `data_class` y `q` (sobre `data_class`, sin comodines);
- paginación y orden estable `data_class, purpose, version DESC`;
- `summary`: `active_count`, `operations_today` (día de Bogotá, no de UTC), `running_jobs` y
  `provider` (`names` de las filas `active`, `state` de `recovery.current_state()`, S6-D54);
- no escribe `crypto_ops` y la consulta usa columnas explícitas (nunca `wrapped_material`).
`age_days` se fija como los días completos entre `created_at` y `rotated_at` (o `now` si la llave
sigue sin rotar), nunca negativos.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID
from app.core.crypto import inventory, oplog, recovery
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoJob, CryptoKey, CryptoOp
from app.core.crypto.reencryptor import register_reencryptor
from app.core.crypto.registry import REGISTRY, DataClassSpec, override_registry
from app.core.crypto.schemas import CryptoKeyOut, KeysFilters, KeysSummary
from app.core.pagination import PageParams
from app.main import load_module_services
from tests.conftest import T0
from tests.crypto.conftest import ReencryptorDoble, llaves_mixtas
from tests.factories.members import make_members
from tests.factories.triggers import disable_user_sql, rearm_always_sql

CAMPOS_D13 = {
    "id",
    "purpose",
    "data_class",
    "algorithm",
    "version",
    "state",
    "provider",
    "created_at",
    "rotated_at",
    "age_days",
    "records_count",
}
ADJUNTOS = "attachment.sensitive"
INICIO_DEL_DIA_BOGOTA = datetime(2026, 10, 21, 5, 0, 0, tzinfo=UTC)
"""`T0` es el 21 de octubre de 2026, 15:00 UTC = 10:00 en Bogotá (UTC-5): el día de Bogotá
empieza a las 05:00 UTC, no a las 00:00 UTC."""

pytestmark = pytest.mark.usefixtures("reloj")


@pytest.fixture(autouse=True)
def _servicios_cargados() -> None:
    load_module_services()  # `Base.metadata` con las tablas cifradas de los módulos


@pytest.fixture(autouse=True)
def _estado_del_proveedor_limpio() -> Iterator[None]:
    recovery.reset()
    try:
        yield
    finally:
        recovery.reset()


@pytest.fixture
async def llaves(
    session: AsyncSession, bus_listo: object, proveedor_local: LocalFileProvider
) -> dict[str, CryptoKey]:
    """Las ocho llaves del bus más la `sign` y la `decrypt_only` de `llaves_mixtas`."""
    return await llaves_mixtas(session, proveedor_local)


async def _todas(session: AsyncSession, filtros: KeysFilters | None = None) -> list[CryptoKeyOut]:
    pagina = await inventory.list_keys(session, filtros or KeysFilters(), PageParams(limit=200))
    return list(pagina.items)


async def _sql(session: AsyncSession, consulta: str) -> Any:
    return await session.scalar(text(consulta))


async def _vaciar_ops(session: AsyncSession) -> None:
    await session.execute(text(disable_user_sql("crypto.crypto_ops")))
    await session.execute(text("DELETE FROM crypto.crypto_ops"))
    await session.execute(text(rearm_always_sql("crypto.crypto_ops")))


async def _fila_sign(
    session: AsyncSession,
    proveedor: LocalFileProvider,
    *,
    provider: str,
    version: int,
    state: str,
) -> CryptoKey:
    fila = CryptoKey(
        purpose="sign",
        data_class="audit.signature",
        algorithm="Ed25519",
        provider=provider,
        version=version,
        state=state,
        wrapped_material=proveedor.sign_key_ref().encode("ascii"),
        public_key=await proveedor.sign_public_key(),
        created_by=SYSTEM_USER_ID,
    )
    session.add(fila)
    await session.flush()
    return fila


# age_days (pura) -------------------------------------------------------------------------------


def test_age_days_cuenta_dias_completos_desde_la_creacion_si_nunca_roto() -> None:
    creada = T0 - timedelta(days=10, hours=23)

    assert inventory.age_days(creada, None, T0) == 10


def test_age_days_de_una_llave_rotada_se_congela_en_la_rotacion() -> None:
    creada = T0 - timedelta(days=40)
    rotada = creada + timedelta(days=4, hours=5)

    assert inventory.age_days(creada, rotada, T0) == 4


def test_age_days_nunca_es_negativo() -> None:
    assert inventory.age_days(T0 + timedelta(days=2), None, T0) == 0


def test_age_days_de_una_llave_recien_creada_es_cero() -> None:
    assert inventory.age_days(T0, None, T0) == 0


# Forma de cada fila (D13) ----------------------------------------------------------------------


async def test_cada_llave_trae_los_campos_de_d13_y_ninguno_mas(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    items = await _todas(session)

    assert len(items) == 11  # S6-C1: +1 por la DEK de `attachment.sensitive` (antes 10)
    for item in items:
        assert set(item.model_dump()) == CAMPOS_D13
        assert item.age_days >= 0
    assert {i.id for i in items} >= {llaves["sign"].id, llaves["decrypt_only"].id}


async def test_el_inventario_no_expone_material_ni_la_referencia_de_las_firmas(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    items = await _todas(session)

    volcado = " ".join(str(i.model_dump(mode="json")) for i in items)
    assert "wrapped_material" not in volcado
    assert "apex-sign-audit" not in volcado and "local:" not in volcado
    assert "apxw1" not in volcado and "vault:" not in volcado
    assert "public_key" not in volcado


async def test_rotated_at_es_nulo_en_la_activa_y_trae_fecha_en_la_rotada(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    fecha = T0 - timedelta(days=3)
    anterior = llaves["decrypt_only"]
    anterior.rotated_at = fecha
    await session.flush()

    items = {i.id: i for i in await _todas(session)}

    assert items[anterior.id].rotated_at == fecha
    assert items[llaves["sign"].id].rotated_at is None


# records_count (D13, D14) ----------------------------------------------------------------------


async def test_records_count_de_una_clase_con_columnas_cuenta_por_el_registro(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    await make_members(session, 3)
    esperado = await _sql(session, "SELECT count(*) FROM members.members")
    assert esperado >= 3

    por_clase = {(i.data_class, i.purpose): i for i in await _todas(session)}

    assert por_clase[("member.document", "encrypt")].records_count == esperado
    assert await inventory.records_count(session, "member.document") == esperado


async def test_la_fila_index_de_una_clase_comparte_el_conteo_de_la_clase(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    await make_members(session, 2)

    por_clase = {(i.data_class, i.purpose): i for i in await _todas(session)}

    assert (
        por_clase[("member.document", "index")].records_count
        == por_clase[("member.document", "encrypt")].records_count
    )


async def test_records_count_es_nulo_para_firma_y_sin_columnas_ni_puerto(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    sin_clase = CryptoKey(
        purpose="encrypt",
        data_class="kek.backup",
        algorithm="A256GCM",
        provider="local",
        version=1,
        state="active",
        wrapped_material=b"x",
        created_by=SYSTEM_USER_ID,
    )
    session.add(sin_clase)
    await session.flush()

    por_clase = {i.data_class: i for i in await _todas(session)}

    assert por_clase["audit.signature"].records_count is None
    assert por_clase["kek.backup"].records_count is None
    assert await inventory.records_count(session, "audit.signature") is None
    assert await inventory.records_count(session, "kek.backup") is None


async def test_records_count_de_una_clase_con_puerto_sale_de_count_total(
    session: AsyncSession,
    llaves: dict[str, CryptoKey],
    reencryptor_doble: ReencryptorDoble,
) -> None:
    clase_sin_columnas = DataClassSpec(ADJUNTOS, True, None, False, "str", ())
    # S6-C1: `ensure_keys` ya creó la DEK de `attachment.sensitive` (registro de C1); no se duplica.
    await session.flush()
    reencryptor_doble.total = 7
    register_reencryptor(ADJUNTOS, reencryptor_doble)

    with override_registry({**REGISTRY, ADJUNTOS: clase_sin_columnas}):
        por_clase = {i.data_class: i for i in await _todas(session)}

    assert por_clase[ADJUNTOS].records_count == 7
    assert reencryptor_doble.nombres().count("count_total") == 1


async def test_el_puerto_gana_sobre_las_columnas_del_registro(
    session: AsyncSession,
    llaves: dict[str, CryptoKey],
    reencryptor_doble: ReencryptorDoble,
) -> None:
    await make_members(session, 2)
    reencryptor_doble.total = 99
    register_reencryptor("member.document", reencryptor_doble)

    assert await inventory.records_count(session, "member.document") == 99


# Filtros ---------------------------------------------------------------------------------------


async def test_filtra_por_purpose(session: AsyncSession, llaves: dict[str, CryptoKey]) -> None:
    # S6-C1: 7 encrypt (antes 6) por la DEK de `attachment.sensitive`
    for purpose, cuantas in (("encrypt", 7), ("index", 3), ("sign", 1)):
        items = await _todas(session, KeysFilters(purpose=purpose))
        assert len(items) == cuantas, purpose
        assert {i.purpose for i in items} == {purpose}


async def test_filtra_por_state(session: AsyncSession, llaves: dict[str, CryptoKey]) -> None:
    anteriores = await _todas(session, KeysFilters(state="decrypt_only"))
    activas = await _todas(session, KeysFilters(state="active"))

    assert [i.id for i in anteriores] == [llaves["decrypt_only"].id]
    assert len(activas) == 10  # S6-C1: +1 (antes 9)
    assert await _todas(session, KeysFilters(state="retired")) == []


async def test_filtra_por_provider(
    session: AsyncSession, llaves: dict[str, CryptoKey], proveedor_local: LocalFileProvider
) -> None:
    abierta = await _fila_sign(
        session, proveedor_local, provider="openbao", version=2, state="decrypt_only"
    )

    en_openbao = await _todas(session, KeysFilters(provider="openbao"))
    en_local = await _todas(session, KeysFilters(provider="local"))

    assert [i.id for i in en_openbao] == [abierta.id]
    assert len(en_local) == 11  # S6-C1: +1 (antes 10)


async def test_filtra_por_data_class_exacta(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    items = await _todas(session, KeysFilters(data_class="member.email"))

    assert {(i.purpose, i.version, i.state) for i in items} == {
        ("encrypt", 1, "active"),
        ("encrypt", 2, "decrypt_only"),
        ("index", 1, "active"),
    }
    assert await _todas(session, KeysFilters(data_class="member")) == []


async def test_q_busca_en_data_class_sin_distinguir_mayusculas(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    items = await _todas(session, KeysFilters(q="PHONE"))

    assert {i.data_class for i in items} == {"member.phone"}
    assert len(items) == 2


async def test_q_trata_porcentaje_y_guion_bajo_como_texto_y_no_como_comodin(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    todas = await _todas(session)

    assert await _todas(session, KeysFilters(q="%")) == []
    con_guion = await _todas(session, KeysFilters(q="_"))
    assert {i.id for i in con_guion} == {i.id for i in todas if "_" in i.data_class}
    assert 0 < len(con_guion) < len(todas)


async def test_los_filtros_se_combinan_con_y(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    items = await _todas(session, KeysFilters(purpose="encrypt", state="active", q="member"))

    assert len(items) == 5
    assert {i.purpose for i in items} == {"encrypt"} and {i.state for i in items} == {"active"}


# Paginación y orden ----------------------------------------------------------------------------


async def test_el_total_respeta_los_filtros_y_no_la_pagina(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    pagina = await inventory.list_keys(
        session, KeysFilters(purpose="index"), PageParams(limit=2, offset=0)
    )

    assert (pagina.total, len(pagina.items), pagina.limit, pagina.offset) == (3, 2, 2, 0)


async def test_la_pagina_por_defecto_es_de_25_y_devuelve_limit_y_offset(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    pagina = await inventory.list_keys(session, KeysFilters(), PageParams())

    assert (pagina.limit, pagina.offset, pagina.total, len(pagina.items)) == (25, 0, 11, 11)


async def test_un_offset_pasado_el_final_da_pagina_vacia_con_el_total(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    pagina = await inventory.list_keys(session, KeysFilters(), PageParams(limit=5, offset=40))

    assert (pagina.items, pagina.total, pagina.offset) == ([], 11, 40)


async def test_el_orden_es_data_class_purpose_y_version_descendente(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    items = await _todas(session)

    clave = [(i.data_class, i.purpose, -i.version) for i in items]
    assert clave == sorted(clave)
    emails = [(i.purpose, i.version) for i in items if i.data_class == "member.email"]
    assert emails == [("encrypt", 2), ("encrypt", 1), ("index", 1)]


async def test_paginar_de_a_tres_recorre_el_mismo_orden_sin_repetir_ni_omitir(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    completo = [i.id for i in await _todas(session)]

    recorrido: list[Any] = []
    for desde in range(0, 12, 3):
        pagina = await inventory.list_keys(
            session, KeysFilters(), PageParams(limit=3, offset=desde)
        )
        recorrido.extend(i.id for i in pagina.items)

    assert recorrido == completo
    assert len(set(recorrido)) == len(recorrido) == 11


# Solo lectura y columnas explícitas ------------------------------------------------------------


async def test_listar_y_resumir_no_escriben_crypto_ops(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    antes = await _sql(session, "SELECT count(*) FROM crypto.crypto_ops")
    oplog.reset_buffer()

    await inventory.list_keys(session, KeysFilters(), PageParams())
    await inventory.summary(session)
    await session.flush()

    assert oplog.pending_rows() == []
    assert await _sql(session, "SELECT count(*) FROM crypto.crypto_ops") == antes


async def test_la_consulta_usa_columnas_explicitas_y_nunca_wrapped_material(
    session: AsyncSession, llaves: dict[str, CryptoKey], contador_de_consultas: Any
) -> None:
    with contador_de_consultas.midiendo():
        await inventory.list_keys(session, KeysFilters(), PageParams())
        await inventory.summary(session)

    tocan_llaves = [s for s in contador_de_consultas.sentencias if "crypto_keys" in s]
    assert tocan_llaves, "la consulta no leyó crypto.crypto_keys"
    for sql in tocan_llaves:
        assert "wrapped_material" not in sql, sql
        assert "public_key" not in sql, sql
        assert "*" not in sql.split("FROM")[0], sql


# summary ---------------------------------------------------------------------------------------


async def test_summary_tiene_los_campos_de_d13(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    resumen = await inventory.summary(session)

    assert isinstance(resumen, KeysSummary)
    assert set(resumen.model_dump()) == {
        "active_count",
        "operations_today",
        "running_jobs",
        "provider",
    }
    assert set(resumen.provider.model_dump()) == {"names", "state"}


async def test_active_count_cuenta_las_activas_de_todo_el_inventario(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    resumen = await inventory.summary(session)

    # 6 encrypt (S6-C1: +attachment.sensitive) + 3 index + 1 sign; la decrypt_only no cuenta
    assert resumen.active_count == 10
    assert resumen.active_count == await _sql(
        session, "SELECT count(*) FROM crypto.crypto_keys WHERE state = 'active'"
    )


async def _op(session: AsyncSession, cuando: datetime) -> None:
    session.add(
        CryptoOp(
            at=cuando,
            user_id=SYSTEM_USER_ID,
            verb="sign",
            data_class="audit.signature",
            result="ok",
            created_by=SYSTEM_USER_ID,
        )
    )


async def test_operations_today_cuenta_el_dia_de_bogota_y_no_el_de_utc(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    await _vaciar_ops(session)
    for cuando in (
        INICIO_DEL_DIA_BOGOTA - timedelta(hours=2),  # 03:00 UTC: mismo día UTC, ayer en Bogotá
        INICIO_DEL_DIA_BOGOTA - timedelta(seconds=1),  # el último segundo de ayer
        INICIO_DEL_DIA_BOGOTA,  # medianoche de Bogotá: hoy
        INICIO_DEL_DIA_BOGOTA + timedelta(hours=9),  # 14:00 UTC: hoy
        T0,  # ahora
    ):
        await _op(session, cuando)
    await session.flush()

    resumen = await inventory.summary(session)

    assert resumen.operations_today == 3


async def test_operations_today_es_cero_sin_operaciones(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    await _vaciar_ops(session)

    assert (await inventory.summary(session)).operations_today == 0


async def test_running_jobs_cuenta_solo_los_trabajos_en_ejecucion(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    for clase, estado in (
        ("member.document", "running"),
        ("member.phone", "done"),
        ("member.email", "failed"),
    ):
        session.add(
            CryptoJob(
                kind="rotate",
                data_class=clase,
                status=estado,
                total=10,
                done=10 if estado == "done" else 3,
                created_by=SYSTEM_USER_ID,
            )
        )
    await session.flush()

    assert (await inventory.summary(session)).running_jobs == 1


async def test_provider_names_son_los_de_las_filas_active_sin_repetir(
    session: AsyncSession, llaves: dict[str, CryptoKey], proveedor_local: LocalFileProvider
) -> None:
    # una `decrypt_only` en openbao no cuenta: solo las `active` dicen quién custodia hoy (S6-D54)
    await _fila_sign(session, proveedor_local, provider="openbao", version=2, state="decrypt_only")

    assert (await inventory.summary(session)).provider.names == ["local"]


async def test_provider_names_lista_ambos_cuando_hay_activas_en_los_dos(
    session: AsyncSession, bus_listo: object, proveedor_local: LocalFileProvider
) -> None:
    await _fila_sign(session, proveedor_local, provider="openbao", version=1, state="active")

    assert (await inventory.summary(session)).provider.names == ["local", "openbao"]


@pytest.mark.parametrize("estado", ["ok", "sealed", "unreachable"])
async def test_provider_state_es_el_de_recovery_current_state(
    session: AsyncSession, llaves: dict[str, CryptoKey], estado: Any
) -> None:
    recovery.observe(estado)

    resumen = await inventory.summary(session)

    assert resumen.provider.state == recovery.current_state() == estado


async def test_provider_state_es_unknown_antes_de_la_primera_observacion(
    session: AsyncSession, llaves: dict[str, CryptoKey]
) -> None:
    assert (await inventory.summary(session)).provider.state == "unknown"

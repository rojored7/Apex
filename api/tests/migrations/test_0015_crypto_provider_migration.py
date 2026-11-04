"""`0015_crypto_provider_migration` (S5-W0-3; S5-D4, S5-D18).

Padre `0014_audit_log_triggers_always`; es head. No crea tablas ni columnas: reemplaza con
`CREATE OR REPLACE FUNCTION` la guarda `crypto.guard_keys_update()` de `0003` para que el
propietario (`tools`) pueda:
- migrar una llave de proveedor: `local <-> openbao` con `wrapped_material` nuevo;
- re-envolver (rewrap): solo `wrapped_material`, mismo proveedor.
Nada más cambia: `id`, `purpose`, `data_class`, `algorithm`, `version`, `created_*` quedan
fijos, `state` no se mueve junto con `wrapped_material`, el material nunca queda vacío y las
filas `sign` migran y se re-envuelven igual que las demás (S5-D18 ampliada).
Los dos triggers siguen en `ENABLE ALWAYS`. `apex_api` y `apex_worker`
siguen sin `UPDATE` de `provider` ni de `wrapped_material` (solo `tools`, propietario, migra).

`downgrade`: la función recupera el texto literal de `0003` (se compara con el `prosrc` que
`0003` declara, con `{ERR}` resuelto).

Las filas de cada prueba usan una `data_class` única y se borran al terminar con el ayudante
`tests.factories.triggers` (apagar, borrar y encender por nombre con `ALWAYS`).
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.factories.triggers import CRYPTO_TRIGGERS, disable_user_sql, rearm_always_sql
from tests.migrations.conftest import RolesDb
from tests.migrations.test_db_grants import PRIVACION, como, intentar

REVISION = "0015_crypto_provider_migration"
PADRE = "0014_audit_log_triggers_always"
REVISION_0003 = "0003_crypto"
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
CHECK_VIOLATION = "23514"  # `crypto.*` usa ERRCODE check_violation (0003)
TABLA = "crypto.crypto_keys"
GUARDAS = CRYPTO_TRIGGERS[TABLA]
MATERIAL_VIEJO = b"\x01\x02\x03"
MATERIAL_NUEVO = b"\x0a\x0b\x0c\x0d"


# Ayudas -----------------------------------------------------------------------------------------


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _correr(url: str, sql: str, *args: Any) -> list[asyncpg.Record]:
    async def correr() -> list[asyncpg.Record]:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            return list(await conexion.fetch(sql, *args))
        finally:
            await conexion.close()

    return asyncio.run(correr())


def _error(url: str, sql: str, *args: Any) -> asyncpg.PostgresError | None:
    """El error de la sentencia, o `None` si PostgreSQL la aceptó."""
    try:
        _correr(url, sql, *args)
    except asyncpg.PostgresError as error:
        return error
    return None


def _clase() -> str:
    """`data_class` única que cumple `^[a-z_]+\\.[a-z_]+$` (sin dígitos)."""
    letras = "".join(chr(ord("a") + int(c, 16)) for c in uuid4().hex[:12])
    return f"prueba.{letras}"


@dataclass(frozen=True)
class Llave:
    id: UUID
    data_class: str


def _insertar(
    url: str,
    *,
    purpose: str = "encrypt",
    algorithm: str = "A256GCM",
    provider: str = "local",
    state: str = "active",
) -> Llave:
    llave = Llave(uuid4(), _clase())
    _correr(
        url,
        "INSERT INTO crypto.crypto_keys (id, created_by, purpose, data_class, algorithm, "
        "provider, version, state, wrapped_material) "
        "VALUES ($1, $2, $3, $4, $5, $6, 1, $7, $8)",
        llave.id,
        SYSTEM_USER_ID,
        purpose,
        llave.data_class,
        algorithm,
        provider,
        state,
        MATERIAL_VIEJO,
    )
    return llave


def _borrar(url: str, llave: Llave) -> None:
    """Limpieza: apaga, borra por `id` y vuelve a encender por nombre con `ENABLE ALWAYS`."""

    async def correr() -> None:
        conexion = await asyncpg.connect(_dsn(url))
        try:
            await conexion.execute(disable_user_sql(TABLA))
            await conexion.execute("DELETE FROM crypto.crypto_keys WHERE id = $1", llave.id)
            await conexion.execute(rearm_always_sql(TABLA))
        finally:
            await conexion.close()

    asyncio.run(correr())


def _fila(url: str, llave: Llave) -> asyncpg.Record:
    return _correr(
        url,
        "SELECT provider, wrapped_material, state, version, data_class "
        "FROM crypto.crypto_keys WHERE id = $1",
        llave.id,
    )[0]


def _migrar(
    url: str, llave: Llave, proveedor: str, material: bytes
) -> asyncpg.PostgresError | None:
    return _error(
        url,
        "UPDATE crypto.crypto_keys SET provider = $2, wrapped_material = $3 WHERE id = $1",
        llave.id,
        proveedor,
        material,
    )


def _definicion(url: str) -> str:
    """`pg_get_functiondef` normalizado en espacios (cuerpo y cabecera de la guarda)."""
    texto = _correr(
        url, "SELECT pg_get_functiondef('crypto.guard_keys_update()'::regprocedure) AS d"
    )[0]["d"]
    return " ".join(str(texto).split())


def _cuerpo(url: str) -> str:
    fuente = _correr(
        url, "SELECT prosrc FROM pg_proc WHERE oid = 'crypto.guard_keys_update()'::regprocedure"
    )[0]["prosrc"]
    return " ".join(str(fuente).split())


def _cuerpo_de_0003(alembic_config: Config) -> str:
    """El cuerpo literal que `0003` crea, con `{ERR}` resuelto y espacios normalizados."""
    revision = ScriptDirectory.from_config(alembic_config).get_revision(REVISION_0003)
    assert revision is not None and revision.module is not None
    texto = revision.module.__file__
    assert texto is not None
    with open(texto, encoding="utf-8") as archivo:
        fuente = archivo.read()
    inicio = fuente.index("CREATE FUNCTION crypto.guard_keys_update()")
    abre = fuente.index("$$", inicio) + 2
    cierra = fuente.index("$$", abre)
    cuerpo = fuente[abre:cierra].replace("{ERR}", revision.module.ERR)
    return " ".join(cuerpo.split())


def _estados(url: str) -> dict[str, str]:
    filas = _correr(
        url,
        "SELECT tgname, tgenabled::text AS estado FROM pg_trigger "
        "WHERE NOT tgisinternal AND tgname = ANY($1::text[])",
        list(GUARDAS),
    )
    return {f["tgname"]: f["estado"] for f in filas}


@pytest.fixture
def base(alembic_config: Config, migrated_database: str) -> str:
    """La base migrada a head; falla con "no existe la revisión" hasta que exista `0015`."""
    scripts = ScriptDirectory.from_config(alembic_config)
    try:
        revision = scripts.get_revision(REVISION)
    except Exception as error:  # alembic.util.CommandError o ResolutionError
        pytest.fail(f"no existe la revisión {REVISION}: {type(error).__name__}")
    if revision is None:
        pytest.fail(f"no existe la revisión {REVISION}")
    return migrated_database


@pytest.fixture
def llaves(base: str) -> Iterator[list[Llave]]:
    """Registro de las llaves que crea la prueba; se borran todas al terminar."""
    creadas: list[Llave] = []
    yield creadas
    for llave in creadas:
        _borrar(base, llave)


def _nueva(base: str, llaves: list[Llave], **campos: str) -> Llave:
    llave = _insertar(base, **campos)
    llaves.append(llave)
    return llave


# Revisión ---------------------------------------------------------------------------------------


def test_la_revision_existe_cuelga_de_0014_y_es_head(alembic_config: Config) -> None:
    scripts = ScriptDirectory.from_config(alembic_config)
    try:
        revision = scripts.get_revision(REVISION)
    except Exception as error:
        pytest.fail(f"no existe la revisión {REVISION}: {type(error).__name__}")
    assert revision is not None and revision.down_revision == PADRE
    assert scripts.get_heads() == [REVISION]


# Lo permitido -----------------------------------------------------------------------------------


def test_migrar_de_local_a_openbao_con_material_nuevo_se_acepta(
    base: str, llaves: list[Llave]
) -> None:
    llave = _nueva(base, llaves, provider="local")
    error = _migrar(base, llave, "openbao", MATERIAL_NUEVO)
    assert error is None, error
    fila = _fila(base, llave)
    assert fila["provider"] == "openbao"
    assert bytes(fila["wrapped_material"]) == MATERIAL_NUEVO
    assert fila["state"] == "active" and fila["version"] == 1


def test_migrar_de_openbao_a_local_se_acepta_reversa_de_s5_d18(
    base: str, llaves: list[Llave]
) -> None:
    llave = _nueva(base, llaves, provider="openbao")
    error = _migrar(base, llave, "local", MATERIAL_NUEVO)
    assert error is None, error
    fila = _fila(base, llave)
    assert fila["provider"] == "local"
    assert bytes(fila["wrapped_material"]) == MATERIAL_NUEVO


@pytest.mark.parametrize("proveedor", ["local", "openbao"])
def test_cambiar_solo_wrapped_material_con_el_mismo_proveedor_rewrap_se_acepta(
    base: str, llaves: list[Llave], proveedor: str
) -> None:
    llave = _nueva(base, llaves, provider=proveedor)
    error = _error(
        base,
        "UPDATE crypto.crypto_keys SET wrapped_material = $2 WHERE id = $1",
        llave.id,
        MATERIAL_NUEVO,
    )
    assert error is None, error
    fila = _fila(base, llave)
    assert fila["provider"] == proveedor and bytes(fila["wrapped_material"]) == MATERIAL_NUEVO


def test_migrar_una_llave_decrypt_only_se_acepta(base: str, llaves: list[Llave]) -> None:
    """Las llaves viejas (solo descifran) también viajan al nuevo proveedor."""
    llave = _nueva(base, llaves, provider="local", state="decrypt_only")
    assert _migrar(base, llave, "openbao", MATERIAL_NUEVO) is None


def test_el_cambio_de_estado_solo_sigue_permitido(base: str, llaves: list[Llave]) -> None:
    """Lo que `0003` ya permitía no se pierde: `active -> decrypt_only` sin tocar el material."""
    llave = _nueva(base, llaves)
    error = _error(
        base,
        "UPDATE crypto.crypto_keys SET state = 'decrypt_only', rotated_at = now(), "
        "rotated_by = $2 WHERE id = $1",
        llave.id,
        SYSTEM_USER_ID,
    )
    assert error is None, error


# Lo rechazado -----------------------------------------------------------------------------------


def _rechazado(error: asyncpg.PostgresError | None) -> None:
    assert error is not None, "la guarda aceptó un cambio prohibido"
    assert error.sqlstate == CHECK_VIOLATION
    assert error.message.startswith("crypto.crypto_keys"), error.message


def test_cambiar_provider_sin_cambiar_wrapped_material_se_rechaza(
    base: str, llaves: list[Llave]
) -> None:
    """Una migración sin material nuevo dejaría el blob del proveedor viejo bajo el nuevo."""
    llave = _nueva(base, llaves, provider="local")
    _rechazado(
        _error(
            base,
            "UPDATE crypto.crypto_keys SET provider = 'openbao' WHERE id = $1",
            llave.id,
        )
    )
    assert _fila(base, llave)["provider"] == "local"


def test_state_junto_con_wrapped_material_se_rechaza(base: str, llaves: list[Llave]) -> None:
    llave = _nueva(base, llaves)
    _rechazado(
        _error(
            base,
            "UPDATE crypto.crypto_keys SET state = 'decrypt_only', wrapped_material = $2 "
            "WHERE id = $1",
            llave.id,
            MATERIAL_NUEVO,
        )
    )
    fila = _fila(base, llave)
    assert fila["state"] == "active" and bytes(fila["wrapped_material"]) == MATERIAL_VIEJO


def test_state_junto_con_una_migracion_de_proveedor_se_rechaza(
    base: str, llaves: list[Llave]
) -> None:
    llave = _nueva(base, llaves, provider="local")
    _rechazado(
        _error(
            base,
            "UPDATE crypto.crypto_keys SET provider = 'openbao', wrapped_material = $2, "
            "state = 'decrypt_only' WHERE id = $1",
            llave.id,
            MATERIAL_NUEVO,
        )
    )
    assert _fila(base, llave)["provider"] == "local"


@pytest.mark.parametrize(
    "asignacion",
    [
        "version = 2",
        "data_class = 'prueba.otraclase'",
        "created_by = '00000000-0000-0000-0000-0000000000ff'",
        "created_at = now() - interval '1 day'",
        "id = gen_random_uuid()",
    ],
    ids=["version", "data_class", "created_by", "created_at", "id"],
)
def test_una_migracion_valida_con_una_columna_fija_cambiada_se_rechaza(
    base: str, llaves: list[Llave], asignacion: str
) -> None:
    """Aunque el par `local -> openbao` con material nuevo sea legal, la columna fija lo anula."""
    llave = _nueva(base, llaves, provider="local")
    _rechazado(
        _error(
            base,
            "UPDATE crypto.crypto_keys SET provider = 'openbao', wrapped_material = $2, "  # noqa: S608
            f"{asignacion} WHERE id = $1",
            llave.id,
            MATERIAL_NUEVO,
        )
    )
    assert _fila(base, llave)["provider"] == "local"


@pytest.mark.parametrize("asignacion", ["version = 2", "data_class = 'prueba.otraclase'"])
def test_version_o_data_class_solos_se_rechazan(
    base: str, llaves: list[Llave], asignacion: str
) -> None:
    llave = _nueva(base, llaves)
    _rechazado(
        _error(base, f"UPDATE crypto.crypto_keys SET {asignacion} WHERE id = $1", llave.id)  # noqa: S608
    )


def test_una_fila_sign_si_se_migra_de_proveedor_con_material_nuevo(
    base: str, llaves: list[Llave]
) -> None:
    """S5-D18 ampliada: las filas `sign` migran con el resto (una KEK que no las cubra es un
    residuo peligroso)."""
    llave = _nueva(base, llaves, purpose="sign", algorithm="Ed25519", provider="local")
    assert _migrar(base, llave, "openbao", MATERIAL_NUEVO) is None
    assert _fila(base, llave)["provider"] == "openbao"


@pytest.mark.parametrize("proveedor", ["local", "openbao"])
def test_una_fila_sign_si_se_reenvuelve(base: str, llaves: list[Llave], proveedor: str) -> None:
    llave = _nueva(base, llaves, purpose="sign", algorithm="Ed25519", provider=proveedor)
    error = _error(
        base,
        "UPDATE crypto.crypto_keys SET wrapped_material = $2 WHERE id = $1",
        llave.id,
        MATERIAL_NUEVO,
    )
    assert error is None, error
    assert bytes(_fila(base, llave)["wrapped_material"]) == MATERIAL_NUEVO


def test_una_fila_sign_con_state_y_material_se_rechaza(base: str, llaves: list[Llave]) -> None:
    llave = _nueva(base, llaves, purpose="sign", algorithm="Ed25519")
    _rechazado(
        _error(
            base,
            "UPDATE crypto.crypto_keys SET state = 'decrypt_only', wrapped_material = $2 "
            "WHERE id = $1",
            llave.id,
            MATERIAL_NUEVO,
        )
    )


def test_material_vacio_se_rechaza_en_rewrap_y_en_migracion(base: str, llaves: list[Llave]) -> None:
    llave = _nueva(base, llaves, provider="local")
    _rechazado(_migrar(base, llave, "openbao", b""))
    _rechazado(
        _error(
            base,
            "UPDATE crypto.crypto_keys SET wrapped_material = $2 WHERE id = $1",
            llave.id,
            b"",
        )
    )
    assert bytes(_fila(base, llave)["wrapped_material"]) == MATERIAL_VIEJO


def test_el_mensaje_de_columna_fija_dice_que_cambian_provider_y_material(
    base: str, llaves: list[Llave]
) -> None:
    llave = _nueva(base, llaves)
    error = _error(
        base, "UPDATE crypto.crypto_keys SET data_class = 'otra.clase' WHERE id = $1", llave.id
    )
    _rechazado(error)
    assert error is not None
    assert error.message == (
        "crypto.crypto_keys: solo cambian state, rotated_*, provider y wrapped_material"
    )


def test_borrar_y_vaciar_siguen_prohibidos(base: str, llaves: list[Llave]) -> None:
    llave = _nueva(base, llaves)
    borrado = _error(base, "DELETE FROM crypto.crypto_keys WHERE id = $1", llave.id)
    assert borrado is not None and borrado.sqlstate == CHECK_VIOLATION
    assert "nunca se borran" in borrado.message
    vaciado = _error(base, "TRUNCATE crypto.crypto_keys")
    assert vaciado is not None and vaciado.sqlstate == CHECK_VIOLATION


# Triggers y función -----------------------------------------------------------------------------


def test_los_dos_triggers_de_crypto_keys_siguen_en_always(base: str) -> None:
    assert _estados(base) == dict.fromkeys(GUARDAS, "A")


def test_los_triggers_siguen_sobre_la_misma_funcion(base: str) -> None:
    filas = _correr(
        base,
        "SELECT tgname, tgfoid = 'crypto.guard_keys_update()'::regprocedure AS misma "
        "FROM pg_trigger WHERE NOT tgisinternal AND tgname = ANY($1::text[])",
        list(GUARDAS),
    )
    assert {f["tgname"]: f["misma"] for f in filas} == dict.fromkeys(GUARDAS, True)


def test_la_guarda_en_head_ya_no_es_la_de_0003(base: str, alembic_config: Config) -> None:
    """El upgrade de verdad reemplazó el cuerpo (no es el literal de `0003`)."""
    assert _cuerpo(base) != _cuerpo_de_0003(alembic_config)
    assert "openbao" in _cuerpo(base)


def test_la_guarda_sigue_siendo_invoker_y_sin_search_path_abierto(base: str) -> None:
    fila = _correr(
        base,
        "SELECT prosecdef, provolatile::text AS v FROM pg_proc "
        "WHERE oid = 'crypto.guard_keys_update()'::regprocedure",
    )[0]
    assert fila["prosecdef"] is False, "la guarda no debe ser SECURITY DEFINER"


# Ciclo ------------------------------------------------------------------------------------------


def test_downgrade_restaura_el_cuerpo_de_0003_y_el_upgrade_vuelve_a_la_nueva(
    alembic_config: Config, base: str
) -> None:
    literal_0003 = _cuerpo_de_0003(alembic_config)
    nueva = _definicion(base)
    llave = _insertar(base, provider="local")
    try:
        command.downgrade(alembic_config, PADRE)
        assert _cuerpo(base) == literal_0003
        assert _definicion(base) != nueva, "el downgrade no cambió la función"
        assert _estados(base) == dict.fromkeys(GUARDAS, "A"), "0014 los deja en ALWAYS"
        # Con el texto de 0003 la migración de proveedor vuelve a estar prohibida.
        _rechazado(_migrar(base, llave, "openbao", MATERIAL_NUEVO))
    finally:
        command.upgrade(alembic_config, "head")
        _borrar(base, llave)
    assert _definicion(base) == nueva
    assert _estados(base) == dict.fromkeys(GUARDAS, "A")


# Quién puede (sobre `apex_roles`) ---------------------------------------------------------------


@pytest.mark.parametrize("rol", ["apex_api", "apex_worker"])
@pytest.mark.parametrize("columna", ["provider", "wrapped_material"])
def test_los_roles_de_aplicacion_no_pueden_hacer_update_de_provider_ni_de_material(
    apex_roles: RolesDb, rol: str, columna: str
) -> None:
    valor = "'openbao'" if columna == "provider" else "'\\x00'::bytea"
    error = intentar(como(apex_roles, rol), f"UPDATE crypto.crypto_keys SET {columna} = {valor}")  # noqa: S608
    assert error is not None and error.sqlstate == PRIVACION, f"{rol} no debe poder {columna}"


def test_el_propietario_puede_migrar_el_proveedor_sobre_apex_roles(apex_roles: RolesDb) -> None:
    """Solo `tools` (propietario) migra: la prueba lo ejerce con el propietario de `apex_roles`."""
    llave = uuid4()
    clase = _clase()
    dsn = apex_roles.dsn()

    async def correr() -> asyncpg.PostgresError | None:
        conexion = await asyncpg.connect(dsn)
        try:
            await conexion.execute(
                "INSERT INTO crypto.crypto_keys (id, created_by, purpose, data_class, algorithm, "
                "provider, version, state, wrapped_material) VALUES ($1, $2, 'encrypt', $3, "
                "'A256GCM', 'local', 1, 'active', $4)",
                llave,
                SYSTEM_USER_ID,
                clase,
                MATERIAL_VIEJO,
            )
            try:
                await conexion.execute(
                    "UPDATE crypto.crypto_keys SET provider = 'openbao', wrapped_material = $2 "
                    "WHERE id = $1",
                    llave,
                    MATERIAL_NUEVO,
                )
            except asyncpg.PostgresError as error:
                return error
            return None
        finally:
            await conexion.execute(disable_user_sql(TABLA))
            await conexion.execute("DELETE FROM crypto.crypto_keys WHERE id = $1", llave)
            await conexion.execute(rearm_always_sql(TABLA))
            await conexion.close()

    error = asyncio.run(correr())
    assert error is None, error


# Limpieza de nombres no usados por flake -------------------------------------------------------

_ = re  # `re` queda importado para ampliar los controles del Verde sin tocar los imports

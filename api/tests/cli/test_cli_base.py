"""`app.cli_base`: base común de la capa de aplicación del CLI (S4B-B0; S4B-D28 a D31, D62, D95).

Contrato:
- los nombres que `app.cli` reexporta son los mismos objetos que los de `app.cli_base` (la
  extracción de B0 no copió nada) y `get_settings` es el único símbolo de configuración;
- `resolve_admin_actor(session, email, *, required)`: un admin activo devuelve su id; un coach,
  un admin inactivo o un correo inexistente salen con 2 y `--as: no existe un admin activo con
  ese correo` (sin distinguir cuál fue); sin correo y `required=True` sale con 2 y `--as es
  obligatorio`; sin correo y `required=False` devuelve `SYSTEM_USER_ID`;
- `crypto_runtime(settings, options)` envuelve `cli_runtime`: deja proveedor y keyring cargados
  (`current_keyring()`), cede una sesión y libera el engine al salir; con la KEK ausente sale con
  2 y un mensaje fijo sin ruta; con una DEK `active` que no se desenvuelve aborta con
  `unwrap_failed` ANTES de insertar llaves (S4B-D62, M-4);
- topes de tamaño propios (S4B-D95): `cli.py` 700 líneas, `cli_base.py` 200 y cada archivo de
  `cli_ops/` menos de 150.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Final

import pytest
import typer
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app import cli, cli_base
from app.cli_base import RuntimeOptions, crypto_runtime, resolve_admin_actor
from app.cli_ops.keys import init_keys_files, key_paths_in
from app.core import db
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import configure_keyring, current_keyring
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoKey
from app.core.crypto.provider import configure_provider
from tests.crypto.conftest import limpiar_llaves_con_commit
from tests.factories.users import make_user

SRC: Final = Path(__file__).resolve().parents[2] / "src" / "app"
CLAVE: Final = "Clave-Prueba-9Zx!"
REEXPORTADOS: Final = (
    "unit_of_work",
    "resolve_actor",
    "DB_TIMEOUTS_CHOICES",
    "RuntimeOptions",
    "runtime_options",
    "_sin_tiempos_de_espera",
    "_load_module_services",
    "cli_runtime",
    "_run",
    "reject",
    "production_guard_error",
    "get_settings",
)
SIN_ADMIN: Final = "--as: no existe un admin activo con ese correo"


# Reexportación -----------------------------------------------------------------------------


@pytest.mark.parametrize("nombre", REEXPORTADOS)
def test_cli_reexporta_el_mismo_objeto_que_cli_base(nombre: str) -> None:
    assert getattr(cli, nombre) is getattr(cli_base, nombre)


def test_get_settings_de_cli_base_es_el_de_core_config() -> None:
    from app.core import config

    assert cli_base.get_settings is config.get_settings


# resolve_admin_actor -----------------------------------------------------------------------


async def test_admin_activo_devuelve_su_id(session: AsyncSession) -> None:
    admin = await make_user(session, role="admin", email="adm-base@test.apex", password=CLAVE)
    assert await resolve_admin_actor(session, "adm-base@test.apex", required=True) == admin.id


async def test_correo_con_mayusculas_y_espacios_se_normaliza(session: AsyncSession) -> None:
    admin = await make_user(session, role="admin", email="adm-norm@test.apex", password=CLAVE)
    assert await resolve_admin_actor(session, "  ADM-Norm@Test.Apex ", required=True) == admin.id


async def _sale_con_2(
    session: AsyncSession,
    email: str | None,
    capsys: pytest.CaptureFixture[str],
    *,
    required: bool,
    mensaje: str,
) -> None:
    with pytest.raises(typer.Exit) as salida:
        await resolve_admin_actor(session, email, required=required)
    assert salida.value.exit_code == 2
    err = capsys.readouterr().err
    assert mensaje in err
    if email:
        assert email not in err  # sin eco del correo


async def test_coach_activo_sale_con_2(
    session: AsyncSession, capsys: pytest.CaptureFixture[str]
) -> None:
    await make_user(session, role="coach", email="coach-base@test.apex", password=CLAVE)
    await _sale_con_2(session, "coach-base@test.apex", capsys, required=True, mensaje=SIN_ADMIN)


async def test_admin_inactivo_sale_con_2(
    session: AsyncSession, capsys: pytest.CaptureFixture[str]
) -> None:
    await make_user(
        session, role="admin", email="adm-off@test.apex", password=CLAVE, is_active=False
    )
    await _sale_con_2(session, "adm-off@test.apex", capsys, required=True, mensaje=SIN_ADMIN)


async def test_correo_inexistente_sale_con_2(
    session: AsyncSession, capsys: pytest.CaptureFixture[str]
) -> None:
    await _sale_con_2(session, "nadie@test.apex", capsys, required=True, mensaje=SIN_ADMIN)


async def test_sin_correo_y_obligatorio_sale_con_2(
    session: AsyncSession, capsys: pytest.CaptureFixture[str]
) -> None:
    await _sale_con_2(session, None, capsys, required=True, mensaje="--as es obligatorio")


async def test_sin_correo_y_opcional_devuelve_el_usuario_tecnico(session: AsyncSession) -> None:
    assert await resolve_admin_actor(session, None, required=False) == SYSTEM_USER_ID


async def test_con_correo_invalido_y_opcional_tambien_sale_con_2(
    session: AsyncSession, capsys: pytest.CaptureFixture[str]
) -> None:
    """S4B-D31: `--as` es opcional, pero si viene debe ser un admin activo."""
    await _sale_con_2(session, "nadie@test.apex", capsys, required=False, mensaje=SIN_ADMIN)


# crypto_runtime ----------------------------------------------------------------------------


@pytest.fixture
async def base_de_llaves(engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    """`crypto_keys` vacía antes y después (commit real) y proceso sin proveedor ni keyring."""
    configure_keyring(None)
    configure_provider(None)
    await limpiar_llaves_con_commit(engine)
    try:
        yield engine
    finally:
        configure_keyring(None)
        configure_provider(None)
        await limpiar_llaves_con_commit(engine)


async def _conteo_de_llaves(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return int(await conn.scalar(select(func.count()).select_from(CryptoKey)) or 0)


async def test_crypto_runtime_deja_el_keyring_disponible_y_libera_el_engine(
    base_de_llaves: AsyncEngine, settings_prueba: Settings
) -> None:
    async with crypto_runtime(settings_prueba, RuntimeOptions()) as session:
        assert isinstance(session, AsyncSession)
        llave = current_keyring().active_for("encrypt", "member.document")
        assert llave.key_id is not None
        assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    assert db._engine is None  # el engine propio se liberó
    assert await _conteo_de_llaves(base_de_llaves) > 0  # ensure_keys confirmó sus llaves


async def test_crypto_runtime_libera_el_engine_si_el_cuerpo_falla(
    base_de_llaves: AsyncEngine, settings_prueba: Settings
) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        async with crypto_runtime(settings_prueba):
            raise RuntimeError("boom")
    assert db._engine is None


async def test_kek_ausente_sale_con_2_con_mensaje_fijo_sin_ruta(
    base_de_llaves: AsyncEngine,
    settings_prueba: Settings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ausente = tmp_path / "carpeta-secreta" / "no-existe.kek"
    sin_kek = settings_prueba.model_copy(update={"CRYPTO_LOCAL_KEK_PATH": ausente})
    with pytest.raises(typer.Exit) as salida:
        async with crypto_runtime(sin_kek):
            pytest.fail("no debe ceder la sesión")  # pragma: no cover
    assert salida.value.exit_code == 2
    err = capsys.readouterr().err
    assert "proveedor de llaves" in err
    assert "carpeta-secreta" not in err and str(tmp_path) not in err
    assert db._engine is None
    assert await _conteo_de_llaves(base_de_llaves) == 0


async def test_dek_activa_que_no_se_desenvuelve_aborta_antes_de_insertar(
    base_de_llaves: AsyncEngine,
    settings_prueba: Settings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """S4B-D62: una DEK `active` envuelta con OTRA KEK no se desenvuelve; `ensure_keys` no debe
    crear llaves nuevas con la KEK equivocada."""
    otra = key_paths_in(tmp_path / "otra-kek")
    init_keys_files(otra)
    ajena = LocalFileProvider(otra.kek, otra.signing_key)
    async with async_sessionmaker(base_de_llaves, expire_on_commit=False)() as sesion:
        with actor_scope(SYSTEM_USER_ID):
            sesion.add(
                CryptoKey(
                    purpose="encrypt",
                    data_class="member.document",
                    algorithm="A256GCM",
                    provider="local",
                    version=1,
                    state="active",
                    wrapped_material=await ajena.wrap(os.urandom(32)),
                    created_by=SYSTEM_USER_ID,
                )
            )
            await sesion.commit()
    antes = await _conteo_de_llaves(base_de_llaves)
    assert antes == 1
    with pytest.raises(typer.Exit) as salida:
        async with crypto_runtime(settings_prueba):
            pytest.fail("no debe ceder la sesión")  # pragma: no cover
    assert salida.value.exit_code == 2
    assert "unwrap_failed" in capsys.readouterr().err
    assert db._engine is None
    assert await _conteo_de_llaves(base_de_llaves) == antes


# Tamaños (S4B-D95) -------------------------------------------------------------------------


def _lineas(ruta: Path) -> int:
    return len(ruta.read_text(encoding="utf-8").splitlines())


def test_cli_py_no_pasa_de_700_lineas() -> None:
    assert _lineas(SRC / "cli.py") <= 700


def test_cli_base_py_no_pasa_de_200_lineas() -> None:
    assert _lineas(SRC / "cli_base.py") <= 200


TOPE_CLI_OPS = {"kek.py": 400, "rotate_key.py": 260, "retire_key.py": 200, "rotate_kek.py": 200}
"""B3a (S4B-D121): `kek.py` reúne tres comandos con bitácora y mensajes fijos; los demás archivos
de `cli_ops/` siguen bajo 150 líneas. Los archivos de `cli_ops/` no se importan entre sí, así que
no se puede partir sin un paquete nuevo.

B3b (S4B-D140): `rotate_key.py` (reintentos, lotes, índice y mensajes fijos) pasa de 150 y se
acota en 260; `retire_key.py` (M1: `--manifest` bajo `BACKUP_DIR`) se acota en 200 (S4B-D149).

S5-B2 (S5-D184, S5-D188): `rotate_kek.py` (rotar, reanudar, `--trim` con su comprobación repetida,
las pruebas de custodia y los mensajes fijos) se acota en 200; ver DECISIONES."""


def test_cada_archivo_de_cli_ops_tiene_menos_de_150_lineas() -> None:
    largos = {
        p.name: n
        for p in sorted((SRC / "cli_ops").glob("*.py"))
        if (n := _lineas(p)) >= TOPE_CLI_OPS.get(p.name, 150)
    }
    assert largos == {}


# L4 (S5-D166): `load_keyring` distingue un custodio no disponible de una DEK que no abre ----

from app.cli_keyring import load_keyring  # noqa: E402
from app.core.crypto.errors import CryptoUnavailable  # noqa: E402


class _Caido:
    name = "openbao"

    def __init__(self, razon: str) -> None:
        self.razon = razon

    async def unwrap(self, wrapped: bytes) -> bytes:
        raise CryptoUnavailable(self.razon)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("razon", "texto"),
    [("sealed", "OpenBao sellado"), ("unreachable", "OpenBao inalcanzable")],
)
async def test_custodio_no_disponible_sale_2_con_la_razon(
    base_de_llaves: AsyncEngine,
    proveedor_local: LocalFileProvider,
    capsys: pytest.CaptureFixture[str],
    razon: str,
    texto: str,
) -> None:
    async with async_sessionmaker(base_de_llaves, expire_on_commit=False)() as sesion:
        with actor_scope(SYSTEM_USER_ID):
            sesion.add(
                CryptoKey(
                    purpose="encrypt",
                    data_class="member.document",
                    algorithm="A256GCM",
                    provider="openbao",
                    version=1,
                    state="active",
                    wrapped_material=b"vault:v1:" + os.urandom(8).hex().encode(),
                    created_by=SYSTEM_USER_ID,
                )
            )
            await sesion.commit()
    configure_provider(proveedor_local)
    try:
        async with async_sessionmaker(base_de_llaves, expire_on_commit=False)() as sesion:
            with pytest.raises(typer.Exit) as salida:
                await load_keyring(sesion, lambda _n: _Caido(razon))  # type: ignore[arg-type,return-value]
    finally:
        configure_provider(None)
    assert salida.value.exit_code == 2
    assert texto in capsys.readouterr().err

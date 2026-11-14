"""Layout del volumen `keys`: `custody/` y `jwt/` y `init-keys --migrate-layout` (S6-D58, S5-D201).

Rojo S6-W0-2. Layout nuevo: `custody/kek.bin`, `custody/sign-ed25519.key`, `jwt/jwt_ed25519.pem`
y `jwt/jwt_ed25519.pub` bajo la raíz del volumen. `init-keys` lo crea; `--migrate-layout` mueve
un volumen plano al nuevo con `os.replace` (idempotente, sin sobrescribir, todo o nada ante un
conflicto, exit 2 si los dos layouts tienen el mismo archivo). El volumen plano de entrada lo
arma cada prueba a mano: aquí no se usa `key_paths_in` salvo para fijar su forma nueva.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from app import cli
from app.cli import app, key_paths_in
from app.cli_ops.keys_layout import LayoutReport, migrate_layout
from app.core.config import ConfigError, Settings, load_settings, read_jwt_private_key_path
from tests.cli._apoyo import correr

SOLO_POSIX = pytest.mark.skipif(os.name == "nt", reason="NTFS no conserva el modo POSIX")

# nombre -> (subcarpeta del layout nuevo, contenido de prueba; nunca material real)
NUEVO: dict[str, tuple[str, bytes]] = {
    "kek.bin": ("custody", b"kek-de-prueba-" + b"k" * 18),
    "sign-ed25519.key": ("sign", b"firma-de-prueba-" + b"s" * 16),
    "jwt_ed25519.pem": ("jwt", b"jwt-privada-de-prueba"),
    "jwt_ed25519.pub": ("jwt", b"jwt-publica-de-prueba"),
}
ARBOL_NUEVO: dict[str, bytes] = {f"{c}/{n}": d for n, (c, d) in NUEVO.items()}


def _plano(raiz: Path) -> Path:
    """Volumen plano: los cuatro archivos en la raíz, con modo 600."""
    raiz.mkdir(parents=True, exist_ok=True)
    for nombre, (_carpeta, datos) in NUEVO.items():
        destino = raiz / nombre
        destino.write_bytes(datos)
        destino.chmod(0o600)
    return raiz


def _arbol(raiz: Path) -> dict[str, bytes]:
    return {
        p.relative_to(raiz).as_posix(): p.read_bytes()
        for p in sorted(raiz.rglob("*"))
        if p.is_file()
    }


def _esperado(raiz: Path) -> dict[str, Path]:
    return {nombre: raiz / carpeta / nombre for nombre, (carpeta, _d) in NUEVO.items()}


def _modo(ruta: Path) -> int:
    return stat.S_IMODE(ruta.stat().st_mode)


# --- init-keys crea el layout nuevo ---------------------------------------------------------


def test_key_paths_in_apunta_a_custody_y_a_jwt(tmp_path: Path) -> None:
    rutas = key_paths_in(tmp_path)

    assert rutas.kek == tmp_path / "custody" / "kek.bin"
    assert rutas.signing_key == tmp_path / "sign" / "sign-ed25519.key"
    assert rutas.jwt_private == tmp_path / "jwt" / "jwt_ed25519.pem"
    assert rutas.jwt_public == tmp_path / "jwt" / "jwt_ed25519.pub"


def test_init_keys_crea_custody_y_jwt_y_deja_la_raiz_sin_archivos(tmp_path: Path) -> None:
    raiz = tmp_path / "keys"

    resultado = correr(app, ["init-keys", "--dir", str(raiz)])

    assert resultado.exit_code == 0, resultado.output
    assert sorted(p.name for p in raiz.iterdir()) == ["custody", "jwt", "sign"]
    assert sorted(p.name for p in (raiz / "custody").iterdir()) == ["kek.bin"]
    assert sorted(p.name for p in (raiz / "sign").iterdir()) == ["sign-ed25519.key"]
    assert sorted(p.name for p in (raiz / "jwt").iterdir()) == [
        "jwt_ed25519.pem",
        "jwt_ed25519.pub",
    ]


@SOLO_POSIX
def test_init_keys_deja_los_archivos_en_600_y_las_subcarpetas_en_700(tmp_path: Path) -> None:
    raiz = tmp_path / "keys"

    assert correr(app, ["init-keys", "--dir", str(raiz)]).exit_code == 0

    for subcarpeta in (raiz / "custody", raiz / "jwt", raiz / "sign"):
        assert _modo(subcarpeta) == 0o700, subcarpeta
        for archivo in subcarpeta.iterdir():
            assert _modo(archivo) == 0o600, archivo


# --- migrate_layout (función) ---------------------------------------------------------------


def test_migrate_layout_funcion_mueve_los_cuatro_y_los_informa(tmp_path: Path) -> None:
    raiz = _plano(tmp_path / "keys")

    informe = migrate_layout(raiz)

    assert isinstance(informe, LayoutReport)
    assert set(informe.moved) == set(NUEVO)
    assert informe.conflicts == ()
    assert not informe.nothing_to_migrate
    for nombre, destino in _esperado(raiz).items():
        assert destino.read_bytes() == NUEVO[nombre][1]
        assert not (raiz / nombre).exists()


def test_migrate_layout_funcion_con_conflicto_no_mueve_nada(tmp_path: Path) -> None:
    raiz = _plano(tmp_path / "keys")
    (raiz / "custody").mkdir()
    (raiz / "custody" / "kek.bin").write_bytes(b"otra-kek")
    antes = _arbol(raiz)

    informe = migrate_layout(raiz)

    assert informe.conflicts == ("kek.bin",)
    assert informe.moved == ()
    assert _arbol(raiz) == antes


def test_migrate_layout_funcion_sobre_el_layout_nuevo_no_tiene_nada_que_migrar(
    tmp_path: Path,
) -> None:
    raiz = tmp_path / "keys"
    assert correr(app, ["init-keys", "--dir", str(raiz)]).exit_code == 0
    antes = _arbol(raiz)

    informe = migrate_layout(raiz)

    assert informe.nothing_to_migrate
    assert _arbol(raiz) == antes


def test_migrate_layout_funcion_crea_custody_y_jwt_aunque_no_haya_nada_que_migrar(
    tmp_path: Path,
) -> None:
    # Revisión de seguridad de S6-W0-2: un volumen vacío (proveedor openbao nuevo) gana las
    # subcarpetas para que un subpath del worker no falle con un error confuso.
    raiz = tmp_path / "keys"
    raiz.mkdir()

    informe = migrate_layout(raiz)

    assert informe.nothing_to_migrate
    assert (raiz / "custody").is_dir() and (raiz / "jwt").is_dir() and (raiz / "sign").is_dir()
    if os.name != "nt":
        assert _modo(raiz / "custody") == _modo(raiz / "jwt") == _modo(raiz / "sign") == 0o700


def test_migrate_layout_funcion_un_enlace_simbolico_en_la_raiz_es_conflicto(tmp_path: Path) -> None:
    raiz = _plano(tmp_path / "keys")
    (raiz / "kek.bin").unlink()
    try:
        (raiz / "kek.bin").symlink_to("otra/kek.bin")
    except (OSError, NotImplementedError):
        pytest.skip("sin enlaces simbólicos en este sistema")
    antes = {p.name for p in raiz.iterdir()}

    informe = migrate_layout(raiz)

    assert informe.conflicts == ("kek.bin",)
    assert informe.moved == ()
    assert {p.name for p in raiz.iterdir()} == antes
    assert (raiz / "kek.bin").is_symlink()


# --- init-keys --migrate-layout (CLI) --------------------------------------------------------


def test_migrate_layout_cli_mueve_los_archivos_planos_sin_cambiar_un_byte(tmp_path: Path) -> None:
    raiz = _plano(tmp_path / "keys")

    resultado = correr(app, ["init-keys", "--migrate-layout", "--dir", str(raiz)])

    assert resultado.exit_code == 0, resultado.output
    assert _arbol(raiz) == ARBOL_NUEVO
    for nombre in NUEVO:
        assert nombre in resultado.output  # queda en la salida qué se movió (auditoría del comando)


@SOLO_POSIX
def test_migrate_layout_cli_deja_los_archivos_en_600(tmp_path: Path) -> None:
    raiz = _plano(tmp_path / "keys")

    assert correr(app, ["init-keys", "--migrate-layout", "--dir", str(raiz)]).exit_code == 0

    for destino in _esperado(raiz).values():
        assert _modo(destino) == 0o600, destino


def test_migrate_layout_cli_es_idempotente_la_segunda_dice_nada_que_migrar(tmp_path: Path) -> None:
    raiz = _plano(tmp_path / "keys")
    args = ["init-keys", "--migrate-layout", "--dir", str(raiz)]
    primera = correr(app, args)
    antes = _arbol(raiz)

    segunda = correr(app, args)

    assert primera.exit_code == 0 and segunda.exit_code == 0, segunda.output
    assert "nada que migrar" in segunda.output.lower()
    assert _arbol(raiz) == antes


def test_migrate_layout_cli_sobre_un_volumen_nuevo_dice_nada_que_migrar(tmp_path: Path) -> None:
    raiz = tmp_path / "keys"
    assert correr(app, ["init-keys", "--dir", str(raiz)]).exit_code == 0
    antes = _arbol(raiz)

    resultado = correr(app, ["init-keys", "--migrate-layout", "--dir", str(raiz)])

    assert resultado.exit_code == 0, resultado.output
    assert "nada que migrar" in resultado.output.lower()
    assert _arbol(raiz) == antes


def test_migrate_layout_cli_completa_un_layout_a_medias_sin_tocar_lo_ya_movido(
    tmp_path: Path,
) -> None:
    """Custody ya está en el layout nuevo y el par JWT sigue plano (sin archivo repetido)."""
    raiz = _plano(tmp_path / "keys")
    (raiz / "custody").mkdir()
    for nombre in ("kek.bin", "sign-ed25519.key"):
        os.replace(raiz / nombre, raiz / "custody" / nombre)

    resultado = correr(app, ["init-keys", "--migrate-layout", "--dir", str(raiz)])

    assert resultado.exit_code == 0, resultado.output
    assert _arbol(raiz) == ARBOL_NUEVO


def test_migrate_layout_cli_con_un_archivo_en_los_dos_layouts_sale_con_2_y_no_mueve_nada(
    tmp_path: Path,
) -> None:
    raiz = _plano(tmp_path / "keys")
    (raiz / "custody").mkdir()
    (raiz / "custody" / "kek.bin").write_bytes(b"kek-distinta-del-layout-nuevo")
    antes = _arbol(raiz)

    resultado = correr(app, ["init-keys", "--migrate-layout", "--dir", str(raiz)])

    assert resultado.exit_code == 2, resultado.output
    assert "kek.bin" in resultado.output  # nombra el archivo en conflicto
    assert _arbol(raiz) == antes, "todo o nada: ni siquiera se movió el par JWT"


def test_migrate_layout_cli_no_sobrescribe_el_destino_aunque_el_contenido_sea_igual(
    tmp_path: Path,
) -> None:
    raiz = _plano(tmp_path / "keys")
    (raiz / "jwt").mkdir()
    (raiz / "jwt" / "jwt_ed25519.pub").write_bytes(NUEVO["jwt_ed25519.pub"][1])
    antes = _arbol(raiz)

    resultado = correr(app, ["init-keys", "--migrate-layout", "--dir", str(raiz)])

    assert resultado.exit_code == 2, resultado.output
    assert _arbol(raiz) == antes


def test_migrate_layout_cli_no_imprime_material_de_llave(tmp_path: Path) -> None:
    raiz = _plano(tmp_path / "keys")

    resultado = correr(app, ["init-keys", "--migrate-layout", "--dir", str(raiz)])

    assert resultado.exit_code == 0, resultado.output
    for _carpeta, datos in NUEVO.values():
        assert datos.decode("ascii") not in resultado.output
        assert datos.hex() not in resultado.output


def _settings_openbao(tmp_path: Path, raiz: Path, *, env_plano: bool = False) -> Settings:
    """Settings con OpenBao: sin KEK local, así que la raíz solo puede salir de la ruta JWT."""
    env = tmp_path / ".env"
    jwt_path = raiz / "jwt_ed25519.pem" if env_plano else raiz / "jwt" / "jwt_ed25519.pem"
    env.write_text(
        "DATABASE_URL=postgresql+asyncpg://apex:x@127.0.0.1:1/apex_test\n"
        f"JWT_PRIVATE_KEY_PATH={jwt_path}\n"
        "CRYPTO_PROVIDER=openbao\n"
        "OPENBAO_TOKEN_FILE=/run/apex/openbao/token\n"
        "UPLOADS_DIR=/data/uploads\n"
        'CORS_ORIGINS=["http://localhost"]\n'
        "ENV=dev\n",
        encoding="utf-8",
    )
    return load_settings(env_file=env)


def test_migrate_layout_cli_sin_dir_toma_la_raiz_de_la_ruta_jwt_aunque_no_haya_kek_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con CRYPTO_PROVIDER=openbao `CRYPTO_LOCAL_KEK_PATH` es None y `deploy.sh` corre
    `--migrate-layout` igual: la raíz sale de `JWT_PRIVATE_KEY_PATH` (padre del padre)."""
    raiz = _plano(tmp_path / "keys")
    ajustes = _settings_openbao(tmp_path, raiz)
    assert ajustes.CRYPTO_LOCAL_KEK_PATH is None

    resultado = correr(
        app, ["init-keys", "--migrate-layout"], "dev", base=ajustes, monkeypatch=monkeypatch
    )

    assert resultado.exit_code == 0, resultado.output
    assert _arbol(raiz) == ARBOL_NUEVO


def test_migrate_layout_cli_sin_dir_con_el_env_plano_toma_el_padre_y_avisa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S6-D91: un servidor que actualiza a v0.3 aún tiene la ruta plana del JWT en su `.env`
    (`<raíz>/jwt_ed25519.pem`): la raíz es el padre, no el padre del padre, y el comando avisa
    que hay que actualizar las rutas. Antes decía «nada que migrar» sobre un volumen plano."""
    raiz = _plano(tmp_path / "keys")
    ajustes = _settings_openbao(tmp_path, raiz, env_plano=True)

    resultado = correr(
        app, ["init-keys", "--migrate-layout"], "dev", base=ajustes, monkeypatch=monkeypatch
    )

    assert resultado.exit_code == 0, resultado.output
    assert _arbol(raiz) == ARBOL_NUEVO
    assert "AVISO" in resultado.output and "JWT_PRIVATE_KEY_PATH" in resultado.output
    assert not (tmp_path / "custody").exists(), "no crea carpetas fuera del volumen"


def _settings_rotos() -> Settings:
    raise ConfigError(missing=["CRYPTO_LOCAL_KEK_PATH"], invalid=[])


def test_migrate_layout_cli_sin_dir_con_settings_rotos_usa_solo_la_ruta_jwt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S6-D92: `deploy.sh` corre `--migrate-layout` antes de `up -d`; una KEK mal apuntada en
    `.env` (caso «api roto» de `deploy_e2e.sh`) debe caer en el sondeo de `/health` con rollback,
    no abortar aquí. Solo hace falta `JWT_PRIVATE_KEY_PATH`."""
    raiz = _plano(tmp_path / "keys")
    monkeypatch.setattr(cli, "get_settings", _settings_rotos)
    monkeypatch.setattr(cli, "read_jwt_private_key_path", lambda: raiz / "jwt_ed25519.pem")

    resultado = correr(app, ["init-keys", "--migrate-layout"])

    assert resultado.exit_code == 0, resultado.output
    assert _arbol(raiz) == ARBOL_NUEVO


def test_migrate_layout_cli_sin_dir_sin_ruta_jwt_sale_con_2_y_la_nombra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raiz = _plano(tmp_path / "keys")
    antes = _arbol(raiz)
    monkeypatch.setattr(cli, "get_settings", _settings_rotos)
    monkeypatch.setattr(cli, "read_jwt_private_key_path", lambda: None)

    resultado = correr(app, ["init-keys", "--migrate-layout"])

    assert resultado.exit_code == 2, resultado.output
    assert "JWT_PRIVATE_KEY_PATH" in resultado.output
    assert _arbol(raiz) == antes


def test_read_jwt_private_key_path_ignora_el_resto_del_entorno(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "JWT_PRIVATE_KEY_PATH=/run/apex/keys/jwt_ed25519.pem\n"
        "CRYPTO_LOCAL_KEK_PATH=/nonexistent\n"
        "VARIABLE_QUE_NO_EXISTE=1\n",
        encoding="utf-8",
    )

    assert read_jwt_private_key_path(env) == Path("/run/apex/keys/jwt_ed25519.pem")
    assert read_jwt_private_key_path(tmp_path / "no-existe.env") is None

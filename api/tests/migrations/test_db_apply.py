"""`infra/db/apply.sh`, el entrypoint de `dbsetup` (S4B-W0-3; S4B-D72, L-4).

`apply.sh` exige las tres contraseñas (no vacías, distintas, sin `cambiar-esto`, de 24
caracteres o más) y ejecuta `roles.sql` y `grants.sql` con `psql -v ON_ERROR_STOP=1` desde
`/opt/db`. La prueba lo corre dentro de `db_test` (copia `infra/db` a `/opt/db` del contenedor y
usa la base `apex_roles` de la fixture); nunca toca `apex-db-1`. Imprime al final
`roles aplicados; N tablas clasificadas`.
"""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from tests.migrations.conftest import (
    CLAVES,
    CONTENEDOR,
    INFRA_DB,
    ROLES,
    VARIABLES_CLAVE,
    RolesDb,
    entorno_de_claves,
)

APPLY = INFRA_DB / "apply.sh"


def _docker(*args: str, entrada: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["docker", *args],  # noqa: S607
        input=entrada,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.fixture(scope="module")
def apply_en_db_test(apex_roles: RolesDb) -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker no está en el PATH")
    assert APPLY.is_file(), "no existe infra/db/apply.sh (S4B-W0-3.4)"
    _docker("exec", CONTENEDOR, "rm", "-rf", "/opt/db")
    copia = _docker("cp", str(INFRA_DB), f"{CONTENEDOR}:/opt/db")
    assert copia.returncode == 0, copia.stderr


def _correr_apply(apex: RolesDb, claves: dict[str, str]) -> subprocess.CompletedProcess[str]:
    orden = ["exec"]
    entorno = {
        **entorno_de_claves(claves),
        "PGUSER": apex.propietario,
        "PGPASSWORD": apex.clave_propietario,
        "PGDATABASE": apex.nombre,
        "PGHOST": "127.0.0.1",
    }
    for nombre, valor in entorno.items():
        orden += ["-e", f"{nombre}={valor}"]
    return _docker(*orden, CONTENEDOR, "/bin/sh", "/opt/db/apply.sh")


def test_apply_sh_es_estatico_seguro() -> None:
    texto = APPLY.read_text(encoding="utf-8")
    assert "set -euo pipefail" in texto or "set -eu" in texto
    assert not re.search(r"^\s*set\s+-[a-z]*x", texto, re.MULTILINE), "nunca set -x"
    assert not re.search(r"-v\s+\w*(pass|pw|clave)\w*=", texto, re.IGNORECASE), "sin -v clave=valor"
    assert "ON_ERROR_STOP=1" in texto
    assert "/opt/db/roles.sql" in texto and "/opt/db/grants.sql" in texto
    assert "cambiar-esto" in texto and "24" in texto


def test_apply_sh_aplica_roles_y_grants_y_cuenta_las_tablas(
    apex_roles: RolesDb, apply_en_db_test: None
) -> None:
    resultado = _correr_apply(apex_roles, CLAVES)
    assert resultado.returncode == 0, resultado.stderr
    salida = resultado.stdout + resultado.stderr
    coincide = re.search(r"roles aplicados; (\d+) tablas clasificadas", salida)
    assert coincide, salida
    consulta = _docker(
        "exec", CONTENEDOR, "psql", "-X", "-At", "-U", apex_roles.propietario, "-d",
        apex_roles.nombre, "-c",
        "SELECT count(*) FROM information_schema.tables WHERE table_type = 'BASE TABLE' "
        "AND table_schema IN ('audit','auth','crypto','members','memberships',"
        "'notifications','payments',"
        "'plans','settings','worker','public')",
    )  # fmt: skip
    assert int(coincide.group(1)) == int(consulta.stdout.strip())
    assert all(clave not in salida for clave in CLAVES.values()), "no imprime contraseñas"


@pytest.mark.parametrize(
    ("caso", "cambios"),
    [
        ("vacia", {"apex_api": ""}),
        ("cambiar-esto", {"apex_worker": "cambiar-esto"}),
        ("corta", {"apex_backup": "corta-23-caracteres-abc"}),
        ("repetida", {"apex_worker": CLAVES["apex_api"]}),
        ("repetida-backup", {"apex_backup": CLAVES["apex_worker"]}),
        ("arroba", {"apex_api": "api-prueba-0123456789@abcdef"}),
        ("barra", {"apex_worker": "worker-prueba-0123456789/abc"}),
        ("espacio", {"apex_backup": "backup prueba-0123456789-ab"}),
        ("comilla", {"apex_api": "api-prueba-0123456789'abcdef"}),
    ],
)
def test_apply_sh_rechaza_contraseñas_debiles_sin_imprimirlas(
    apex_roles: RolesDb, apply_en_db_test: None, caso: str, cambios: dict[str, str]
) -> None:
    claves = {**CLAVES, **cambios}
    resultado = _correr_apply(apex_roles, claves)
    assert resultado.returncode != 0, caso
    salida = resultado.stdout + resultado.stderr
    assert any(VARIABLES_CLAVE[rol] in salida for rol in cambios), "nombra la variable"
    for valor in (*claves.values(), *CLAVES.values()):
        if valor and valor != "cambiar-esto":  # el marcador no es un secreto
            assert valor not in salida, "el mensaje nunca incluye el valor"
    assert "roles aplicados" not in salida


def test_apply_sh_falla_si_falta_una_variable(apex_roles: RolesDb, apply_en_db_test: None) -> None:
    orden = ["exec", "-e", f"PGUSER={apex_roles.propietario}", "-e",
             f"PGPASSWORD={apex_roles.clave_propietario}", "-e", f"PGDATABASE={apex_roles.nombre}",
             "-e", "PGHOST=127.0.0.1"]  # fmt: skip
    for rol in ROLES[:2]:
        orden += ["-e", f"{VARIABLES_CLAVE[rol]}={CLAVES[rol]}"]
    resultado = _docker(*orden, CONTENEDOR, "/bin/sh", "/opt/db/apply.sh")
    assert resultado.returncode != 0
    assert "APEX_BACKUP_DB_PASSWORD" in resultado.stdout + resultado.stderr

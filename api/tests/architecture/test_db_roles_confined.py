"""Los roles de aplicación y sus archivos viven confinados (S4B-W0-3; S4B-D83, D101).

- `infra/db/{roles,grants,revoke}.sql` y `apply.sh` solo los usan `tests/migrations` (sobre
  `db_test`) y la infraestructura; nada de `src/app` los lee ni los ejecuta.
- Todo `docker exec` o `docker cp` de las pruebas apunta al contenedor de `db_test`
  (`apex-db_test-1`), nunca a `apex-db-1`: los roles de la base viva los crea `dbsetup`.
- La fixture `apex_roles` solo crea y borra la base `apex_roles` y arranca limpiando con
  `revoke.sql`.
"""

from __future__ import annotations

import re
from pathlib import Path

API = Path(__file__).resolve().parents[2]
SRC = API / "src" / "app"
TESTS = API / "tests"
CONFTEST = TESTS / "migrations" / "conftest.py"


def _fuentes(raiz: Path) -> list[Path]:
    return [p for p in raiz.rglob("*.py") if "__pycache__" not in p.parts]


def test_src_no_toca_infra_db_ni_los_nombres_de_los_roles() -> None:
    patron = re.compile(
        r"infra/db|revoke\.sql|grants\.sql|roles\.sql|apex_api\b|apex_worker\b|apex_backup\b"
    )
    culpables = [
        str(p.relative_to(API)) for p in _fuentes(SRC) if patron.search(p.read_text("utf-8"))
    ]
    assert culpables == []


def test_ninguna_prueba_apunta_a_la_base_viva() -> None:
    vivo = re.compile(r"(exec|cp|run)[^\n]*apex-db-1|apex_db_1")
    culpables = [
        str(p.relative_to(API))
        for p in _fuentes(TESTS)
        if p.name != Path(__file__).name and vivo.search(p.read_text("utf-8"))
    ]
    assert culpables == []


def test_los_docker_exec_de_las_pruebas_usan_el_contenedor_de_db_test() -> None:
    texto = CONFTEST.read_text("utf-8")
    assert 'CONTENEDOR = os.environ.get("APEX_DB_TEST_CONTAINER", "apex-db_test-1")' in texto
    for ruta in _fuentes(TESTS / "migrations"):
        cuerpo = ruta.read_text("utf-8")
        for linea in cuerpo.splitlines():
            if re.search(r'"(exec|cp)"', linea) or "docker exec" in linea:
                assert "CONTENEDOR" in cuerpo, f"{ruta.name}: docker sin CONTENEDOR"


def test_la_fixture_apex_roles_solo_borra_su_propia_base_y_limpia_con_revoke() -> None:
    texto = CONFTEST.read_text("utf-8")
    assert 'BASE_ROLES = "apex_roles"' in texto
    borrados = re.findall(r"DROP DATABASE IF EXISTS [^\"']*", texto)
    assert borrados and all("{BASE_ROLES}" in b for b in borrados)
    assert "revoke.sql" in texto and "DROP OWNED BY" in texto
    assert texto.index("_revoke_en_postgres()") < texto.index("CREATE DATABASE")


def test_los_sql_de_roles_solo_los_ejecutan_las_pruebas_de_migraciones() -> None:
    patron = re.compile(r"roles\.sql|grants\.sql|revoke\.sql|apply\.sh")
    permitidos = {"conftest.py", "test_db_grants.py", "test_db_apply.py"}
    culpables = [
        str(p.relative_to(API))
        for p in _fuentes(TESTS)
        if patron.search(p.read_text("utf-8"))
        and not (p.parent.name == "migrations" and p.name in permitidos)
        and p.name != Path(__file__).name
    ]
    assert culpables == []

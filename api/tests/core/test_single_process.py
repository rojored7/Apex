"""Un solo proceso del api (S6-D79, O4): el semáforo de adjuntos (D59), el rotador único (D61) y
`single_flight` de S5 suponen un solo worker de uvicorn.

Rojo S6-W0-5. Estas pruebas leen texto (`api/Dockerfile` e `infra/compose*.yml`); la parte viva
(`docker compose config`, `CMD` de la imagen) vive en `scripts/ci/test_compose_config.sh` y
`scripts/ci/test_api_image.sh`. Escalar a varios procesos exige mover esos tres candados a la base
(deuda anotada en RUNBOOK §1): hasta entonces estas pruebas lo impiden.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
DOCKERFILE = RAIZ / "api" / "Dockerfile"
COMPOSES = sorted((RAIZ / "infra").glob("compose*.yml"))


def _sin_comentarios(texto: str) -> str:
    return "\n".join(linea for linea in texto.splitlines() if not linea.lstrip().startswith("#"))


def _cmd_del_dockerfile() -> list[str]:
    cmds = re.findall(r"^CMD\s+(\[.*\])\s*$", DOCKERFILE.read_text(encoding="utf-8"), re.M)
    assert len(cmds) == 1, f"se esperaba un único CMD en api/Dockerfile y hay {len(cmds)}"
    return list(json.loads(cmds[0]))


def test_el_cmd_del_dockerfile_arranca_uvicorn() -> None:
    cmd = _cmd_del_dockerfile()
    assert cmd[0] == "uvicorn" and "app.main:app" in cmd


def test_el_cmd_del_dockerfile_no_lleva_workers() -> None:
    cmd = _cmd_del_dockerfile()
    assert not [a for a in cmd if a == "--workers" or a.startswith("--workers=")], cmd


def test_el_dockerfile_no_fija_workers_por_entorno_ni_por_gunicorn() -> None:
    texto = _sin_comentarios(DOCKERFILE.read_text(encoding="utf-8"))
    assert "gunicorn" not in texto.lower()
    assert not re.search(r"\b(UVICORN_WORKERS|WEB_CONCURRENCY)\b", texto)
    assert not re.search(r"--workers\b", texto)


def test_ningun_compose_declara_workers_ni_las_variables_que_los_activan() -> None:
    assert COMPOSES, "no se encontró infra/compose*.yml"
    for ruta in COMPOSES:
        texto = _sin_comentarios(ruta.read_text(encoding="utf-8"))
        assert not re.search(r"\b(UVICORN_WORKERS|WEB_CONCURRENCY)\b", texto), ruta.name
        assert not re.search(r"--workers\b", texto), ruta.name
        assert "gunicorn" not in texto.lower(), ruta.name


def test_el_cmd_de_compose_dev_conserva_un_solo_proceso_con_reload() -> None:
    """El comando de desarrollo del api (con `--reload`) tampoco lleva `--workers`: uvicorn lo
    rechaza junto con `--reload`, y el cuaderno de S6 lo da por un solo proceso."""
    texto = (RAIZ / "infra" / "compose.dev.yml").read_text(encoding="utf-8")
    comandos = re.findall(r'^\s*command:\s*(\["uvicorn".*\])\s*$', texto, re.M)
    assert comandos, "compose.dev.yml debe declarar el comando de uvicorn del api"
    for comando in comandos:
        assert "--workers" not in comando
        assert "--reload" in comando

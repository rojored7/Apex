"""Casos del analizador `find_forbidden_imports` (US-022 T3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.architecture import _imports
from tests.architecture._imports import ALLOW_FOREIGN_SCHEMAS, find_forbidden_imports


def _buscar(ruta: str, fuente: str, *, module: str) -> list[str]:
    return [
        f"{v.line}:{v.imported}:{v.rule}"
        for v in find_forbidden_imports(Path(ruta), module=module, source=fuente)
    ]


def test_models_ajenos_desde_service() -> None:
    fuente = "import os\nfrom app.modules.memberships.models import Membership\n"
    assert _buscar("members/service.py", fuente, module="members") == [
        "2:app.modules.memberships.models:foreign_models"
    ]


def test_models_propios_desde_router() -> None:
    fuente = "from app.modules.plans.models import Plan\n"
    assert _buscar("plans/router.py", fuente, module="plans") == [
        "1:app.modules.plans.models:router_models"
    ]


def test_service_ajeno_esta_permitido() -> None:
    fuente = (
        "from app.modules.memberships import service as memberships_service\n"
        "from app.modules.members.models import Member\n"
    )
    assert _buscar("members/service.py", fuente, module="members") == []


def test_import_dentro_de_una_funcion_y_type_checking() -> None:
    fuente = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from app.modules.payments.models import Payment\n"
        "def f():\n"
        "    from app.modules.memberships.models import Membership\n"
        "    return Membership\n"
    )
    assert _buscar("members/service.py", fuente, module="members") == [
        "3:app.modules.payments.models:foreign_models",
        "5:app.modules.memberships.models:foreign_models",
    ]


def test_import_relativo() -> None:
    fuente = "from ..memberships.models import Membership\nfrom .models import Member\n"
    assert _buscar("members/service.py", fuente, module="members") == [
        "1:app.modules.memberships.models:foreign_models"
    ]


def test_import_relativo_desde_subpaquete() -> None:
    fuente = "from ...memberships.models import X\nfrom ..models import Member\n"
    assert _buscar("members/handlers/eventos.py", fuente, module="members") == [
        "1:app.modules.memberships.models:foreign_models"
    ]


def test_import_modulo_con_alias_y_from_paquete() -> None:
    fuente = (
        "import app.modules.memberships.models as m\n"
        "from app.modules.memberships import models\n"
        "from app.modules.memberships import models as mm, service\n"
    )
    assert _buscar("members/service.py", fuente, module="members") == [
        "1:app.modules.memberships.models:foreign_models",
        "2:app.modules.memberships.models:foreign_models",
        "3:app.modules.memberships.models:foreign_models",
    ]


def test_router_ajeno() -> None:
    fuente = "from app.modules.billing.router import router\n"
    assert _buscar("members/service.py", fuente, module="members") == [
        "1:app.modules.billing.router:foreign_router"
    ]


def test_importlib_con_cadena_literal() -> None:
    fuente = 'import importlib\nm = importlib.import_module("app.modules.memberships.models")\n'
    assert _buscar("members/service.py", fuente, module="members") == [
        "2:app.modules.memberships.models:foreign_models"
    ]


def test_schemas_ajenos_dependen_de_la_bandera(monkeypatch: pytest.MonkeyPatch) -> None:
    fuente = (
        "from app.modules.memberships.schemas import MembershipOut\n"
        "from app.modules.memberships.exceptions import X\n"
    )
    assert ALLOW_FOREIGN_SCHEMAS is True
    assert _buscar("members/service.py", fuente, module="members") == []
    monkeypatch.setattr(_imports, "ALLOW_FOREIGN_SCHEMAS", False)
    assert _buscar("members/service.py", fuente, module="members") == [
        "1:app.modules.memberships.schemas:foreign_non_service",
        "2:app.modules.memberships.exceptions:foreign_non_service",
    ]


def test_lee_el_archivo_cuando_no_hay_source(tmp_path: Path) -> None:
    archivo = tmp_path / "members" / "service.py"
    archivo.parent.mkdir()
    archivo.write_text("from app.modules.plans.models import Plan\n", encoding="utf-8")
    [violacion] = find_forbidden_imports(archivo, module="members")
    assert violacion.rule == "foreign_models" and violacion.line == 1
    assert str(violacion).endswith("importa app.modules.plans.models (foreign_models)")

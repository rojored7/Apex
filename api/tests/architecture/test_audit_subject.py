"""El sujeto de la auditoría y el camino del historial del socio (S4A-B5, US-106; S4A-D20, C6).

`core/audit.py` llena `subject_member_id` con `_subject(obj)`, que lee el atributo de clase
`__audit_subject__` del modelo (nombre del atributo con el UUID del socio). El historial del socio
(`GET /members/{member_id}/audit`) filtra por esa columna, así que:
- `Member` declara `"id"`; `Membership` y `Payment` declaran `"member_id"`; el atributo nombrado
  existe como columna mapeada del modelo y es auditado (`__audited__`);
- `MembershipFreeze` no declara sujeto (S4A-D20: la congelación aparece por el `update` de la
  membresía);
- `core.audit._subject` es el mecanismo real (lee `__audit_subject__`), con un control;
- `modules/members/service.py` no importa `memberships.service` ni `payments.service` a nivel de
  módulo (el historial no los recorre: delega en `audit`); la única perezosa es la de la lista
  blanca de G-03 (`members -> memberships`, con su marca).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final
from uuid import uuid4

import pytest
from sqlalchemy.orm import class_mapper

import app
from app.core import audit as core_audit
from app.modules.members.models import Member
from app.modules.memberships.models import Membership, MembershipFreeze
from app.modules.payments.models import Payment

MEMBERS_SERVICE: Final = Path(app.__file__).resolve().parent / "modules" / "members" / "service.py"
PROHIBIDOS_ARRIBA: Final = frozenset({"memberships", "payments"})


@pytest.mark.parametrize(
    ("modelo", "atributo"),
    [(Member, "id"), (Membership, "member_id"), (Payment, "member_id")],
    ids=["Member", "Membership", "Payment"],
)
def test_los_modelos_con_socio_declaran_su_sujeto(modelo: type, atributo: str) -> None:
    assert getattr(modelo, "__audited__", False) is True
    assert getattr(modelo, "__audit_subject__", None) == atributo
    columnas = {attr.key for attr in class_mapper(modelo).column_attrs}
    assert atributo in columnas, f"{modelo.__name__}.{atributo} no es una columna mapeada"


def test_membership_freeze_no_declara_sujeto_por_s4a_d20() -> None:
    assert getattr(MembershipFreeze, "__audited__", False) is True
    assert getattr(MembershipFreeze, "__audit_subject__", None) is None
    assert "member_id" not in {attr.key for attr in class_mapper(MembershipFreeze).column_attrs}


def test_el_mecanismo_real_lee_audit_subject() -> None:
    """Control: `core.audit._subject` devuelve el UUID del atributo nombrado y `None` sin sujeto."""
    socio_id = uuid4()
    membresia = Membership(member_id=socio_id)
    assert core_audit._subject(membresia) == socio_id
    socio = Member(id=socio_id)
    assert core_audit._subject(socio) == socio_id
    assert core_audit._subject(MembershipFreeze(membership_id=uuid4())) is None


def _imports_de_services(arbol: ast.Module) -> tuple[set[str], set[str]]:
    """`(arriba, perezosos)`: módulos `app.modules.<x>` importados a nivel de módulo y dentro de
    funciones (cualquier forma: `import`, `from app.modules.x import service`, `from
    app.modules.x.service import ...`)."""
    arriba: set[str] = set()
    perezosos: set[str] = set()
    en_funciones = {
        id(hijo)
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.FunctionDef | ast.AsyncFunctionDef)
        for hijo in ast.walk(nodo)
    }
    for nodo in ast.walk(arbol):
        nombres: list[str] = []
        if isinstance(nodo, ast.Import):
            nombres = [alias.name for alias in nodo.names]
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres = [nodo.module, *(f"{nodo.module}.{alias.name}" for alias in nodo.names)]
        for nombre in nombres:
            partes = nombre.split(".")
            if partes[:2] == ["app", "modules"] and len(partes) >= 4 and partes[3] == "service":
                (perezosos if id(nodo) in en_funciones else arriba).add(partes[2])
    return arriba, perezosos


def test_members_service_no_importa_memberships_ni_payments_arriba() -> None:
    arriba, perezosos = _imports_de_services(ast.parse(MEMBERS_SERVICE.read_text(encoding="utf-8")))
    assert not (arriba & PROHIBIDOS_ARRIBA), f"imports de nivel de módulo: {sorted(arriba)}"
    assert "audit" in arriba, "el historial delega en audit.service (S4A-D20)"
    assert "payments" not in perezosos
    assert perezosos <= {"memberships"}


def test_el_detector_de_imports_ve_arriba_y_perezosos() -> None:
    fuente = """
from app.modules.memberships import service as memberships_service
import app.modules.payments.service

async def f():
    from app.modules.memberships.service import status_for  # lazy: G-03
    return status_for
"""
    arriba, perezosos = _imports_de_services(ast.parse(fuente))
    assert arriba == {"memberships", "payments"}
    assert perezosos == {"memberships"}

"""El detalle de auditoría no devuelve los blobs de `athletes.body_metrics` (S9-A2, L-8; S9-D19).

`GET /audit/{seq}` sustituye el valor de los cuatro campos de salud (`weight_g`, `height_cm`,
`body_fat_pct`, `notes`) de esa tabla por el texto fijo `cifrado`, en `before`, `after` y en
`changes` (con `encrypted = True`), tenga o no forma de blob: se decide por tabla y campo, no por
la forma del valor. Sin llave, algoritmo ni largo del blob. Un campo vacío sigue `None`; el
`notes` de otra tabla no se toca; la fila `reveal` (`field` e `ip`) queda igual.
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from tests.athletes._apoyo import alta, auditoria_de, fila_cruda, revelar
from tests.audit._apoyo import ruta_entrada
from tests.audit.conftest import audit_service
from tests.conftest import Cabeceras, UsuarioPrueba
from tests.notifications._apoyo_avisos import socio

CAMPOS = ("weight_g", "height_cm", "body_fat_pct", "notes")
TABLA = "athletes.body_metrics"
MARCA = "cifrado"


@pytest.fixture
async def escena(
    session: AsyncSession, bus_listo: Keyring, reloj: FrozenClock, ana: UsuarioPrueba
) -> dict[str, object]:
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, ana.id, miembro.id, weight_g=73_417, notes="Nota privada")
    filas = await auditoria_de(session, medicion.id)
    (insercion,) = [f for f in filas if f["action"] == "insert"]
    return {"seq": insercion["seq"], "member_id": miembro.id, "metric_id": medicion.id}


async def test_el_insert_trae_los_cuatro_campos_como_cifrado(
    session: AsyncSession, escena: dict[str, object]
) -> None:
    crudo = await fila_cruda(session, escena["metric_id"])  # type: ignore[arg-type]
    assert all(crudo[c].startswith("apx1.") for c in CAMPOS)

    detalle = await audit_service.get_entry(session, escena["seq"])  # type: ignore[arg-type]

    assert detalle.before is None
    assert detalle.after is not None
    for campo in CAMPOS:
        assert detalle.after[campo] == MARCA, campo
    cambios = {c.field: c for c in detalle.changes}
    for campo in CAMPOS:
        assert cambios[campo].after == MARCA and cambios[campo].before is None, campo
        assert cambios[campo].encrypted is True, campo
    serializado = json.dumps(detalle.model_dump(mode="json"))
    for ajeno in ("apx1.", "A256GCM", "key_id", "73417", "Nota privada"):
        assert ajeno not in serializado, ajeno
    assert detalle.after["member_id"] == str(escena["member_id"])


async def test_se_sustituye_por_tabla_y_campo_aunque_no_tenga_forma_de_blob(
    session: AsyncSession, escena: dict[str, object], ana: UsuarioPrueba
) -> None:
    with actor_scope(ana.id):
        fila = await record(
            session,
            action="update",
            table_name=TABLA,
            record_id=escena["metric_id"],  # type: ignore[arg-type]
            before={"weight_g": "texto plano antes", "notes": None},
            after={"weight_g": "texto plano despues", "notes": "otro texto", "voided_by": None},
            user_id=ana.id,
        )
    detalle = await audit_service.get_entry(session, fila.seq)

    assert detalle.before == {"weight_g": MARCA, "notes": None}
    assert detalle.after is not None
    assert detalle.after["weight_g"] == MARCA and detalle.after["notes"] == MARCA
    assert "texto plano" not in json.dumps(detalle.model_dump(mode="json"))


async def test_el_notes_de_otra_tabla_no_se_sustituye(
    session: AsyncSession, escena: dict[str, object], ana: UsuarioPrueba
) -> None:
    with actor_scope(ana.id):
        fila = await record(
            session,
            action="update",
            table_name="wods.wod_movements",
            record_id=escena["metric_id"],  # type: ignore[arg-type]
            before={"notes": "antes"},
            after={"notes": "despues"},
            user_id=ana.id,
        )
    detalle = await audit_service.get_entry(session, fila.seq)

    assert detalle.before == {"notes": "antes"} and detalle.after == {"notes": "despues"}


async def test_la_fila_reveal_conserva_field_e_ip(
    session: AsyncSession, escena: dict[str, object], ana: UsuarioPrueba
) -> None:
    await revelar(
        session,
        ana.id,
        escena["member_id"],
        escena["metric_id"],
        "weight_g",
        role="admin",  # type: ignore[arg-type]
    )
    (reveal,) = [
        f
        for f in await auditoria_de(session, escena["metric_id"])  # type: ignore[arg-type]
        if f["action"] == "reveal"
    ]

    detalle = await audit_service.get_entry(session, reveal["seq"])

    assert detalle.after == {"field": "weight_g", "ip": "198.51.100.9"}
    assert detalle.changes[0].field in {"field", "ip"}


async def test_por_http_el_cuerpo_no_lleva_blobs_ni_valores(
    app_http: AsyncClient,
    session: AsyncSession,
    escena: dict[str, object],
    ana: UsuarioPrueba,
    cabeceras: Cabeceras,
) -> None:
    r = await app_http.get(ruta_entrada(escena["seq"]), headers=cabeceras(ana))  # type: ignore[arg-type]

    assert r.status_code == 200, r.text
    for ajeno in ("apx1.", "A256GCM", "73417", "Nota privada"):
        assert ajeno not in r.text, ajeno
    assert r.json()["after"]["weight_g"] == MARCA
    total = await session.scalar(text("SELECT count(*) FROM audit.audit_log"))
    assert total is not None

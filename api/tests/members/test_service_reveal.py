"""`members.service.reveal` con PostgreSQL real (S3-B10; US-074; D19, D-4, L-12, N-20, Q6;
blueprint B10 y demo 6).

- El valor revelado es el sembrado en los cinco campos (`birth_date` como `AAAA-MM-DD`,
  `emergency_contact` como `EmergencyContactOut`); la salida es un `RevealOut` con el campo.
- Exactamente UNA fila `reveal` en `audit.audit_log` por llamada: `table_name="members.members"`,
  el socio como `record_id` y `subject_member_id`, el actor como `user_id`, `before` nulo y
  `after == {"field": <campo>, "ip": <ip>}` (L-12), nunca el valor.
- Exactamente UNA fila `decrypt` nueva en `crypto_ops` con `purpose='reveal'`,
  `data_class='member.<campo>'`, el `record_id` del socio y el actor; ninguna `mask`.
- Si la auditoría falla (`append_entry` lanza), no queda fila `reveal` ni sale el valor, pero el
  `decrypt` sobrevive al rollback (`oplog._after_soft_rollback`, D19). Se prueba con commit real
  (`dos_sesiones` y `bus_confirmado`): la fila la confirma otra conexión.
- Un campo vacío devuelve `None`, también audita y no descifra nada.
- Ningún suscriptor agrega otra fila de auditoría (no hay evento `SensitiveFieldRevealed`, D19).
- Funciona sobre un socio dado de baja (N-20); un id inexistente da `MemberNotFound` sin auditar.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit as core_audit
from app.core.clock import FrozenClock
from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.modules.members import service
from app.modules.members.exceptions import MemberNotFound
from app.modules.members.schemas import EmergencyContactOut, RevealOut
from tests.conftest import T0, CrearUsuario, UsuarioPrueba
from tests.factories.members import KNOWN, KNOWN_NORMALIZED, make_member
from tests.members._apoyo import auditoria_del_socio, operaciones, peticion

IP = "198.51.100.4"
CINCO = ("document", "phone", "email", "birth_date", "emergency_contact")
ESPERADOS: dict[str, Any] = {
    "document": KNOWN["document"],
    "phone": KNOWN["phone"],
    "email": KNOWN["email"],
    "birth_date": KNOWN["birth_date"].isoformat(),
    "emergency_contact": EmergencyContactOut(name="Rosa", phone="3115550199"),
}


class AuditoriaRota(Exception):
    """Falla simulada de la cadena (no hereda de `RuntimeError`: `NotImplementedError` sí)."""


@pytest.fixture
async def coach(usuario_real: CrearUsuario, bus_listo: Keyring) -> UsuarioPrueba:
    return await usuario_real("coach")


async def revelar(
    session: AsyncSession, actor: UUID, member_id: UUID, campo: str, ip: str = IP
) -> RevealOut:
    """Una petición: sesión limpia, `service.reveal` bajo el actor y commit."""
    with peticion(session, actor):
        salida = await service.reveal(session, member_id, campo, ip=ip)  # type: ignore[arg-type]
        await session.commit()
    return salida


async def _decrypts(session: AsyncSession, member_id: UUID) -> list[dict[str, Any]]:
    return await operaciones(session, verb="decrypt", record_id=member_id)


# Valor ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("campo", CINCO)
async def test_el_valor_revelado_es_el_sembrado(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock, campo: str
) -> None:
    socio = await make_member(session)
    salida = await revelar(session, coach.id, socio.id, campo)
    assert isinstance(salida, RevealOut)
    assert salida.field == campo
    assert salida.value == ESPERADOS[campo]


async def test_la_fecha_sale_como_texto_iso_y_el_contacto_como_objeto(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(
        session, emergency_contact={"name": "Rosa", "phone": "3115550199", "relationship": "madre"}
    )
    fecha = await revelar(session, coach.id, socio.id, "birth_date")
    assert fecha.model_dump(mode="json") == {"field": "birth_date", "value": "1991-07-23"}
    contacto = await revelar(session, coach.id, socio.id, "emergency_contact")
    assert contacto.model_dump(mode="json") == {
        "field": "emergency_contact",
        "value": {"name": "Rosa", "phone": "3115550199", "relationship": "madre"},
    }


# Auditoría (D19, L-12) ------------------------------------------------------------------------


@pytest.mark.parametrize("campo", CINCO)
async def test_deja_exactamente_una_fila_reveal_sin_el_valor(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock, campo: str
) -> None:
    socio = await make_member(session)
    await revelar(session, coach.id, socio.id, campo)
    filas = await auditoria_del_socio(session, socio.id, "reveal")
    assert len(filas) == 1
    (fila,) = filas
    assert fila["table_name"] == "members.members"
    assert fila["record_id"] == socio.id
    assert fila["subject_member_id"] == socio.id
    assert fila["user_id"] == coach.id
    assert fila["before"] is None
    assert fila["after"] == {"field": campo, "ip": IP}
    volcado = json.dumps([fila["before"], fila["after"]])
    for valor in KNOWN_NORMALIZED:
        assert valor not in volcado, valor
    assert "apx1." not in volcado


async def test_cada_reveal_agrega_su_fila_y_nada_mas(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    """Ningún suscriptor ni hook agrega filas: dos reveals, dos filas y ninguna de otra acción."""
    socio = await make_member(session)
    antes = await auditoria_del_socio(session, socio.id)
    await revelar(session, coach.id, socio.id, "document")
    await revelar(session, coach.id, socio.id, "phone", ip="203.0.113.50")
    nuevas = (await auditoria_del_socio(session, socio.id))[len(antes) :]
    assert [(f["action"], f["after"]) for f in nuevas] == [
        ("reveal", {"field": "document", "ip": IP}),
        ("reveal", {"field": "phone", "ip": "203.0.113.50"}),
    ]


# crypto_ops (D19, D-4) ------------------------------------------------------------------------


@pytest.mark.parametrize("campo", CINCO)
async def test_deja_exactamente_un_decrypt_con_proposito_reveal(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock, campo: str
) -> None:
    socio = await make_member(session)
    await revelar(session, coach.id, socio.id, campo)
    filas = await _decrypts(session, socio.id)
    assert len(filas) == 1, filas
    (fila,) = filas
    assert fila["purpose"] == "reveal"
    assert fila["data_class"] == f"member.{campo}"
    assert fila["user_id"] == coach.id
    assert fila["result"] == "ok"
    assert fila["batch_id"] is None


# Vacío, dado de baja e inexistente ------------------------------------------------------------


@pytest.mark.parametrize("campo", ["phone", "email", "birth_date", "emergency_contact"])
async def test_un_campo_vacio_devuelve_none_y_tambien_audita(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock, campo: str
) -> None:
    socio = await make_member(session, **{campo: None})
    salida = await revelar(session, coach.id, socio.id, campo)
    assert salida == RevealOut(field=campo, value=None)  # type: ignore[arg-type]
    filas = await auditoria_del_socio(session, socio.id, "reveal")
    assert [f["after"] for f in filas] == [{"field": campo, "ip": IP}]
    assert await _decrypts(session, socio.id) == []


async def test_funciona_sobre_un_socio_dado_de_baja(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    socio = await make_member(session, deleted_at=T0 - timedelta(days=3), status="inactive")
    salida = await revelar(session, coach.id, socio.id, "document")
    assert salida.value == KNOWN["document"]
    assert len(await auditoria_del_socio(session, socio.id, "reveal")) == 1


async def test_un_id_inexistente_da_member_not_found_sin_auditar(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    inexistente = UUID("00000000-0000-4000-8000-00000000b10a")
    with pytest.raises(MemberNotFound), peticion(session, coach.id):
        await service.reveal(session, inexistente, "document", ip=IP)
    await session.rollback()
    assert await auditoria_del_socio(session, inexistente) == []
    assert await _decrypts(session, inexistente) == []


# Si la auditoría falla, el valor no sale (D19; commit real) -------------------------------------


async def test_si_la_auditoria_falla_no_queda_reveal_ni_valor_pero_si_el_decrypt(
    dos_sesiones: tuple[AsyncSession, AsyncSession],
    bus_confirmado: Keyring,
    reloj: FrozenClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primera, segunda = dos_sesiones
    socio = await make_member(primera)
    actor = UUID("0000000a-0000-4000-8000-00000000b10b")

    def _rota(*_args: object, **_kwargs: object) -> object:
        raise AuditoriaRota("cadena no disponible")

    monkeypatch.setattr(core_audit, "append_entry", _rota)
    salida: RevealOut | None = None
    with actor_scope(actor), pytest.raises(AuditoriaRota):
        salida = await service.reveal(segunda, socio.id, "document", ip=IP)
        await segunda.commit()
    await segunda.rollback()
    monkeypatch.undo()

    assert salida is None  # el valor nunca salió del service
    consulta = text(
        "SELECT count(*) FROM audit.audit_log WHERE record_id = :id AND action = 'reveal'"
    )
    assert await primera.scalar(consulta, {"id": socio.id}) == 0
    decrypts = (
        (
            await primera.execute(
                text(
                    "SELECT purpose, data_class, user_id FROM crypto.crypto_ops "
                    "WHERE record_id = :id AND verb = 'decrypt'"
                ),
                {"id": socio.id},
            )
        )
        .mappings()
        .all()
    )
    assert [dict(f) for f in decrypts] == [
        {"purpose": "reveal", "data_class": "member.document", "user_id": actor}
    ]
    await primera.commit()


# Revisión de seguridad del Verde (LOW-2) -------------------------------------------------------


async def test_un_contacto_guardado_ilegible_da_un_error_opaco_sin_el_claro(
    ops_tras_el_rollback: None, session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    """Un contacto cifrado sin `phone` no sale en el error de pydantic (`input_value`): el
    error es opaco, sin la excepción original encadenada, y no queda fila `reveal`. El `decrypt`
    que sobrevive al rollback lo borra `ops_tras_el_rollback` (va antes que `session`)."""
    socio = await make_member(session, emergency_contact={"name": "Rosaura Ilegible"})
    socio_id = socio.id
    with pytest.raises(RuntimeError) as error, peticion(session, coach.id):
        await service.reveal(session, socio_id, "emergency_contact", ip=IP)
    await session.rollback()
    assert "Rosaura" not in str(error.value)
    assert error.value.__suppress_context__ is True
    assert error.value.__cause__ is None
    assert await auditoria_del_socio(session, socio_id, "reveal") == []

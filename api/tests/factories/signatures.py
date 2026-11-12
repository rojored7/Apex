"""Fábrica de firmas de la cadena de auditoría (S6-A1; S6-D7, S6-D34, ADR-006).

- `payload_de(through_seq, chain_hash, version=1)`: el payload de ADR-006 construido AQUÍ, a mano,
  como oráculo independiente de `core.audit_sign.signature_payload` (las pruebas no comparan el
  código con sí mismo).
- `firmar_hasta(session, through_seq, ...)`: inserta una fila de `audit.signatures` para la fila
  `through_seq` de la cadena, con `bus.sign("audit.signature", payload)` real (exige keyring con
  la fila `sign`, `tests.crypto.conftest.fila_sign`); no pasa por `sign_latest`.
- `alterar_fila(session, seq, *, rehash=False)`: cambia `after` de la fila `seq` de
  `audit.audit_log` con los triggers apagados y vueltos a encender con `ENABLE ALWAYS`
  (`tamper_row`); con `rehash` recalcula la cola (la cadena queda internamente válida).
- `borrar_firma(session, through_seq)`: borra la firma con los triggers de `audit.signatures`
  apagados y los enciende uno por uno con `ENABLE ALWAYS`.
- `cadena_con_firmas(session, segmentos)`: por cada entero `n` agrega `n` filas válidas y firma
  con `sign_latest`; devuelve los `SignOutcome`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Final
from uuid import UUID, uuid4

from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import audit_sign
from app.core.audit_sign import AuditSignature, SignOutcome
from app.core.clock import current_clock
from app.core.context import SYSTEM_USER_ID
from app.core.crypto import bus
from app.core.crypto.keyring import Keyring, configure_keyring
from tests.factories import audit_chain
from tests.factories.triggers import disable_user_sql, rearm_always_sql

TABLA: Final = AuditSignature.__table__
CLASE: Final = "audit.signature"


def payload_de(through_seq: int, chain_hash: str, version: int = 1) -> bytes:
    """`apex-audit-sig-v<version>\\n<through_seq>\\n<chain_hash>` en ASCII (ADR-006)."""
    return f"apex-audit-sig-v{version}\n{through_seq}\n{chain_hash}".encode("ascii")


async def firmar_hasta(
    session: AsyncSession,
    through_seq: int,
    *,
    by: UUID = SYSTEM_USER_ID,
    version: int = 1,
    signed_at: datetime | None = None,
) -> UUID:
    """Firma (con el bus) el hash de la fila `through_seq` y guarda la fila; no confirma."""
    hash_ = await audit_chain.hash_of(session, through_seq)
    assert hash_ is not None, f"no existe la fila {through_seq} de la cadena"
    firma = await bus.sign(CLASE, payload_de(through_seq, hash_, version))
    llave_id = UUID(firma.split(".")[1])
    algoritmo = firma.split(".")[2]
    ahora = signed_at or current_clock().now_utc()
    valores: dict[str, Any] = {
        "id": uuid4(),
        "through_seq": through_seq,
        "hash": hash_,
        "signature": firma,
        "key_id": llave_id,
        "algorithm": algoritmo,
        "payload_version": version,
        "signed_at": ahora,
        "created_at": ahora,
        "updated_at": ahora,
        "created_by": by,
    }
    await session.execute(insert(TABLA).values(**valores))
    return UUID(str(valores["id"]))


async def alterar_fila(session: AsyncSession, seq: int, *, rehash: bool = False) -> None:
    """Reescribe `after` de la fila `seq` de `audit.audit_log` (triggers apagados y rearmados)."""
    await audit_chain.tamper_row(session, seq, "after", {"n": seq, "alterado": True}, rehash=rehash)


async def borrar_firma(session: AsyncSession, through_seq: int) -> None:
    """Borra la firma de `through_seq` (triggers apagados y vueltos a encender, uno por nombre)."""
    await session.execute(text(disable_user_sql("audit.signatures")))
    await session.execute(TABLA.delete().where(TABLA.c.through_seq == through_seq))
    await session.execute(text(rearm_always_sql("audit.signatures")))


async def firmas(session: AsyncSession) -> list[Any]:
    """Filas crudas de `audit.signatures` en orden de `through_seq`."""
    resultado = await session.execute(select(TABLA).order_by(TABLA.c.through_seq))
    return list(resultado.mappings().all())


async def cadena_con_firmas(session: AsyncSession, segmentos: Sequence[int]) -> list[SignOutcome]:
    """Por cada `n` de `segmentos`: agrega `n` filas válidas y firma con `sign_latest`."""
    salida: list[SignOutcome] = []
    for n in segmentos:
        await audit_chain.make_audit_chain(session, n)
        salida.append(await audit_sign.sign_latest(session))
    return salida


# Escenarios de verificación (S6-A3; S6-D62, S6-D81) ----------------------------------------


async def copiar_firma(session: AsyncSession, *, de_seq: int, a_seq: int) -> None:
    """Pone en la fila `a_seq` la firma de `de_seq` (base64 válido, firma equivocada): triggers
    apagados y vueltos a encender uno por uno con `ENABLE ALWAYS`."""
    await session.execute(text(disable_user_sql("audit.signatures")))
    await session.execute(
        text(
            "UPDATE audit.signatures SET signature = "
            "(SELECT signature FROM audit.signatures WHERE through_seq = :de) "
            "WHERE through_seq = :a"
        ),
        {"de": de_seq, "a": a_seq},
    )
    await session.execute(text(rearm_always_sql("audit.signatures")))


async def escribir_firma(session: AsyncSession, through_seq: int, texto: str) -> None:
    """Reemplaza el texto de la firma de `through_seq` (por ejemplo, basura que no se parsea)."""
    await session.execute(text(disable_user_sql("audit.signatures")))
    await session.execute(
        text("UPDATE audit.signatures SET signature = :s WHERE through_seq = :a"),
        {"s": texto, "a": through_seq},
    )
    await session.execute(text(rearm_always_sql("audit.signatures")))


async def cambiar_llave(
    session: AsyncSession,
    key_id: UUID,
    *,
    state: str | None = None,
    public_key: str | None = None,
) -> None:
    """Cambia el estado o la clave pública de una fila de `crypto.crypto_keys` (triggers apagados y
    vueltos a encender). Solo para armar escenarios: producción no toca `public_key` (D81)."""
    await session.execute(text(disable_user_sql("crypto.crypto_keys")))
    if state is not None:
        await session.execute(
            text("UPDATE crypto.crypto_keys SET state = :v WHERE id = :i"),
            {"v": state, "i": key_id},
        )
    if public_key is not None:
        await session.execute(
            text("UPDATE crypto.crypto_keys SET public_key = :v WHERE id = :i"),
            {"v": public_key, "i": key_id},
        )
    await session.execute(text(rearm_always_sql("crypto.crypto_keys")))


async def keyring_nuevo(session: AsyncSession, resolver: Any) -> Keyring:
    """Un keyring recién cargado desde la base (como tras reiniciar el api) y fijado como el del
    proceso; refleja los cambios de `cambiar_llave`, que un keyring ya cargado no ve."""
    nuevo = Keyring()
    await nuevo.load_all(session, resolver)
    configure_keyring(nuevo)
    return nuevo


async def firma_de_llave_retirada(
    session: AsyncSession, proveedor: Any, through_seq: int, *, estado: str = "retired"
) -> UUID:
    """Firma `through_seq` con la llave activa, la pasa a `estado` (`retired` o `decrypt_only`) y
    crea la versión 2 `active` (como tras `rotate-key audit.signature`); devuelve el `key_id` de la
    llave vieja. El keyring del proceso queda recargado (`keyring_nuevo`)."""
    from tests.crypto.conftest import fila_sign

    await firmar_hasta(session, through_seq)
    vieja = (await firmas(session))[-1]["key_id"]
    await cambiar_llave(session, vieja, state=estado)
    await fila_sign(session, proveedor, version=2)
    await keyring_nuevo(session, lambda _n: proveedor)
    return UUID(str(vieja))

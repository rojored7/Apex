"""Tipos de columna `Encrypted` y `BlindIndexed`, cifrado en el flush y `reveal` (US-028).

- Un modelo declara `document: Mapped[Secret | None] = mapped_column(Encrypted("member.document"))`
  y `document_idx: Mapped[str | None] = mapped_column(BlindIndexed("member.document",
  source="document"))`. Asigna `Secret.from_plain(...)`; nunca llama a `bus.encrypt`.
- `before_flush` (sobre `sqlalchemy.orm.Session`, instalado por `create_app`, worker, CLI y
  `conftest`): asigna el `id` si falta, rechaza cambios de `id` en registros cifrados
  (`id_immutable`), cifra cada `Secret` pendiente con `aad = id` según el `value_type` de la
  clase (`str`, `date.isoformat()`, `canonical_json`) y llena el `BlindIndexed` asociado en el
  mismo flush; `None` deja ambas columnas en `NULL`; un `_idx` cambiado a mano sin cambio de su
  fuente falla (`index_manual`). Antes de cifrar comprueba, una vez por flush y por clase, que
  la llave `active` de la base (`SELECT ... FOR SHARE`) es la del keyring; si no,
  `crypto_key_changed` (US-030: la rotación espera a las escrituras en curso).
- El `TypeDecorator` solo deja llegar a la base blobs `apx1` válidos: un texto en claro falla
  también por `INSERT` de Core (`plaintext`). Expone `is_encrypted = True` para la auditoría
  (US-016), que serializa pasando por `process_bind_param`.
- `reveal(obj, campo, proposito)` es la única lectura en claro; el propósito va a `crypto_ops`.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from uuid import uuid4

from sqlalchemy import Text, TypeDecorator, event, text
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import ColumnProperty, Session, UOWTransaction, class_mapper
from sqlalchemy.orm.attributes import instance_state

from app.core.crypto import bus
from app.core.crypto.blob import parse_blob
from app.core.crypto.errors import CryptoError
from app.core.crypto.keyring import current_keyring
from app.core.crypto.registry import DataClassSpec, get_spec
from app.core.crypto.secret import PlainValue, Secret, canonical_json


class Encrypted(TypeDecorator[Secret]):
    impl = Text
    cache_ok = True
    is_encrypted = True

    def __init__(self, data_class: str) -> None:
        spec = get_spec(data_class)
        if not spec.encrypt:
            raise CryptoError("unsupported", f"la clase {data_class} no se cifra")
        self.data_class = data_class
        super().__init__()

    def process_bind_param(self, value: object, dialect: Dialect | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, Secret):
            if not value.is_sealed:
                raise CryptoError("plaintext", "valor en claro hacia la base: Secret sin cifrar")
            return value.blob
        if isinstance(value, str):
            try:
                parse_blob(value)
            except CryptoError:
                raise CryptoError("plaintext", "valor en claro hacia la base") from None
            return value
        raise CryptoError("plaintext", "valor en claro hacia la base")

    def process_result_value(self, value: str | None, dialect: Dialect | None) -> Secret | None:
        return None if value is None else Secret.from_blob(value)


class BlindIndexed(TypeDecorator[str]):
    impl = Text
    cache_ok = True
    is_blind_index = True

    def __init__(self, data_class: str, *, source: str) -> None:
        spec = get_spec(data_class)
        if spec.index_kind is None:
            raise CryptoError("no_index", f"la clase {data_class} no tiene índice ciego")
        self.data_class = data_class
        self.source = source
        super().__init__()


# Serialización por tipo de valor ----------------------------------------------------


def _to_bytes(value: PlainValue, spec: DataClassSpec) -> tuple[bytes, str | None]:
    """`(bytes a cifrar, texto para el índice)` según `value_type`."""
    if spec.value_type == "str":
        if not isinstance(value, str):
            raise CryptoError("unsupported", f"{spec.name} espera texto")
        return value.encode("utf-8"), value
    if spec.value_type == "date":
        if not isinstance(value, date):
            raise CryptoError("unsupported", f"{spec.name} espera una fecha")
        return value.isoformat().encode("ascii"), None
    if not isinstance(value, dict | type(value)) or isinstance(value, str | date):
        raise CryptoError("unsupported", f"{spec.name} espera un mapeo")
    return canonical_json(value).encode("utf-8"), None


def _from_bytes(data: bytes, spec: DataClassSpec) -> str | date | dict[str, Any]:
    if spec.value_type == "str":
        return data.decode("utf-8")
    if spec.value_type == "date":
        return date.fromisoformat(data.decode("ascii"))
    cargado: dict[str, Any] = json.loads(data.decode("utf-8"))
    return cargado


# Listener de flush --------------------------------------------------------------------


def _column_props(obj: object) -> list[ColumnProperty[Any]]:
    return list(class_mapper(type(obj)).column_attrs)


def _encrypted_props(obj: object) -> list[tuple[ColumnProperty[Any], Encrypted]]:
    salida: list[tuple[ColumnProperty[Any], Encrypted]] = []
    for prop in _column_props(obj):
        tipo = prop.columns[0].type
        if isinstance(tipo, Encrypted):
            salida.append((prop, tipo))
    return salida


def _index_props(obj: object) -> list[tuple[ColumnProperty[Any], BlindIndexed]]:
    salida: list[tuple[ColumnProperty[Any], BlindIndexed]] = []
    for prop in _column_props(obj):
        tipo = prop.columns[0].type
        if isinstance(tipo, BlindIndexed):
            salida.append((prop, tipo))
    return salida


def _check_key_current(
    session: Session, data_class: str, purpose: str, revisadas: set[str]
) -> None:
    clave = f"{purpose}:{data_class}"
    if clave in revisadas:
        return
    revisadas.add(clave)
    fila = (
        session.connection()
        .execute(
            text(
                "SELECT id FROM crypto.crypto_keys WHERE purpose = :p AND data_class = :dc "
                "AND state = 'active' FOR SHARE"
            ),
            {"p": purpose, "dc": data_class},
        )
        .first()
    )
    vigente = current_keyring().active_for(purpose, data_class).key_id
    if fila is None or fila[0] != vigente:
        raise CryptoError(
            "crypto_key_changed",
            f"la llave {purpose} de {data_class} cambió; reintente la operación",
        )


def _encrypt_pending(session: Session, obj: object, revisadas: set[str]) -> None:
    cifradas = _encrypted_props(obj)
    if not cifradas:
        return
    estado = instance_state(obj)
    if estado.persistent and estado.attrs["id"].history.has_changes():
        raise CryptoError("id_immutable", "no se puede cambiar el id de un registro cifrado")
    if getattr(obj, "id", None) is None:
        obj.id = uuid4()  # type: ignore[attr-defined]
    record_id = obj.id  # type: ignore[attr-defined]
    aad = bus.aad_for(record_id)
    indices = _index_props(obj)
    for prop, tipo in cifradas:
        valor = getattr(obj, prop.key)
        asociados = [p for p, t in indices if t.source == prop.key]
        if valor is None:
            for idx in asociados:
                if getattr(obj, idx.key) is not None:
                    setattr(obj, idx.key, None)
            continue
        if not isinstance(valor, Secret):
            raise CryptoError("plaintext", f"{prop.key} debe recibir un Secret, no texto en claro")
        if valor.is_sealed:
            continue
        spec = get_spec(tipo.data_class)
        _check_key_current(session, tipo.data_class, "encrypt", revisadas)
        datos, texto_indice = _to_bytes(valor._take_plain(), spec)
        blob = bus.encrypt(tipo.data_class, datos, aad, record_id=record_id)
        setattr(obj, prop.key, Secret.from_blob(blob))
        for idx in asociados:
            if texto_indice is None:
                continue
            _check_key_current(session, tipo.data_class, "index", revisadas)
            setattr(
                obj, idx.key, bus.blind_index(tipo.data_class, texto_indice, record_id=record_id)
            )
    for idx, tipo_idx in indices:
        if (
            estado.attrs[idx.key].history.has_changes()
            and not estado.attrs[tipo_idx.source].history.has_changes()
        ):
            raise CryptoError(
                "index_manual", f"{idx.key} se calcula desde {tipo_idx.source}; no se asigna a mano"
            )


def _before_flush(session: Session, flush_context: UOWTransaction, instances: object) -> None:
    revisadas: set[str] = set()
    for obj in list(session.new) + list(session.dirty):
        _encrypt_pending(session, obj, revisadas)


def install_crypto_type_listeners() -> None:
    """Registra el listener sobre la clase `Session` síncrona (idempotente)."""
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)


# Lectura en claro ---------------------------------------------------------------------


def reveal(obj: object, field: str, purpose: str) -> str | date | dict[str, Any] | None:
    """Descifra `obj.<field>` con `aad = obj.id` y deja rastro con `purpose` (N-01, N-21)."""
    props = {p.key: p for p in _column_props(obj)}
    prop = props.get(field)
    tipo = prop.columns[0].type if prop is not None else None
    if not isinstance(tipo, Encrypted):
        raise CryptoError("unsupported", f"{field} no es una columna cifrada")
    valor = getattr(obj, field)
    if valor is None:
        return None
    if not isinstance(valor, Secret) or not valor.is_sealed:
        raise CryptoError("unsupported", f"{field} aún no está cifrado (haga flush)")
    record_id = obj.id  # type: ignore[attr-defined]
    datos = bus.decrypt(valor.blob, bus.aad_for(record_id), purpose=purpose, record_id=record_id)
    return _from_bytes(datos, get_spec(tipo.data_class))

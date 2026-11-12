"""Puerto `Reencryptor` (G-09; S6-D14, S6-B1).

Una clase cifrada cuyos blobs no viven en columnas del registro (por ejemplo
`attachment.sensitive`, archivos en el `StorageProvider`) registra aquí quien cuenta y recifra.
`core/crypto/service.py` delega en el puerto cuando existe; sin columnas ni puerto, la rotación
responde `rotation_not_supported`. Sin importar modelos ni `app.modules`.

Contrato que las pruebas fijan: el registro vive en el diccionario del módulo `_registered`
(`{data_class: Reencryptor}`); las pruebas lo aíslan con `monkeypatch.setattr`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

_registered: dict[str, Reencryptor] = {}


@runtime_checkable
class Reencryptor(Protocol):
    """Quien sabe contar y recifrar los registros de una clase fuera de las columnas."""

    async def count_total(self, session: AsyncSession) -> int: ...

    async def count_pending(self, session: AsyncSession, active_key_id: UUID) -> int: ...

    async def reencrypt_batch(
        self, session: AsyncSession, active_key_id: UUID, batch_size: int
    ) -> int: ...

    async def count_by_key(self, session: AsyncSession, key_id: UUID) -> int:
        """Objetos cifrados con esa llave (cualquier estado): `retire-key` los suma (S6-D14)."""
        ...


def register_reencryptor(data_class: str, impl: Reencryptor) -> None:
    """Registra `impl` para `data_class`; registrar dos veces la misma clase es un error."""
    if data_class in _registered:
        raise ValueError(f"ya hay un Reencryptor registrado para {data_class}")
    _registered[data_class] = impl


def _reset_for_tests() -> None:
    """SOLO PRUEBAS: vacía el registro del proceso para que un registro no contamine a otras."""
    _registered.clear()


def get_reencryptor(data_class: str) -> Reencryptor | None:
    """El puerto de la clase, o `None` si no hay."""
    return _registered.get(data_class)


def reencryptor_registered(data_class: str) -> bool:
    return data_class in _registered

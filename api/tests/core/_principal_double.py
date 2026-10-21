"""Doble del puerto `PrincipalLoader` (US-034, M-2): devuelve lo que cada prueba registre."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal


class PrincipalDouble:
    def __init__(self) -> None:
        self.usuarios: dict[UUID, Principal | None] = {}
        self.llamadas: list[UUID] = []

    def reset(self) -> None:
        self.usuarios.clear()
        self.llamadas.clear()

    async def __call__(self, session: AsyncSession, user_id: UUID) -> Principal | None:
        self.llamadas.append(user_id)
        return self.usuarios.get(user_id)


# Instancia única: conftest la registra y las pruebas la pueblan (mismo módulo importado).
principal_double = PrincipalDouble()

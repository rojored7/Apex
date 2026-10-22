"""Hallazgos de la revisión de seguridad de S2-B7 (`security-reviewer`), fijados con prueba.

- MEDIUM-1: los índices ciegos (`document_idx`, `phone_idx`, `email_idx`) no viajan a
  `audit.audit_log.after`: son HMAC con llave y permitirían correlacionar socios desde la
  auditoría. Quedan como `***` (`__audit_redact__`).
- LOW-2: un documento corto (menos de 6 caracteres normalizados) no se muestra entero en la
  máscara: va sin cola.
- LOW-5: `data_consent` es una autorización legal; solo vale un `true` JSON literal
  (`StrictBool`), no `"true"`, `"yes"` ni `1`.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import REDACTED
from app.core.clock import FrozenClock
from app.modules.members.schemas import MemberCreate
from app.modules.members.service import mask
from tests.auth._cuentas import filas_auditoria
from tests.conftest import CrearUsuario
from tests.members._apoyo import crear, cuerpo, entrada, fila_socio

INDICES = ("document_idx", "phone_idx", "email_idx")


async def test_la_auditoria_del_alta_no_lleva_los_indices_ciegos(
    session: AsyncSession, usuario_real: CrearUsuario, bus_listo: Any, reloj: FrozenClock
) -> None:
    admin = await usuario_real("admin")
    salida = await crear(session, admin.id, entrada())
    fila = await fila_socio(session, salida.id)
    (auditoria,) = await filas_auditoria(session, "members.members", salida.id)
    for indice in INDICES:
        assert auditoria["after"][indice] == REDACTED, indice
        assert fila[indice] not in str(auditoria["after"]), indice


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("123", "CC ••••"), ("1.234", "CC ••••"), ("12345", "CC ••••"), ("123456", "CC •••• 3456")],
)
def test_un_documento_corto_no_se_muestra_entero(valor: str, esperado: str) -> None:
    assert mask("document", valor, document_type="CC") == esperado


@pytest.mark.parametrize("valor", ["true", "yes", 1, "1"])
def test_data_consent_solo_acepta_el_booleano_literal(valor: Any) -> None:
    with pytest.raises(ValidationError) as error:
        MemberCreate.model_validate(cuerpo(data_consent=valor))
    assert error.value.errors()[0]["loc"] == ("data_consent",)


def test_data_consent_true_y_false_literales_pasan() -> None:
    assert MemberCreate.model_validate(cuerpo(data_consent=True)).data_consent is True
    assert MemberCreate.model_validate(cuerpo(data_consent=False)).data_consent is False

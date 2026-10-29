"""Ninguna sección de configuración guarda secretos (US-054 T10; DECISIONES Q12).

Recorre `SECTION_REGISTRY` (que debe tener exactamente las secciones habilitadas) y falla si
un esquema no declara `extra="forbid"` o si algún campo, también anidado, parece un secreto:
sufijo `_password`, `_token`, `_secret` o `_key`, o un nombre que contiene `password`,
`secret`, `api_key`, `private_key`, `smtp_pass` o `vapid` (sin distinguir mayúsculas). Los
secretos de canales (SMTP, VAPID, Telegram) van por `.env`, nunca por la base.

S4A-B4 (S4A-D61 a, L-10): `settings.settings_sections` es auditada y el detalle admin de la
auditoría la muestra tal cual; por eso ningún campo (tampoco anidado) de un esquema registrado, de
escritura (`SECTION_REGISTRY`) o de lectura (`SECTION_VIEWS`), puede CONTENER `token`, `secret` o
`password` en el nombre o el alias (regla más amplia que los sufijos de arriba: `token_hash`,
`tokens` o `bot_tokens` también caen).
"""

from __future__ import annotations

import re
from typing import Any, get_args

from pydantic import BaseModel, ConfigDict, Field

from app.modules.settings.schemas import (
    ENABLED_SECTIONS,
    SECTION_REGISTRY,
    SECTION_VIEWS,
    PaymentMethodsSettings,
    SectionKey,
)

SECRETO = re.compile(
    r"(_password|_token|_secret|_key)$|password|secret|api_key|private_key|smtp_pass|vapid",
    re.IGNORECASE,
)

CONTIENE_SECRETO = re.compile(r"token|secret|password", re.IGNORECASE)


def _modelos_anidados(anotacion: Any) -> list[type[BaseModel]]:
    if isinstance(anotacion, type) and issubclass(anotacion, BaseModel):
        return [anotacion]
    return [m for arg in get_args(anotacion) for m in _modelos_anidados(arg)]


def campos_sospechosos(modelo: type[BaseModel], ruta: str = "") -> list[str]:
    """Rutas `seccion.campo` de los campos con nombre (o alias) de secreto."""
    hallados: list[str] = []
    for nombre, info in modelo.model_fields.items():
        actual = f"{ruta}.{nombre}" if ruta else nombre
        if any(SECRETO.search(n) for n in (nombre, info.alias or "")):
            hallados.append(actual)
        for anidado in _modelos_anidados(info.annotation):
            hallados.extend(campos_sospechosos(anidado, actual))
    return hallados


def sin_extra_forbid(modelo: type[BaseModel]) -> list[str]:
    salida = [] if modelo.model_config.get("extra") == "forbid" else [modelo.__name__]
    for info in modelo.model_fields.values():
        for anidado in _modelos_anidados(info.annotation):
            salida.extend(sin_extra_forbid(anidado))
    return salida


def test_el_registro_tiene_exactamente_las_secciones_habilitadas() -> None:
    assert set(SECTION_REGISTRY) == set(ENABLED_SECTIONS)
    assert all(modelo.model_fields for modelo in SECTION_REGISTRY.values())


def test_payment_methods_esta_registrada_y_revisada() -> None:
    """S3-B3 (US-056, D24): la sección nueva entra al registro y se revisa también anidada
    (`MethodLabel` por medio): sin campos de secreto y con `extra="forbid"` en cada nivel."""
    assert SectionKey.payment_methods in ENABLED_SECTIONS
    assert SECTION_REGISTRY[SectionKey.payment_methods] is PaymentMethodsSettings
    assert campos_sospechosos(PaymentMethodsSettings) == []
    assert sin_extra_forbid(PaymentMethodsSettings) == []


def test_ningun_esquema_registrado_declara_un_campo_secreto() -> None:
    assert SECTION_REGISTRY, "SECTION_REGISTRY vacío: la prueba no revisaría nada"
    hallados = [
        f"{clave}.{campo}"
        for clave, modelo in SECTION_REGISTRY.items()
        for campo in campos_sospechosos(modelo)
    ]
    assert hallados == []


def test_todo_esquema_registrado_prohibe_campos_extra() -> None:
    assert SECTION_REGISTRY, "SECTION_REGISTRY vacío: la prueba no revisaría nada"
    sin_forbid = [n for modelo in SECTION_REGISTRY.values() for n in sin_extra_forbid(modelo)]
    assert sin_forbid == []


def test_el_detector_reconoce_los_nombres_de_secreto() -> None:
    """Control del detector: si este falla, las dos anteriores pasarían en falso."""

    class Interno(BaseModel):
        model_config = ConfigDict(extra="allow")
        vapid_public: str = ""

    class Canales(BaseModel):
        model_config = ConfigDict(extra="forbid")
        sender_name: str = ""
        smtp_password: str = ""
        bot_token: str = ""
        client_secret: str = ""
        signing_key: str = ""
        API_KEY: str = ""
        nested: Interno | None = None

    assert campos_sospechosos(Canales) == [
        "smtp_password",
        "bot_token",
        "client_secret",
        "signing_key",
        "API_KEY",
        "nested.vapid_public",
    ]
    assert sin_extra_forbid(Canales) == ["Interno"]


def campos_con_secreto(modelo: type[BaseModel], ruta: str = "") -> list[str]:
    """Rutas de los campos (también anidados) cuyo nombre o alias contiene `token`, `secret` o
    `password` (S4A-D61 a)."""
    hallados: list[str] = []
    for nombre, info in modelo.model_fields.items():
        actual = f"{ruta}.{nombre}" if ruta else nombre
        if any(CONTIENE_SECRETO.search(n) for n in (nombre, info.alias or "")):
            hallados.append(actual)
        for anidado in _modelos_anidados(info.annotation):
            hallados.extend(campos_con_secreto(anidado, actual))
    return hallados


def test_ninguna_seccion_registrada_tiene_un_campo_que_contenga_token_secret_o_password() -> None:
    """S4A-D61 a: la auditoría muestra las secciones tal cual; un secreto nunca vive en ellas."""
    modelos = {**{f"w:{k}": m for k, m in SECTION_REGISTRY.items()}}
    modelos.update({f"r:{k}": m for k, m in SECTION_VIEWS.items()})
    assert len(modelos) >= 2 * len(ENABLED_SECTIONS)
    hallados = [
        f"{clave}.{campo}" for clave, m in modelos.items() for campo in campos_con_secreto(m)
    ]
    assert hallados == []


def test_el_detector_de_contiene_ve_nombres_que_los_sufijos_no_ven() -> None:
    """Control: `token_hash`, `bot_tokens`, `Secreto` no, `SecretName` sí, alias y anidados."""

    class Anidado(BaseModel):
        model_config = ConfigDict(extra="forbid")
        password_hint: str = ""

    class Seccion(BaseModel):
        model_config = ConfigDict(extra="forbid", populate_by_name=True)
        token_hash: str = ""
        bot_tokens: str = ""
        SecretName: str = ""
        nombre: str = Field(default="", alias="apiToken")
        ciudad: str = ""
        interno: Anidado | None = None

    assert campos_con_secreto(Seccion) == [
        "token_hash",
        "bot_tokens",
        "SecretName",
        "nombre",
        "interno.password_hint",
    ]
    assert campos_sospechosos(Seccion) != campos_con_secreto(Seccion)

"""Funciones puras de settings sin base (US-054 T7; S2-D15).

`validate_section`, `check_version`, `ensure_enabled` y `defaults_for`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.settings.exceptions import (
    SectionNotAvailable,
    SettingsValidationError,
    VersionConflict,
)
from app.modules.settings.schemas import ENABLED_SECTIONS, SectionKey
from app.modules.settings.service import (
    check_version,
    defaults_for,
    ensure_enabled,
    validate_section,
)
from tests.settings._apoyo import (
    DESCONOCIDAS,
    GYM_DEFAULTS,
    GYM_OK,
    MEMBERSHIPS_DEFAULTS,
    NO_HABILITADAS,
    PRIVACY_DEFAULTS,
)


def test_validate_section_devuelve_el_modelo_validado() -> None:
    modelo = validate_section(SectionKey.gym, GYM_OK)
    assert modelo.model_dump(mode="json") == GYM_OK


def test_el_modelo_validado_es_inmutable() -> None:
    modelo = validate_section(SectionKey.gym, GYM_OK)
    with pytest.raises(ValidationError):
        modelo.name = "Otro"  # type: ignore[attr-defined]


def test_valor_invalido_da_422_con_field_en_forma_value_x() -> None:
    with pytest.raises(SettingsValidationError) as excinfo:
        validate_section(SectionKey.gym, {**GYM_OK, "name": ""})
    error = excinfo.value
    assert error.status == 422
    assert error.code == "validation_error"
    assert error.field == "value.name"


def test_campo_desconocido_da_422_con_su_field() -> None:
    with pytest.raises(SettingsValidationError) as excinfo:
        validate_section(SectionKey.gym, {**GYM_OK, "color": "rojo"})
    assert excinfo.value.status == 422 and excinfo.value.field == "value.color"


def test_el_mensaje_del_422_no_repite_el_valor_recibido() -> None:
    valor = "correo-que-no-es-correo-7731"
    with pytest.raises(SettingsValidationError) as excinfo:
        validate_section(SectionKey.gym, {**GYM_OK, "email": valor})
    assert excinfo.value.field == "value.email"
    assert valor not in excinfo.value.message
    assert valor not in str(excinfo.value)


def test_check_version_igual_no_lanza() -> None:
    check_version(3, 3)
    check_version(0, 0)


@pytest.mark.parametrize(("guardada", "enviada"), [(3, 2), (3, 4), (1, 0), (0, 1)])
def test_check_version_distinta_da_409_version_conflict(guardada: int, enviada: int) -> None:
    with pytest.raises(VersionConflict) as excinfo:
        check_version(guardada, enviada)
    assert excinfo.value.status == 409 and excinfo.value.code == "version_conflict"
    assert (
        excinfo.value.message == "Otra persona cambió esta sección. Recarga para ver los cambios."
    )


@pytest.mark.parametrize("clave", ["gym", "privacy", "memberships"])
def test_ensure_enabled_acepta_las_tres_del_sprint(clave: str) -> None:
    assert ensure_enabled(clave) == SectionKey(clave)
    assert SectionKey(clave) in ENABLED_SECTIONS


@pytest.mark.parametrize("clave", [*NO_HABILITADAS, *DESCONOCIDAS, ""])
def test_ensure_enabled_rechaza_futuras_y_desconocidas_con_404(clave: str) -> None:
    with pytest.raises(SectionNotAvailable) as excinfo:
        ensure_enabled(clave)
    error = excinfo.value
    assert error.status == 404 and error.code == "section_not_available"
    assert error.field is None


def test_defaults_de_gym_traen_el_respaldo_apex() -> None:
    assert defaults_for(SectionKey.gym) == GYM_DEFAULTS


def test_defaults_de_memberships_son_7_30_2_7() -> None:
    assert defaults_for(SectionKey.memberships) == MEMBERSHIPS_DEFAULTS


def test_defaults_de_privacy_no_tienen_version_ni_texto() -> None:
    assert defaults_for(SectionKey.privacy) == PRIVACY_DEFAULTS


def test_defaults_for_devuelve_una_copia() -> None:
    primero = defaults_for(SectionKey.gym)
    primero["name"] = "Mutado"
    assert defaults_for(SectionKey.gym)["name"] == "APEX"


@pytest.mark.parametrize("clave", [SectionKey.gym, SectionKey.memberships])
def test_los_defaults_validan_contra_su_esquema(clave: SectionKey) -> None:
    assert validate_section(clave, defaults_for(clave)).model_dump(mode="json") == defaults_for(
        clave
    )

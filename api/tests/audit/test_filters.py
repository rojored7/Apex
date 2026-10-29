"""Filtros de `GET /audit` y marcador de blobs: pruebas puras (S4A-B4, US-102 y US-103; S4A-D16,
S4A-D45, S4A-D46, S4A-D52, S4A-D61 b).

Valores a mano con `AHORA = 2026-10-21T15:00:00Z`: piso de los instantes 2020-01-01T00:00Z, techo
2026-10-22T15:00:00Z (`now + 1 día`); `MAX_AUDIT_OFFSET = 100_000` (100.000 se admite, 100.001 da
422 con `field="offset"`). `q` que es un UUID (también en mayúsculas o con espacios) pasa a
`record_id`; otro texto se limpia (`core.search.clean_query`: NFC, sin controles y recortado) y
queda en `email_term` sin plegar (el plegado de mayúsculas y tildes lo hace `auth`). El blob de
prueba `apx1.<KEY>.A256GCM.n.c` tiene cinco partes: su marcador es `{"encrypted": True,
"key_id": "<KEY>", "alg": "A256GCM"}`.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.audit import AUDIT_ACTIONS
from app.core.audit import BLOB_PREFIX as PREFIJO_DE_AUDITORIA
from app.core.crypto import blob as crypto_blob
from app.core.crypto import types as crypto_types
from app.core.pagination import PageParams
from app.modules.audit import diff
from app.modules.audit.exceptions import AuditRangeInvalid
from app.modules.audit.queries import AUDITABLE_TABLES, AuditFilters, build_audit_filters
from app.modules.audit.schemas import (
    MAX_AUDIT_OFFSET,
    MAX_SEQ,
    TABLE_MAX_LENGTH,
    TABLE_PATTERN,
    AuditListQuery,
)

AHORA = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
TECHO = datetime(2026, 10, 22, 15, 0, tzinfo=UTC)
PISO = datetime(2020, 1, 1, tzinfo=UTC)
UN_MICRO = timedelta(microseconds=1)
PAGINA = PageParams()
ID = UUID("6f1c2b3a-4d5e-4f60-8a7b-9c0d1e2f3a4b")
KEY = "328c1948-e343-48a1-9ef4-1b9dab140c4f"
BLOB = f"apx1.{KEY}.A256GCM.n.c"
MARCADOR = {"encrypted": True, "key_id": KEY, "alg": "A256GCM"}


def _filtros(page: PageParams = PAGINA, **datos: Any) -> AuditFilters:
    return build_audit_filters(AuditListQuery(**datos), page, now=AHORA)


def _campo_invalido(page: PageParams = PAGINA, **datos: Any) -> str | None:
    with pytest.raises(AuditRangeInvalid) as capturado:
        _filtros(page, **datos)
    assert (capturado.value.status, capturado.value.code) == (422, "validation_error")
    return capturado.value.field


# Constantes ---------------------------------------------------------------------------------


def test_constantes_del_contrato() -> None:
    assert MAX_AUDIT_OFFSET == 100_000
    assert MAX_SEQ == 9_223_372_036_854_775_807
    assert TABLE_MAX_LENGTH == 127


def test_auditable_tables_es_la_lista_unica_de_las_nueve_tablas() -> None:
    """S4A-D61 b: la constante única; cada nombre cumple el patrón del filtro `table`."""
    assert (
        frozenset(
            {
                "members.members",
                "memberships.memberships",
                "memberships.membership_freezes",
                "payments.payments",
                "plans.plans",
                "auth.users",
                "auth.one_time_tokens",
                "settings.settings_sections",
                "audit.verifications",
            }
        )
        == AUDITABLE_TABLES
    )
    assert all(re.fullmatch(TABLE_PATTERN, t) for t in AUDITABLE_TABLES)


# build_audit_filters -------------------------------------------------------------------------


def test_sin_filtros_no_filtra_nada() -> None:
    assert _filtros() == AuditFilters()


@pytest.mark.parametrize(
    ("datos", "esperado"),
    [
        ({"user_id": ID}, AuditFilters(user_id=ID)),
        ({"table": "members.members"}, AuditFilters(table_name="members.members")),
        ({"table": "audit.verifications"}, AuditFilters(table_name="audit.verifications")),
        (
            {"record_id": ID, "table": "members.members"},
            AuditFilters(record_id=ID, table_name="members.members"),
        ),
        ({"subject_member_id": ID}, AuditFilters(subject_member_id=ID)),
        ({"action": "reveal"}, AuditFilters(action="reveal")),
        ({"from": PISO}, AuditFilters(start=PISO)),
        ({"to": TECHO}, AuditFilters(end=TECHO)),
        (
            {"from": AHORA - timedelta(days=7), "to": AHORA},
            AuditFilters(start=AHORA - timedelta(days=7), end=AHORA),
        ),
    ],
    ids=["user", "table", "table-verify", "record", "subject", "action", "from", "to", "rango"],
)
def test_cada_filtro_pasa_a_los_filtros(datos: dict[str, Any], esperado: AuditFilters) -> None:
    assert _filtros(**datos) == esperado


def test_from_llega_por_alias_o_por_nombre() -> None:
    assert AuditListQuery(**{"from": PISO}).from_ == PISO
    assert AuditListQuery(from_=PISO).from_ == PISO


@pytest.mark.parametrize(
    "q",
    [str(ID), str(ID).upper(), f"  {ID}  "],
    ids=["minusculas", "mayusculas", "espacios"],
)
def test_q_uuid_con_tabla_filtra_record_id(q: str) -> None:
    assert _filtros(q=q, table="plans.plans") == AuditFilters(
        record_id=ID, table_name="plans.plans"
    )


@pytest.mark.parametrize(
    ("q", "termino"),
    [
        ("ana", "ana"),
        ("  Ana.PÉREZ ", "Ana.PÉREZ"),
        ("pérez", "pérez"),
        ("ana\x07", "ana"),
        ("50%_x", "50%_x"),
        ("6f1c2b3a", "6f1c2b3a"),
    ],
    ids=["simple", "recorta", "nfc", "control", "comodines", "uuid-parcial"],
)
def test_q_texto_es_el_termino_de_correo(q: str, termino: str) -> None:
    assert _filtros(q=q) == AuditFilters(email_term=termino)


@pytest.mark.parametrize(
    "q", [None, "", "   ", "\x07"], ids=["none", "vacia", "blancos", "control"]
)
def test_q_vacia_no_filtra(q: str | None) -> None:
    assert _filtros(q=q) == AuditFilters()


def test_q_y_los_demas_filtros_se_combinan() -> None:
    assert _filtros(q="ana", action="update", table="plans.plans") == AuditFilters(
        email_term="ana", action="update", table_name="plans.plans"
    )


@pytest.mark.parametrize(
    ("datos", "campo"),
    [
        ({"from": PISO - UN_MICRO}, "from"),
        ({"to": PISO - UN_MICRO}, "to"),
        ({"from": TECHO + UN_MICRO}, "from"),
        ({"to": TECHO + UN_MICRO}, "to"),
        ({"from": datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=5)))}, "from"),
        ({"to": datetime(9999, 12, 31, tzinfo=UTC)}, "to"),
        ({"from": AHORA, "to": AHORA - UN_MICRO}, "to"),
        ({"from": AHORA, "to": AHORA}, "to"),
    ],
    ids=[
        "from-bajo-piso",
        "to-bajo-piso",
        "from-sobre-techo",
        "to-sobre-techo",
        "from-anio-1-mas-5",
        "to-9999",
        "invertido",
        "iguales",
    ],
)
def test_rangos_fuera_de_limite_dan_audit_range_invalid_con_el_campo(
    datos: dict[str, Any], campo: str
) -> None:
    assert _campo_invalido(**datos) == campo


def test_el_rango_valido_en_los_bordes_pasa() -> None:
    assert _filtros(**{"from": PISO, "to": TECHO}) == AuditFilters(start=PISO, end=TECHO)


def test_offset_100000_se_admite_y_100001_da_field_offset() -> None:
    assert _filtros(PageParams(limit=25, offset=MAX_AUDIT_OFFSET)) == AuditFilters()
    assert _campo_invalido(PageParams(limit=25, offset=MAX_AUDIT_OFFSET + 1)) == "offset"


def test_el_error_de_rango_no_repite_el_valor() -> None:
    with pytest.raises(AuditRangeInvalid) as capturado:
        _filtros(**{"from": datetime(2019, 12, 31, 23, 59, tzinfo=UTC)})
    assert "2019" not in capturado.value.message


# AuditListQuery -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tabla",
    [
        "Members.members",
        "members.Members",
        "members.members.extra",
        "members",
        "members.",
        ".members",
        "members-x.members",
        "members.members ",
        "a" * 64 + "." + "b" * 63,
    ],
    ids=["mayus-1", "mayus-2", "tres", "uno", "vacio-2", "vacio-1", "guion", "espacio", "128"],
)
def test_table_fuera_del_patron_o_largo_se_rechaza(tabla: str) -> None:
    with pytest.raises(ValidationError) as capturado:
        AuditListQuery(table=tabla)
    assert capturado.value.errors()[0]["loc"] == ("table",)


def test_table_de_127_caracteres_con_el_patron_se_admite() -> None:
    tabla = "a" * 63 + "." + "b" * 63
    assert len(tabla) == 127
    assert AuditListQuery(table=tabla).table == tabla


@pytest.mark.parametrize("accion", ["hack", "INSERT", "", "select"])
def test_action_fuera_de_la_lista_se_rechaza(accion: str) -> None:
    with pytest.raises(ValidationError):
        AuditListQuery(action=accion)  # type: ignore[arg-type]


@pytest.mark.parametrize("accion", AUDIT_ACTIONS)
def test_toda_accion_de_la_cadena_se_admite(accion: str) -> None:
    assert AuditListQuery(action=accion).action == accion  # type: ignore[arg-type]


def test_query_sin_zona_y_campo_extra_se_rechazan() -> None:
    with pytest.raises(ValidationError):
        AuditListQuery(**{"from": datetime(2026, 10, 1)})
    with pytest.raises(ValidationError):
        AuditListQuery(entity="members")  # type: ignore[call-arg]


# blob_marker y redact_blobs (S4A-D52) --------------------------------------------------------


def test_blob_marker_de_un_blob_da_el_marcador() -> None:
    assert diff.blob_marker(BLOB) == MARCADOR


def test_blob_marker_pasa_el_key_id_a_minusculas() -> None:
    marcador = diff.blob_marker(f"apx1.{KEY.upper()}.A256GCM.n.c")
    assert marcador is not None
    assert marcador["key_id"] == KEY


@pytest.mark.parametrize(
    "valor",
    [
        "texto sin prefijo",
        "***",
        "",
        "apx1",
        "apx1.",
        f"apx1.{KEY}.A256GCM.n",
        f"apx1.{KEY}.A256GCM.n.c.d",
        "apx1.no-es-uuid.A256GCM.n.c",
        f"apx1.{KEY}..n.c",
        f"apx2.{KEY}.A256GCM.n.c",
        f"x apx1.{KEY}.A256GCM.n.c",
        None,
        42,
        {"phone": BLOB},
    ],
    ids=[
        "texto",
        "redactado",
        "vacio",
        "solo-version",
        "solo-prefijo",
        "cuatro-partes",
        "seis-partes",
        "key-no-uuid",
        "alg-vacio",
        "otra-version",
        "prefijo-en-medio",
        "none",
        "entero",
        "dict",
    ],
)
def test_blob_marker_de_lo_que_no_es_un_blob_da_none(valor: object) -> None:
    assert diff.blob_marker(valor) is None


def test_prefijo_y_separador_coinciden_con_core_crypto() -> None:
    """S4A-D17/D52: `audit` no importa `core.crypto`; la prueba fija la paridad del formato."""
    nonce = bytes(range(crypto_blob.NONCE_LEN))
    real = crypto_blob.format_blob(UUID(KEY), "A256GCM", nonce, b"texto cifrado")
    partes = crypto_types.parse_blob(real)
    assert diff.BLOB_PREFIX == crypto_blob.BLOB_PREFIX + diff.BLOB_SEPARATOR
    assert diff.BLOB_PREFIX == PREFIJO_DE_AUDITORIA
    assert diff.BLOB_PARTS == crypto_blob.PARTS
    assert len(real.split(diff.BLOB_SEPARATOR)) == diff.BLOB_PARTS
    assert diff.blob_marker(real) == {
        "encrypted": True,
        "key_id": str(partes.key_id),
        "alg": partes.alg,
    }


def test_redact_blobs_sustituye_cada_blob_tambien_anidado_y_no_muta() -> None:
    entrada: dict[str, Any] = {
        "phone": BLOB,
        "phone_idx": "***",
        "first_name": "Lucía",
        "nested": {"email": BLOB, "n": 3},
        "lista": [BLOB, "x"],
        "nada": None,
    }
    copia = {**entrada, "nested": dict(entrada["nested"]), "lista": list(entrada["lista"])}

    salida = diff.redact_blobs(entrada)

    assert salida == {
        "phone": MARCADOR,
        "phone_idx": "***",
        "first_name": "Lucía",
        "nested": {"email": MARCADOR, "n": 3},
        "lista": [MARCADOR, "x"],
        "nada": None,
    }
    assert entrada == copia
    assert "apx1." not in repr(salida)


def test_redact_blobs_de_none_y_vacio() -> None:
    assert diff.redact_blobs(None) is None
    assert diff.redact_blobs({}) == {}


# Decisiones del Verde (S4A-B4, dudas c y d) ---------------------------------------------------

OTRO_ID = UUID("0b6f7e2a-1c3d-4e5f-8a9b-0c1d2e3f4a5b")


TABLA = "members.members"


def test_record_id_explicito_manda_sobre_un_q_uuid_distinto() -> None:
    """S4A-D104: el filtro explícito `record_id` gana; el `q` UUID que choca se ignora."""
    esperado = AuditFilters(record_id=ID, table_name=TABLA)
    assert _filtros(q=str(OTRO_ID), record_id=ID, table=TABLA) == esperado
    assert _filtros(q=str(ID), record_id=ID, table=TABLA) == esperado


def test_record_id_explicito_y_q_de_texto_se_combinan() -> None:
    assert _filtros(q="ana", record_id=ID, table=TABLA) == AuditFilters(
        record_id=ID, table_name=TABLA, email_term="ana"
    )


# Revisión de seguridad de B4 (S4A-D106) -------------------------------------------------------


def test_record_id_sin_table_da_field_record_id() -> None:
    """S4A-D106 a: sin `table` el conteo no tiene índice líder."""
    assert _campo_invalido(record_id=ID) == "record_id"
    assert _campo_invalido(record_id=ID, q="ana", action="update") == "record_id"


def test_q_uuid_sin_table_no_filtra() -> None:
    assert _filtros(q=str(ID)) == AuditFilters()
    assert _filtros(q=str(ID), action="insert") == AuditFilters(action="insert")


@pytest.mark.parametrize("tabla", ["members.socios", "public.users", "audit.audit_log"])
def test_table_que_no_es_auditable_da_field_table_con_mensaje_fijo(tabla: str) -> None:
    with pytest.raises(AuditRangeInvalid) as capturado:
        _filtros(table=tabla)
    assert (capturado.value.status, capturado.value.field) == (422, "table")
    assert tabla not in capturado.value.message


def test_toda_tabla_auditable_se_admite() -> None:
    for tabla in AUDITABLE_TABLES:
        assert _filtros(table=tabla) == AuditFilters(table_name=tabla)


@pytest.mark.parametrize(
    "valor",
    [
        "apx1.",
        "apx1.basura",
        f"apx1.{KEY}.A256GCM.n",
        "apx1.no-es-uuid.A256GCM.n.c",
        f"apx1.{KEY}..n.c",
    ],
    ids=["solo-prefijo", "basura", "cuatro-partes", "key-no-uuid", "alg-vacio"],
)
def test_redact_blobs_tapa_un_apx1_mal_formado(valor: str) -> None:
    """Duda d: todo texto con el prefijo `apx1.` sale como marcador, aunque esté mal formado
    (`key_id` y `alg` nulos); nunca tal cual."""
    salida = diff.redact_blobs({"phone": valor, "lista": [valor], "x": {"y": valor}})
    marcador = {"encrypted": True, "key_id": None, "alg": None}
    assert salida == {"phone": marcador, "lista": [marcador], "x": {"y": marcador}}
    assert "apx1" not in repr(salida)


def test_diff_marca_encrypted_un_apx1_mal_formado() -> None:
    [cambio] = diff.diff(None, {"phone": "apx1.basura"}, "insert")
    assert cambio.encrypted is True
    assert cambio.after == {"encrypted": True, "key_id": None, "alg": None}


def test_diff_dos_blobs_de_la_misma_llave_son_un_cambio() -> None:
    """Se compara en crudo: los marcadores coinciden, pero el valor cifrado cambió."""
    viejo = f"apx1.{KEY}.A256GCM.bm9uY2U.YQ"
    nuevo = f"apx1.{KEY}.A256GCM.b3Rybw.Yg"
    [cambio] = diff.diff({"phone": viejo}, {"phone": nuevo}, "update")
    assert (cambio.kind, cambio.before, cambio.after) == ("changed", MARCADOR, MARCADOR)


MAL_FORMADO = {"encrypted": True, "key_id": None, "alg": None}


@pytest.mark.parametrize(
    "valor",
    [f" {BLOB}", f"x {BLOB}", f"\n{BLOB}", f"{BLOB}\n", f"texto {BLOB} texto", f"\t{BLOB}"],
    ids=["espacio", "texto-delante", "salto-delante", "salto-detras", "incrustado", "tab"],
)
def test_un_blob_con_algo_delante_o_incrustado_no_sale_tal_cual(valor: str) -> None:
    """Revisión de B4 (L): `apx1.` en cualquier posición se tapa; nunca salen nonce ni cifrado."""
    salida = diff.redact_blobs({"phone": valor, "lista": [valor]})
    assert salida == {"phone": MAL_FORMADO, "lista": [MAL_FORMADO]}
    [cambio] = diff.diff(None, {"phone": valor}, "insert")
    assert (cambio.after, cambio.encrypted) == (MAL_FORMADO, True)
    assert "apx1" not in repr(salida) and "apx1" not in repr(cambio)


def _anidado(niveles: int, hoja: Any) -> dict[str, Any]:
    valor: Any = hoja
    for _ in range(niveles):
        valor = {"n": valor}
    return valor  # type: ignore[no-any-return]


def _profundidad(valor: Any) -> int:
    nivel = 0
    while isinstance(valor, dict) and "n" in valor:
        valor, nivel = valor["n"], nivel + 1
    return nivel


def test_redact_blobs_trunca_mas_alla_de_max_depth_sin_recursion_error() -> None:
    """Revisión de B4 (L): 40 niveles no dan `RecursionError` (500); bajo 32 se trunca."""
    entrada = _anidado(40, BLOB)

    salida = diff.redact_blobs(entrada)

    assert diff.MAX_DEPTH == 32
    assert salida is not None
    assert _profundidad(salida) == diff.MAX_DEPTH
    hoja = salida
    for _ in range(diff.MAX_DEPTH):
        hoja = hoja["n"]
    assert hoja == {"truncated": True}
    assert "apx1" not in repr(salida)
    assert _profundidad(entrada) == 40


def test_diff_trunca_mas_alla_de_max_depth() -> None:
    [cambio] = diff.diff(None, {"payload": _anidado(40, "x")}, "insert")
    assert _profundidad(cambio.after) == diff.MAX_DEPTH - 1
    assert diff.redact_blobs(_anidado(diff.MAX_DEPTH - 1, BLOB)) == _anidado(
        diff.MAX_DEPTH - 1, MARCADOR
    )

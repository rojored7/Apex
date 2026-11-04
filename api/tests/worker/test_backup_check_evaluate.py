"""`backup_check.parse_manifest` y `backup_check.evaluate` (puras; S4B-B2.3; D25, D69, D80, D97).

- `evaluate`: los seis estados con la prioridad `missing > corrupt > undecryptable > stale >
  ok_unverified > ok`. Borde de edad: 24 h 0 s es `stale`, 23 h 59 min 59 s es válido.
  `created_at` a más de 5 min en el futuro, `name` que no coincide con `created_at` (UTC) o
  `size_bytes` sobre `MAX_BACKUP_BYTES` -> `corrupt`; `verify == "failed"` -> `undecryptable`;
  `verify == "skipped"` -> `ok_unverified`. `files_ok=False` -> `missing`, `sizes_ok=False` ->
  `corrupt`, `None` no pesa.
- `parse_manifest`: el manifiesto es dato no confiable; JSON inválido, versión desconocida, nombres
  con `..`, `/`, `\\` o absolutos, `sha256` mal formado, `files` sin `db` y campos extra dan `None`.
  Los tres prefijos (`apex`, `pre-deploy`, `pre-restore`) se parsean; que `latest.json` sea
  `apex-*` lo decide `run` (ver `test_backup_check.py`).
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.worker.jobs.backup_check import (
    MAX_BACKUP_BYTES,
    Manifest,
    ManifestFile,
    evaluate,
    parse_manifest,
)
from tests.factories.backup import iso_z, manifest_bytes, manifest_dict, set_name

NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)
SHA = "ab" * 32


def _manifiesto(
    creado: datetime = NOW - timedelta(hours=5),
    *,
    name: str | None = None,
    verify: str = "ok",
    size: int = 100,
) -> Manifest:
    return Manifest(
        name=name or set_name("apex", creado),
        created_at=creado,
        database="apex",
        files=(
            ManifestFile("db", "a-db.dump.age", size, SHA, SHA),
            ManifestFile("uploads", "a-uploads.tar.age", size, SHA, SHA),
        ),
        verify=verify,
        verified_at=creado + timedelta(minutes=2) if verify != "skipped" else None,
        upload="ok",
        upload_error=None,
    )


def _estado(m: Manifest, *, files_ok: bool | None = True, sizes_ok: bool | None = True) -> str:
    return evaluate(m, NOW, files_ok=files_ok, sizes_ok=sizes_ok)


# evaluate: los seis estados ----------------------------------------------------------------------


def test_un_juego_de_hace_cinco_horas_verificado_es_ok() -> None:
    assert _estado(_manifiesto()) == "ok"


def test_verify_skipped_es_ok_unverified() -> None:
    assert _estado(_manifiesto(verify="skipped")) == "ok_unverified"


def test_verify_failed_es_undecryptable() -> None:
    assert _estado(_manifiesto(verify="failed")) == "undecryptable"


def test_archivo_ausente_es_missing() -> None:
    assert _estado(_manifiesto(), files_ok=False) == "missing"


def test_tamano_o_sha256_distintos_es_corrupt() -> None:
    assert _estado(_manifiesto(), sizes_ok=False) == "corrupt"


def test_sin_comprobar_archivos_no_pesa() -> None:
    assert _estado(_manifiesto(), files_ok=None, sizes_ok=None) == "ok"


# evaluate: bordes de edad (24 h) ------------------------------------------------------------------


def test_exactamente_24_horas_es_stale() -> None:
    creado = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
    assert _estado(_manifiesto(creado)) == "stale"


def test_23_horas_59_minutos_59_segundos_es_valido() -> None:
    creado = datetime(2026, 10, 20, 12, 0, 1, tzinfo=UTC)
    assert _estado(_manifiesto(creado)) == "ok"


def test_un_juego_de_hace_varios_dias_es_stale() -> None:
    assert _estado(_manifiesto(NOW - timedelta(days=5))) == "stale"


# evaluate: L-1 (S4B-D69) ------------------------------------------------------------


def test_created_at_a_mas_de_cinco_minutos_en_el_futuro_es_corrupt() -> None:
    creado = NOW + timedelta(minutes=5, seconds=1)
    assert _estado(_manifiesto(creado)) == "corrupt"


def test_created_at_a_exactamente_cinco_minutos_en_el_futuro_se_tolera() -> None:
    creado = NOW + timedelta(minutes=5)
    assert _estado(_manifiesto(creado)) == "ok"


def test_name_que_no_coincide_con_created_at_es_corrupt() -> None:
    assert _estado(_manifiesto(name="apex-20200101-000000")) == "corrupt"


def test_name_se_compara_con_created_at_en_utc() -> None:
    # 07:00 UTC; en Bogotá serían las 02:00 y el nombre sería otro.
    creado = datetime(2026, 10, 21, 7, 0, 0, tzinfo=UTC)
    assert _estado(_manifiesto(creado, name="apex-20261021-070000")) == "ok"
    assert _estado(_manifiesto(creado, name="apex-20261021-020000")) == "corrupt"


def test_size_bytes_sobre_el_tope_es_corrupt() -> None:
    assert MAX_BACKUP_BYTES == 50 * 1024**3
    assert _estado(_manifiesto(size=MAX_BACKUP_BYTES + 1)) == "corrupt"
    assert _estado(_manifiesto(size=MAX_BACKUP_BYTES)) == "ok"


# evaluate: prioridad missing > corrupt > undecryptable > stale > ok_unverified > ok

VIEJO = NOW - timedelta(days=3)


@pytest.mark.parametrize(
    ("manifiesto", "files_ok", "sizes_ok", "esperado"),
    [
        (_manifiesto(NOW + timedelta(hours=2), verify="failed"), False, False, "missing"),
        (_manifiesto(VIEJO, verify="failed"), False, True, "missing"),
        (_manifiesto(VIEJO, verify="failed"), True, False, "corrupt"),
        (_manifiesto(NOW + timedelta(hours=2), verify="failed"), True, True, "corrupt"),
        (_manifiesto(VIEJO, verify="skipped"), True, False, "corrupt"),
        (_manifiesto(VIEJO, verify="failed"), True, True, "undecryptable"),
        (_manifiesto(VIEJO, verify="skipped"), True, True, "stale"),
        (_manifiesto(VIEJO, verify="ok"), True, True, "stale"),
        (_manifiesto(verify="skipped"), True, True, "ok_unverified"),
        (_manifiesto(verify="ok"), True, True, "ok"),
    ],
)
def test_prioridad_entre_los_seis_estados(
    manifiesto: Manifest, files_ok: bool, sizes_ok: bool, esperado: str
) -> None:
    assert _estado(manifiesto, files_ok=files_ok, sizes_ok=sizes_ok) == esperado


# parse_manifest -----------------------------------------------------------------------------------


def _valido() -> dict[str, Any]:
    db = {
        "name": "apex-20261021-070000-db.dump.age",
        "size_bytes": 10,
        "sha256": SHA,
        "plain_sha256": SHA,
    }
    up = {
        "name": "apex-20261021-070000-uploads.tar.age",
        "size_bytes": 5,
        "sha256": SHA,
        "plain_sha256": SHA,
    }
    return manifest_dict("apex-20261021-070000", datetime(2026, 10, 21, 7, tzinfo=UTC), db, up)


def test_un_manifiesto_valido_se_parsea_completo() -> None:
    m = parse_manifest(manifest_bytes(_valido()))
    assert m is not None
    assert m.name == "apex-20261021-070000"
    assert m.created_at == datetime(2026, 10, 21, 7, 0, 0, tzinfo=UTC)
    assert m.created_at.utcoffset() == timedelta(0)
    assert m.database == "apex"
    assert [(f.kind, f.name, f.size_bytes, f.sha256) for f in m.files] == [
        ("db", "apex-20261021-070000-db.dump.age", 10, SHA),
        ("uploads", "apex-20261021-070000-uploads.tar.age", 5, SHA),
    ]
    assert (m.verify, m.upload) == ("ok", "ok")


def test_verify_skipped_con_verified_at_nulo_se_parsea() -> None:
    datos = _valido()
    datos["verify"], datos["verified_at"] = "skipped", None
    m = parse_manifest(manifest_bytes(datos))
    assert m is not None
    assert (m.verify, m.verified_at) == ("skipped", None)


@pytest.mark.parametrize("prefijo", ["apex", "pre-deploy", "pre-restore"])
def test_los_tres_prefijos_se_parsean(prefijo: str) -> None:
    datos = _valido()
    datos["name"] = f"{prefijo}-20261021-070000"
    m = parse_manifest(manifest_bytes(datos))
    assert m is not None
    assert m.name == f"{prefijo}-20261021-070000"


def test_solo_db_sin_uploads_se_parsea() -> None:
    datos = _valido()
    datos["files"] = datos["files"][:1]
    assert parse_manifest(manifest_bytes(datos)) is not None


def test_parse_no_compara_name_con_created_at_eso_es_de_evaluate() -> None:
    datos = _valido()
    datos["name"] = "apex-20200101-000000"
    assert parse_manifest(manifest_bytes(datos)) is not None


def _con(cambio: Any) -> bytes:
    datos = copy.deepcopy(_valido())
    cambio(datos)
    return manifest_bytes(datos)


def _quita(clave: str) -> Any:
    return lambda d: d.pop(clave)


def _pone(clave: str, valor: Any) -> Any:
    return lambda d: d.__setitem__(clave, valor)


def _archivo(clave: str, valor: Any, indice: int = 0) -> Any:
    return lambda d: d["files"][indice].__setitem__(clave, valor)


INVALIDOS: dict[str, bytes] = {
    "json roto": b"{no es json",
    "vacío": b"",
    "no utf-8": b"\xff\xfe\x00{",
    "lista en vez de objeto": b"[]",
    "format_version 2": _con(_pone("format_version", 2)),
    "format_version ausente": _con(_quita("format_version")),
    "format_version texto": _con(_pone("format_version", "1")),
    "name con ..": _con(_pone("name", "apex-../x")),
    "name con barra": _con(_pone("name", "apex/20261021-070000")),
    "name sin fecha": _con(_pone("name", "apex-2026")),
    "name con otro prefijo": _con(_pone("name", "otro-20261021-070000")),
    "name ausente": _con(_quita("name")),
    "created_at sin Z": _con(_pone("created_at", "2026-10-21T07:00:00")),
    "created_at con offset": _con(_pone("created_at", "2026-10-21T07:00:00-05:00")),
    "created_at ausente": _con(_quita("created_at")),
    "verify desconocido": _con(_pone("verify", "maybe")),
    "upload desconocido": _con(_pone("upload", "quizá")),
    "campo extra": _con(_pone("extra", 1)),
    "archivo absoluto": _con(_archivo("name", "/etc/passwd")),
    "archivo absoluto de windows": _con(_archivo("name", "C:\\x\\a.age")),
    "archivo con barra": _con(_archivo("name", "sub/a-db.dump.age")),
    "archivo con barra invertida": _con(_archivo("name", "sub\\a-db.dump.age")),
    "archivo ..": _con(_archivo("name", "..")),
    "archivo ../x": _con(_archivo("name", "../x-db.dump.age")),
    "archivo vacío": _con(_archivo("name", "")),
    "archivo con nul": _con(_archivo("name", "a\x00b.age")),
    "sha256 corto": _con(_archivo("sha256", "ab" * 31)),
    "sha256 en mayúsculas": _con(_archivo("sha256", "AB" * 32)),
    "sha256 no hex": _con(_archivo("sha256", "zz" * 32)),
    "sha256 ausente": _con(lambda d: d["files"][0].pop("sha256")),
    "size negativo": _con(_archivo("size_bytes", -1)),
    "size texto": _con(_archivo("size_bytes", "10")),
    "size booleano": _con(_archivo("size_bytes", True)),
    "kind desconocido": _con(_archivo("kind", "logs")),
    "files vacío": _con(_pone("files", [])),
    "files ausente": _con(_quita("files")),
    "files sin db": _con(lambda d: d.__setitem__("files", d["files"][1:])),
}


@pytest.mark.parametrize("raw", list(INVALIDOS.values()), ids=list(INVALIDOS))
def test_manifiesto_invalido_da_none(raw: bytes) -> None:
    assert parse_manifest(raw) is None


def test_el_manifiesto_serializado_a_mano_tambien_se_parsea() -> None:
    texto = json.dumps(_valido())
    assert parse_manifest(texto.encode("utf-8")) is not None
    assert iso_z(NOW) == "2026-10-21T12:00:00Z"

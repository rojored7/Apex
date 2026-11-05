"""`app.cli_manifest.recent_signed_manifest` (S5-B13; S5-D72, H-1; cierra S4B-D57/D80/D149).

`recent_signed_manifest(path, pubkey, *, now, max_age=24 h, base=None,
require_openbao_snapshot=False) -> ManifestCheck(ok, reason, created_at, has_snapshot)`.
Motivos (`reason`):
- `ok`: `latest.json` con firma `minisign` válida de `pubkey`, `verify == "ok"`, de menos de 24 h
  y con `created_at` no más de 5 min en el futuro;
- `no_signature`: falta `latest.json.minisig` (o el manifiesto);
- `bad_signature`: la firma no verifica (bit cambiado, manifiesto alterado tras firmar, otra llave);
- `stale`: más de `max_age`, o `created_at` a más de 5 min en el futuro;
- `no_snapshot`: con `require_openbao_snapshot`, sin `openbao_snapshot` o con `verified = false`;
- `invalid`: manifiesto de más de 1 MiB, enlace simbólico (del manifiesto o de la firma), fuera de
  `base`, JSON ilegible o `verify != "ok"`.
`has_snapshot` es `True` solo con `openbao_snapshot.verified == true`. El orden de evaluación fija
que un manifiesto sin firma o con firma mala nunca se lee como confiable: la firma va antes que la
edad y que la instantánea.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.cli_manifest import ManifestCheck, recent_signed_manifest
from app.core.crypto import minisign
from tests.factories.backup import make_backup_dir, manifest_bytes
from tests.factories.minisign_signer import make_signing_key, write_signature

NOW = datetime(2026, 11, 4, 12, 0, 0, tzinfo=UTC)
LLAVE = make_signing_key(11)
OTRA = make_signing_key(12)


def _juego(carpeta: Path, **cambios: object) -> Path:
    cambios.setdefault("sign", LLAVE)
    return make_backup_dir(carpeta, NOW, **cambios).latest  # type: ignore[arg-type]


def _revisar(path: Path, **cambios: object) -> ManifestCheck:
    return recent_signed_manifest(path, LLAVE.pubkey, now=NOW, **cambios)  # type: ignore[arg-type]


def test_un_manifiesto_firmado_reciente_y_verificado_es_ok(tmp_path: Path) -> None:
    resultado = _revisar(_juego(tmp_path))

    assert resultado.ok is True
    assert resultado.reason == "ok"
    assert resultado.created_at == NOW - timedelta(hours=5)
    assert resultado.has_snapshot is False


def test_sin_minisig_es_no_signature(tmp_path: Path) -> None:
    latest = _juego(tmp_path, sign=None)

    resultado = _revisar(latest)

    assert (resultado.ok, resultado.reason) == (False, "no_signature")


def test_un_manifiesto_inexistente_no_es_ok(tmp_path: Path) -> None:
    resultado = _revisar(tmp_path / "latest.json")

    assert resultado.ok is False
    assert resultado.reason in {"no_signature", "invalid"}


def test_una_firma_con_un_bit_cambiado_es_bad_signature(tmp_path: Path) -> None:
    latest = _juego(tmp_path, tamper="signature")

    resultado = _revisar(latest)

    assert (resultado.ok, resultado.reason) == (False, "bad_signature")


def test_un_manifiesto_alterado_despues_de_firmar_es_bad_signature(tmp_path: Path) -> None:
    latest = _juego(tmp_path)
    latest.write_bytes(latest.read_bytes().replace(b'"verify": "ok"', b'"verify": "ok" '))

    resultado = _revisar(latest)

    assert (resultado.ok, resultado.reason) == (False, "bad_signature")


def test_la_firma_de_otra_llave_es_bad_signature(tmp_path: Path) -> None:
    latest = _juego(tmp_path, sign=OTRA)

    resultado = _revisar(latest)

    assert (resultado.ok, resultado.reason) == (False, "bad_signature")


def test_un_minisig_basura_es_bad_signature(tmp_path: Path) -> None:
    latest = _juego(tmp_path, sign=None)
    (tmp_path / "latest.json.minisig").write_text("firma de prueba\n", encoding="utf-8")

    resultado = _revisar(latest)

    assert (resultado.ok, resultado.reason) == (False, "bad_signature")


def test_mas_de_24_horas_es_stale(tmp_path: Path) -> None:
    latest = _juego(tmp_path, created_at=NOW - timedelta(hours=24, seconds=1))

    resultado = _revisar(latest)

    assert (resultado.ok, resultado.reason) == (False, "stale")


def test_justo_por_debajo_de_24_horas_es_ok(tmp_path: Path) -> None:
    latest = _juego(tmp_path, created_at=NOW - timedelta(hours=23, minutes=59))

    assert _revisar(latest).ok is True


def test_max_age_se_puede_acortar(tmp_path: Path) -> None:
    latest = _juego(tmp_path)  # hace 5 h

    assert _revisar(latest, max_age=timedelta(hours=4)).reason == "stale"
    assert _revisar(latest, max_age=timedelta(hours=6)).ok is True


def test_created_at_en_el_futuro_mas_de_5_minutos_es_stale(tmp_path: Path) -> None:
    latest = _juego(tmp_path, created_at=NOW + timedelta(minutes=6))

    resultado = _revisar(latest)

    assert (resultado.ok, resultado.reason) == (False, "stale")


def test_created_at_en_el_futuro_hasta_5_minutos_se_tolera(tmp_path: Path) -> None:
    latest = _juego(tmp_path, created_at=NOW + timedelta(minutes=4))

    assert _revisar(latest).ok is True


def test_una_firma_mala_gana_a_un_manifiesto_viejo(tmp_path: Path) -> None:
    """La firma se comprueba antes que la edad: un manifiesto no firmado no se interpreta."""
    latest = _juego(tmp_path, created_at=NOW - timedelta(days=3), tamper="signature")

    assert _revisar(latest).reason == "bad_signature"


def test_verify_distinto_de_ok_no_es_ok(tmp_path: Path) -> None:
    for verify in ("skipped", "failed"):
        carpeta = tmp_path / verify
        resultado = _revisar(_juego(carpeta, verify=verify))
        assert (resultado.ok, resultado.reason) == (False, "invalid"), verify


# Instantánea de OpenBao -----------------------------------------------------------------------


def test_con_instantanea_verificada_has_snapshot_es_true_y_se_exige_bien(tmp_path: Path) -> None:
    latest = _juego(tmp_path, snapshot=True)

    resultado = _revisar(latest, require_openbao_snapshot=True)

    assert (resultado.ok, resultado.reason, resultado.has_snapshot) == (True, "ok", True)


def test_sin_exigirla_una_instantanea_no_cambia_el_resultado(tmp_path: Path) -> None:
    resultado = _revisar(_juego(tmp_path, snapshot=True))

    assert (resultado.ok, resultado.has_snapshot) == (True, True)


def test_exigida_y_ausente_es_no_snapshot(tmp_path: Path) -> None:
    latest = _juego(tmp_path)

    resultado = _revisar(latest, require_openbao_snapshot=True)

    assert (resultado.ok, resultado.reason, resultado.has_snapshot) == (False, "no_snapshot", False)


def test_exigida_y_con_verified_false_es_no_snapshot(tmp_path: Path) -> None:
    latest = _juego(tmp_path, snapshot=True, snapshot_verified=False)

    resultado = _revisar(latest, require_openbao_snapshot=True)

    assert (resultado.ok, resultado.reason, resultado.has_snapshot) == (False, "no_snapshot", False)


def test_el_motivo_stale_gana_a_no_snapshot(tmp_path: Path) -> None:
    latest = _juego(tmp_path, created_at=NOW - timedelta(days=2))

    assert _revisar(latest, require_openbao_snapshot=True).reason == "stale"


# Rechazos de forma -----------------------------------------------------------------------------


def test_un_manifiesto_de_mas_de_1_mib_se_rechaza_como_invalid(tmp_path: Path) -> None:
    latest = _juego(tmp_path)
    latest.write_bytes(latest.read_bytes() + b" " * (1 << 20))
    write_signature(LLAVE, latest)  # firmado y válido, pero demasiado grande

    resultado = _revisar(latest)

    assert (resultado.ok, resultado.reason) == (False, "invalid")


def test_un_manifiesto_de_exactamente_1_mib_no_se_rechaza_por_tamano(tmp_path: Path) -> None:
    latest = _juego(tmp_path)
    relleno = (1 << 20) - latest.stat().st_size
    latest.write_bytes(latest.read_bytes() + b" " * relleno)
    write_signature(LLAVE, latest)

    assert latest.stat().st_size == 1 << 20
    assert _revisar(latest).ok is True


def test_json_ilegible_firmado_es_invalid(tmp_path: Path) -> None:
    latest = _juego(tmp_path)
    latest.write_bytes(b"{no es json")
    write_signature(LLAVE, latest)

    resultado = _revisar(latest)

    assert (resultado.ok, resultado.reason) == (False, "invalid")


def test_un_manifiesto_que_es_un_enlace_simbolico_se_rechaza(tmp_path: Path) -> None:
    real = _juego(tmp_path / "real")
    enlace = tmp_path / "latest.json"
    try:
        enlace.symlink_to(real)
        (tmp_path / "latest.json.minisig").symlink_to(real.with_name("latest.json.minisig"))
    except OSError:
        pytest.skip("enlaces simbólicos sin privilegios en este equipo; corren en CI/Linux")

    resultado = _revisar(enlace)

    assert resultado.ok is False
    assert resultado.reason == "invalid"


def test_una_firma_que_es_un_enlace_simbolico_se_rechaza(tmp_path: Path) -> None:
    latest = _juego(tmp_path / "m")
    otra = tmp_path / "otra"
    otra.mkdir()
    firma_real = tmp_path / "firma-real"
    firma_real.write_bytes((tmp_path / "m" / "latest.json.minisig").read_bytes())
    (otra / "latest.json").write_bytes(latest.read_bytes())
    try:
        (otra / "latest.json.minisig").symlink_to(firma_real)
    except OSError:
        pytest.skip("enlaces simbólicos sin privilegios en este equipo; corren en CI/Linux")

    resultado = _revisar(otra / "latest.json")

    assert resultado.ok is False
    assert resultado.reason in {"invalid", "no_signature"}


def test_con_base_un_manifiesto_fuera_de_ella_se_rechaza(tmp_path: Path) -> None:
    latest = _juego(tmp_path / "ajeno")

    resultado = _revisar(latest, base=tmp_path / "backups")

    assert (resultado.ok, resultado.reason) == (False, "invalid")


def test_con_base_un_manifiesto_dentro_de_ella_es_ok(tmp_path: Path) -> None:
    latest = _juego(tmp_path / "backups")

    assert _revisar(latest, base=tmp_path / "backups").ok is True


def test_no_deja_pasar_un_nombre_con_traversal_hacia_otra_carpeta(tmp_path: Path) -> None:
    latest = _juego(tmp_path / "ajeno")
    camino = tmp_path / "backups" / ".." / "ajeno" / latest.name
    (tmp_path / "backups").mkdir()

    resultado = _revisar(camino, base=tmp_path / "backups")

    assert (resultado.ok, resultado.reason) == (False, "invalid")


def test_la_pubkey_mal_formada_no_es_ok_y_no_lanza(tmp_path: Path) -> None:
    latest = _juego(tmp_path)

    resultado = recent_signed_manifest(latest, "no-es-una-llave", now=NOW)

    assert resultado.ok is False
    assert resultado.reason in {"bad_signature", "invalid"}


# Instantánea exigida: el archivo existe y coincide (S5-D177, revisión de seguridad B13: HIGH) -----


def _con_snapshot(carpeta: Path, **cambios: object) -> Path:
    return _juego(carpeta, snapshot=True, **cambios)


def _reescribir(latest: Path, cambiar: Callable[[dict[str, Any]], None]) -> None:
    datos = json.loads(latest.read_text(encoding="utf-8"))
    cambiar(datos)
    latest.write_bytes(manifest_bytes(datos))
    write_signature(LLAVE, latest)


def test_exigida_con_el_archivo_completo_es_ok(tmp_path: Path) -> None:
    resultado = _revisar(_con_snapshot(tmp_path), require_openbao_snapshot=True)

    assert (resultado.ok, resultado.reason, resultado.has_snapshot) == (True, "ok", True)


def test_exigida_y_el_archivo_borrado_por_retencion_es_no_snapshot(tmp_path: Path) -> None:
    latest = _con_snapshot(tmp_path)
    for archivo in tmp_path.glob("*-openbao.snap.age"):
        archivo.unlink()

    resultado = _revisar(latest, require_openbao_snapshot=True)

    assert (resultado.ok, resultado.reason, resultado.has_snapshot) == (False, "no_snapshot", False)


@pytest.mark.parametrize("tamper", ["snapshot_size", "snapshot_sha256"])
def test_exigida_con_tamano_o_hash_distinto_es_no_snapshot(tmp_path: Path, tamper: str) -> None:
    latest = _con_snapshot(tmp_path, tamper=tamper)

    resultado = _revisar(latest, require_openbao_snapshot=True)

    assert (resultado.ok, resultado.reason) == (False, "no_snapshot")


def test_exigida_con_el_archivo_modificado_en_disco_es_no_snapshot(tmp_path: Path) -> None:
    latest = _con_snapshot(tmp_path)
    archivo = next(tmp_path.glob("*-openbao.snap.age"))
    archivo.write_bytes(archivo.read_bytes()[:-1] + b"X")

    assert _revisar(latest, require_openbao_snapshot=True).reason == "no_snapshot"


@pytest.mark.parametrize(
    "nombre",
    [
        "../fuera-openbao.snap.age",
        "otro-20261104-070000-openbao.snap.age",
        "/etc/passwd",
        "apex-20260101-000000-openbao.snap.age",
        "",
    ],
)
def test_exigida_con_un_nombre_fuera_del_juego_es_no_snapshot(tmp_path: Path, nombre: str) -> None:
    latest = _con_snapshot(tmp_path)
    _reescribir(latest, lambda d: d["openbao_snapshot"].update(name=nombre))

    assert _revisar(latest, require_openbao_snapshot=True).reason == "no_snapshot"


@pytest.mark.parametrize(
    "cambio",
    [{"sha256": "corto"}, {"size_bytes": -1}, {"size_bytes": "10"}, {"size_bytes": True}],
)
def test_exigida_con_forma_invalida_es_no_snapshot(tmp_path: Path, cambio: dict[str, Any]) -> None:
    latest = _con_snapshot(tmp_path)
    _reescribir(latest, lambda d: d["openbao_snapshot"].update(cambio))

    assert _revisar(latest, require_openbao_snapshot=True).reason == "no_snapshot"


def test_exigida_con_la_instantanea_como_enlace_simbolico_es_no_snapshot(tmp_path: Path) -> None:
    latest = _con_snapshot(tmp_path)
    archivo = next(tmp_path.glob("*-openbao.snap.age"))
    real = tmp_path / "real.bin"
    real.write_bytes(archivo.read_bytes())
    archivo.unlink()
    try:
        archivo.symlink_to(real)
    except OSError:
        pytest.skip("enlaces simbólicos sin privilegios en este equipo; corren en CI/Linux")

    assert _revisar(latest, require_openbao_snapshot=True).reason == "no_snapshot"


def test_sin_exigirla_un_archivo_de_instantanea_ausente_no_cambia_el_resultado(
    tmp_path: Path,
) -> None:
    latest = _con_snapshot(tmp_path)
    for archivo in tmp_path.glob("*-openbao.snap.age"):
        archivo.unlink()

    assert _revisar(latest).ok is True


def test_el_manifiesto_se_abre_una_sola_vez(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S5-D178: se parsean los bytes verificados, no una segunda lectura del archivo."""
    latest = _juego(tmp_path)
    leidos: list[Path] = []
    original = minisign._read_regular

    def espia(path: Path, limit: int) -> bytes | None:
        leidos.append(path)
        return original(path, limit)

    monkeypatch.setattr(minisign, "_read_regular", espia)

    assert _revisar(latest).ok is True
    assert leidos.count(latest) == 1

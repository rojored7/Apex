"""Reglas puras de las medidas (S9-A1, US-178; S9-D3, S9-D4, S9-D32, S9-D36 L-1).

`encode_metric` y `decode_metric` convierten una medida al claro de ancho fijo que se cifra:
marca de campo (`w`, `h`, `f`, `n`) + dígitos. Así todos los blobs de un campo miden lo mismo y
un blob copiado a otra columna de la misma fila no se acepta (M-2). `notes` va como
`n` + 4 dígitos con los bytes UTF-8 del texto + texto + espacios hasta que el claro COMPLETO
(cabecera de 5 bytes incluida) mida un múltiplo de 128 bytes (L-1: oculta el largo). Los errores
nunca repiten el texto recibido ni encadenan la causa.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from app.modules.athletes.exceptions import MetricValidationError
from app.modules.results.service import score_key

if TYPE_CHECKING:
    from app.modules.results.schemas import ResultMark
    from app.modules.wods.service import WodRecordMeta

METRIC_FIELDS: Final[tuple[str, ...]] = ("weight_g", "height_cm", "body_fat_pct", "notes")
FIELD_MARKS: Final[dict[str, str]] = {
    "weight_g": "w",
    "height_cm": "h",
    "body_fat_pct": "f",
    "notes": "n",
}
WEIGHT_MIN_G: Final = 20_000
WEIGHT_MAX_G: Final = 400_000
HEIGHT_MIN_CM: Final = 50
HEIGHT_MAX_CM: Final = 250
FAT_MIN_PCT: Final = 1
FAT_MAX_PCT: Final = 75
NOTES_MAX_CHARS: Final = 500
NOTES_BLOCK_BYTES: Final = 128
NOTES_HEADER_BYTES: Final = 5  # `n` + 4 dígitos
EARLIEST_MEASURED_ON: Final = date(2000, 1, 1)
SELF_UNDO_WINDOW_H: Final = 24  # S9-D33 (M-3): ventana en la que el coach deshace lo suyo
ADMIN_ROLE: Final = "admin"
COACH_ROLE: Final = "coach"

# Campo -> (mínimo, máximo, dígitos del ancho fijo).
_NUMERIC: Final[dict[str, tuple[int, int, int]]] = {
    "weight_g": (WEIGHT_MIN_G, WEIGHT_MAX_G, 6),
    "height_cm": (HEIGHT_MIN_CM, HEIGHT_MAX_CM, 3),
    "body_fat_pct": (FAT_MIN_PCT, FAT_MAX_PCT, 2),
}
_OPAQUE: Final = "La medida guardada no es válida."


class MetricDecodeError(ValueError):
    """Un claro que no decodifica (marca ajena, largo o dígitos inválidos): mensaje fijo, opaco."""


def _opaque() -> MetricDecodeError:
    return MetricDecodeError(_OPAQUE)


def _check_field(field: str) -> None:
    if field not in FIELD_MARKS:
        raise ValueError("campo de medida desconocido")


def _out_of_range(field: str) -> MetricValidationError:
    return MetricValidationError(message="El valor está fuera del rango permitido.", field=field)


def _notes_padded_size(raw_len: int) -> int:
    total = NOTES_HEADER_BYTES + raw_len
    return -(-total // NOTES_BLOCK_BYTES) * NOTES_BLOCK_BYTES


def encode_metric(field: str, value: int | str) -> str:
    """Claro de ancho fijo con marca de campo; `MetricValidationError` si el valor no cabe."""
    _check_field(field)
    if field == "notes":
        if not isinstance(value, str) or not 1 <= len(value) <= NOTES_MAX_CHARS:
            raise _out_of_range(field)
        raw = value.encode("utf-8")
        cuerpo = f"n{len(raw):04d}{value}"
        return cuerpo + " " * (_notes_padded_size(len(raw)) - len(cuerpo.encode("utf-8")))
    minimo, maximo, digitos = _NUMERIC[field]
    if isinstance(value, bool) or not isinstance(value, int) or not minimo <= value <= maximo:
        raise _out_of_range(field)
    return f"{FIELD_MARKS[field]}{value:0{digitos}d}"


def _decode_notes(text: str) -> str:
    raw = text.encode("utf-8")
    if len(raw) < NOTES_HEADER_BYTES or raw[:1] != b"n" or len(raw) % NOTES_BLOCK_BYTES:
        raise _opaque()
    cuenta = raw[1:NOTES_HEADER_BYTES]
    if not (cuenta.isascii() and cuenta.isdigit()):
        raise _opaque()
    largo = int(cuenta)
    if (
        not 1 <= largo <= NOTES_MAX_CHARS * 4
        or NOTES_HEADER_BYTES + largo > len(raw)
        or len(raw) != _notes_padded_size(largo)
    ):
        raise _opaque()
    relleno = raw[NOTES_HEADER_BYTES + largo :]
    if relleno.strip(b" "):
        raise _opaque()
    try:
        return raw[NOTES_HEADER_BYTES : NOTES_HEADER_BYTES + largo].decode("utf-8")
    except UnicodeDecodeError:
        raise _opaque() from None


def decode_metric(field: str, text: str) -> int | str:
    """Inverso de `encode_metric`. Exige marca, largo exacto, dígitos ASCII y rango."""
    _check_field(field)
    if field == "notes":
        return _decode_notes(text)
    minimo, maximo, digitos = _NUMERIC[field]
    if len(text) != 1 + digitos or text[0] != FIELD_MARKS[field]:
        raise _opaque()
    cifras = text[1:]
    if not (cifras.isascii() and cifras.isdigit()):
        raise _opaque()
    valor = int(cifras)
    if not minimo <= valor <= maximo:
        raise _opaque()
    return valor


def validate_metric(
    *,
    measured_on: date,
    weight_g: int | None,
    height_cm: int | None,
    body_fat_pct: int | None,
    notes: str | None,
    today: date,
) -> None:
    """422 con `field` (sin repetir el valor). `today` es la fecha civil de Bogotá."""
    if not EARLIEST_MEASURED_ON <= measured_on <= today:
        raise MetricValidationError(
            message="La fecha de la medición no es válida.", field="measured_on"
        )
    valores: dict[str, int | None] = {
        "weight_g": weight_g,
        "height_cm": height_cm,
        "body_fat_pct": body_fat_pct,
    }
    for campo, valor in valores.items():
        if valor is not None:
            minimo, maximo, _ = _NUMERIC[campo]
            if not minimo <= valor <= maximo:
                raise _out_of_range(campo)
    if notes is not None and not 1 <= len(notes) <= NOTES_MAX_CHARS:
        raise _out_of_range("notes")
    if all(v is None for v in valores.values()):
        raise MetricValidationError(
            message="Registra al menos una medida: peso, estatura o grasa.", field="weight_g"
        )


def can_void(
    *,
    role: str,
    caller: UUID,
    recorded_by: UUID,
    created_at: datetime,
    now: datetime,
) -> bool:
    """M-3 (S9-D33): el admin anula todo; el coach solo lo que registró él y hasta
    `SELF_UNDO_WINDOW_H` horas después de crearlo (la hora 24 exacta aún cuenta). Un `now`
    anterior a `created_at` (reloj desfasado) cuenta como dentro de la ventana."""
    if role == ADMIN_ROLE:
        return True
    if role != COACH_ROLE or recorded_by != caller:
        return False
    return now - created_at <= timedelta(hours=SELF_UNDO_WINDOW_H)


# S9-B1 (US-180; S9-D10, N-45): el récord vigente ------------------------------------------------


@dataclass(frozen=True, slots=True)
class RecordRow:
    """Lo que `pick_current` necesita de un récord: sin ORM ni nombres (pura)."""

    id: UUID
    kind: str
    movement_id: UUID | None
    benchmark_id: UUID | None
    value_g: int | None
    level: str | None
    seconds: int | None
    rounds: int | None
    reps: int | None
    load_g: int | None
    capped: bool
    achieved_on: date
    created_at: datetime
    invalidated_at: datetime | None = None
    source: str = "manual"


@dataclass(frozen=True, slots=True)
class _Score:
    """La marca de un récord con la forma de `results.ScoreLike`."""

    level: str
    seconds: int | None
    rounds: int | None
    reps: int | None
    load_g: int | None
    capped: bool


def pick_current(
    records: Sequence[RecordRow], *, score_type: str | None = None
) -> RecordRow | None:
    """El récord vigente entre los NO invalidados de UN mismo objetivo (S9-D10, N-45).

    RM: el mayor `value_g`. Benchmark: el de menor `results.service.score_key(score_type)`
    (`score_type` es obligatorio con filas `benchmark`: `ValueError` si falta). Empate: el
    `achieved_on` más antiguo, luego el `created_at` más antiguo y, al final, el id menor (orden
    total, sin depender del orden de entrada). Vacía o solo invalidados: `None`.
    """
    vivos = [r for r in records if r.invalidated_at is None]
    if not vivos:
        return None
    if any(r.kind == "benchmark" for r in vivos):
        if score_type is None:
            raise ValueError("score_type es obligatorio con récords de benchmark")
        clave = score_key(score_type)

        def orden(r: RecordRow) -> tuple[Any, ...]:
            marca = _Score(r.level or "rx", r.seconds, r.rounds, r.reps, r.load_g, r.capped)
            return (clave(marca), r.achieved_on, r.created_at, r.id)
    else:

        def orden(r: RecordRow) -> tuple[Any, ...]:
            return (-(r.value_g or 0), r.achieved_on, r.created_at, r.id)

    return min(vivos, key=orden)


# S9-B3 (US-181, S9-D10): derivar un RM de una marca de carga ------------------------------------


@dataclass(frozen=True, slots=True)
class RecordDraft:
    """Un récord derivado listo para insertar (puro, sin ORM): el objetivo, la marca y de qué
    resultado y WOD nace. `kind = "rm"` lleva `movement_id` y `value_g`; `kind = "benchmark"`
    (B4) lleva `benchmark_id` y las marcas. `achieved_on` es la fecha del WOD."""

    kind: str
    movement_id: UUID | None
    benchmark_id: UUID | None
    value_g: int | None
    level: str | None
    seconds: int | None
    rounds: int | None
    reps: int | None
    load_g: int | None
    capped: bool
    achieved_on: date
    result_id: UUID
    wod_id: UUID


def derive_rm(
    mark: ResultMark, meta: WodRecordMeta, current: RecordRow | None
) -> RecordDraft | None:
    """RM derivado (S9-D10): solo `meta.score_type == "load"` con movimiento principal, nivel
    distinto de `scaled`, `load_g` mayor que 0 y ESTRICTAMENTE mayor que el vigente (o sin
    vigente). `rx_plus` deriva igual que `rx`."""
    if meta.score_type != "load" or meta.primary_movement_id is None:
        return None
    if mark.level == "scaled" or mark.load_g is None or mark.load_g <= 0:
        return None
    if current is not None and mark.load_g <= (current.value_g or 0):
        return None
    return RecordDraft(
        kind="rm",
        movement_id=meta.primary_movement_id,
        benchmark_id=None,
        value_g=mark.load_g,
        level=None,
        seconds=None,
        rounds=None,
        reps=None,
        load_g=None,
        capped=False,
        achieved_on=mark.wod_date,
        result_id=mark.result_id,
        wod_id=mark.wod_id,
    )


# Los campos que exige cada tipo de marca (la misma forma de `results/rules.validate_score`).
_BENCHMARK_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    "time": ("seconds",),
    "rounds_reps": ("rounds", "reps"),
    "reps": ("reps",),
    "load": ("load_g",),
}


def _has_score(mark: ResultMark, score_type: str) -> bool:
    """La marca trae el campo de su `score_type` (`capped` suma `reps`); una carga de 0 g no es
    récord (coherente con `derive_rm`, S9-D59)."""
    campos = _BENCHMARK_FIELDS[score_type] + (("reps",) if mark.capped else ())
    if any(getattr(mark, c) is None for c in campos):
        return False
    return score_type != "load" or (mark.load_g or 0) > 0


def derive_benchmark(
    mark: ResultMark, meta: WodRecordMeta, current: RecordRow | None
) -> RecordDraft | None:
    """Récord de benchmark derivado (S9-D10, US-182): solo si el WOD es de un benchmark, la marca
    es de ESE benchmark y es ESTRICTAMENTE mejor que la vigente según `score_key` (el orden del
    leaderboard): el empate no crea, un `scaled` nunca gana a un `rx`, `rx_plus` compite con `rx`
    y un `capped` puede ser el primero pero va detrás de todo el que terminó. No derivan un tipo
    sin leaderboard, una marca sin el campo de su tipo (la forma de la tabla exige uno) ni una
    carga de 0 g."""
    if meta.benchmark_id is None or mark.benchmark_id != meta.benchmark_id:
        return None
    if meta.score_type not in _BENCHMARK_FIELDS or not _has_score(mark, meta.score_type):
        return None
    clave = score_key(meta.score_type)
    if current is not None:
        vigente = _Score(
            current.level or "rx",
            current.seconds,
            current.rounds,
            current.reps,
            current.load_g,
            current.capped,
        )
        if not clave(mark) < clave(vigente):
            return None
    return RecordDraft(
        kind="benchmark",
        movement_id=None,
        benchmark_id=meta.benchmark_id,
        value_g=None,
        level=mark.level,
        seconds=mark.seconds,
        rounds=mark.rounds,
        reps=mark.reps,
        load_g=mark.load_g,
        capped=mark.capped,
        achieved_on=mark.wod_date,
        result_id=mark.result_id,
        wod_id=mark.wod_id,
    )


# S9-B5 (US-181, S9-D11): la reposición del mejor tras invalidar ---------------------------------


def best_candidate(
    candidates: Sequence[ResultMark],
    *,
    kind: Literal["rm", "benchmark"],
    score_type: str | None,
    current: RecordRow | None,
) -> ResultMark | None:
    """La marca que debe reponerse como récord, o `None` (S9-D11; pura, sin ORM).

    `candidates` son marcas vigentes y validadas del MISMO objetivo SIN récord vivo (el filtro lo
    hace quien llama). Contrato:
    - `kind="rm"`: elegibles las que no son `scaled` y traen `load_g` mayor que 0; gana el mayor
      `load_g`; vuelve solo si es ESTRICTAMENTE mayor que `current.value_g` (o sin vigente).
    - `kind="benchmark"` (`score_type` obligatorio: `ValueError` si falta): elegibles las que traen
      el campo de su tipo (la regla de `derive_benchmark`); gana la de menor `score_key`; vuelve
      solo si es ESTRICTAMENTE mejor que la del vigente.
    - Empate entre candidatas: la de `wod_date` más antigua y, luego, el `result_id` menor (N-45).
    - Sin candidatas elegibles: `None`. No muta la entrada.
    """
    if kind == "rm":
        elegibles = [
            m for m in candidates if m.level != "scaled" and m.load_g is not None and m.load_g > 0
        ]
        if not elegibles:
            return None
        mejor = min(elegibles, key=lambda m: (-(m.load_g or 0), m.wod_date, m.result_id))
        if current is not None and (mejor.load_g or 0) <= (current.value_g or 0):
            return None
        return mejor
    if score_type is None:
        raise ValueError("score_type es obligatorio con kind benchmark")
    if score_type not in _BENCHMARK_FIELDS:
        return None
    clave = score_key(score_type)
    elegibles = [m for m in candidates if _has_score(m, score_type)]
    if not elegibles:
        return None
    mejor = min(elegibles, key=lambda m: (clave(m), m.wod_date, m.result_id))
    if current is not None:
        vigente = _Score(
            current.level or "rx",
            current.seconds,
            current.rounds,
            current.reps,
            current.load_g,
            current.capped,
        )
        if not clave(mejor) < clave(vigente):
            return None
    return mejor


# S9-C1 (US-183, S9-D6): la serie de un benchmark -----------------------------------------------


@dataclass(frozen=True, slots=True)
class Attempt:
    """Un intento de la serie: la marca y lo que la serie decide sobre ella."""

    mark: ResultMark
    is_best: bool
    level_changed: bool


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    """Un benchmark con intentos: cuántos, el mejor y la fecha del último."""

    benchmark_id: UUID
    attempts: int
    best: ResultMark
    last_on: date


def _best_index(marks: Sequence[ResultMark], score_type: str) -> int:
    """Posición de la mejor marca: menor `score_key`; en empate, la primera de la entrada."""
    clave = score_key(score_type)
    return min(range(len(marks)), key=lambda i: (clave(marks[i]), i))


def benchmark_series(marks: Sequence[ResultMark], score_type: str) -> list[Attempt]:
    """La serie de intentos de UN benchmark (pura).

    `marks` llega en orden cronológico ascendente y ese orden se conserva. Exactamente un
    `is_best` (el de menor `results.score_key(score_type)`; en empate, el primero de la entrada);
    `level_changed` es verdadero si el nivel difiere del intento anterior (el primero, falso).
    Entrada vacía, salida vacía. No muta la entrada.
    """
    if not marks:
        return []
    mejor = _best_index(marks, score_type)
    return [
        Attempt(
            mark=m,
            is_best=i == mejor,
            level_changed=i > 0 and m.level != marks[i - 1].level,
        )
        for i, m in enumerate(marks)
    ]


def summarize_benchmarks(
    marks: Sequence[ResultMark], score_types: Mapping[UUID, str]
) -> list[BenchmarkSummary]:
    """Agrupa marcas de varios benchmarks (pura).

    `marks` llega en orden cronológico ascendente. Por `benchmark_id`: número de intentos, el
    mejor (misma regla de `benchmark_series`) y la mayor `wod_date`. Una marca sin `benchmark_id`
    o cuyo benchmark falta en `score_types` se ignora. Orden de salida: primera aparición."""
    grupos: dict[UUID, list[ResultMark]] = {}
    for m in marks:
        if m.benchmark_id is not None and m.benchmark_id in score_types:
            grupos.setdefault(m.benchmark_id, []).append(m)
    return [
        BenchmarkSummary(
            benchmark_id=bid,
            attempts=len(grupo),
            best=grupo[_best_index(grupo, score_types[bid])],
            last_on=max(m.wod_date for m in grupo),
        )
        for bid, grupo in grupos.items()
    ]


# S9-C2 (US-184, S9-D10, S9-D27): el resumen del atleta -------------------------------------------

RECENT_RECORDS: Final = 3  # US-184 CA1: los últimos tres récords


@dataclass(frozen=True, slots=True)
class RecordsDigest:
    """Lo que el resumen saca de los récords vivos: cuántos RM vigentes y los más recientes."""

    current_rms: int
    recent: tuple[RecordRow, ...]


def current_records(
    records: Sequence[RecordRow], score_types: Mapping[UUID, str]
) -> list[RecordRow]:
    """El récord vigente de cada objetivo (pura): `pick_current` por movimiento o benchmark.

    Un benchmark cuyo tipo de marca falta en `score_types` se ignora (no se puede ordenar). Los
    invalidados no cuentan. Sin orden garantizado en la salida."""
    grupos: dict[tuple[str, UUID], list[RecordRow]] = {}
    for fila in records:
        destino = fila.movement_id if fila.kind == "rm" else fila.benchmark_id
        if destino is not None:
            grupos.setdefault((fila.kind, destino), []).append(fila)
    vigentes: list[RecordRow] = []
    for (tipo, destino), grupo in grupos.items():
        if tipo == "benchmark":
            if destino not in score_types:
                continue
            elegido = pick_current(grupo, score_type=score_types[destino])
        else:
            elegido = pick_current(grupo)
        if elegido is not None:
            vigentes.append(elegido)
    return vigentes


def summarize_records(
    records: Sequence[RecordRow],
    score_types: Mapping[UUID, str],
    *,
    recent_limit: int = RECENT_RECORDS,
) -> RecordsDigest:
    """Resumen de los récords (pura): RM vigentes y los más recientes entre los vigentes.

    `recent`: por `achieved_on`, `created_at` e id descendentes (orden total), a lo sumo
    `recent_limit`."""
    vigentes = current_records(records, score_types)
    recientes = sorted(vigentes, key=lambda r: (r.achieved_on, r.created_at, r.id), reverse=True)
    return RecordsDigest(
        current_rms=sum(1 for r in vigentes if r.kind == "rm"),
        recent=tuple(recientes[: max(recent_limit, 0)]),
    )

// S9-F3 · US-183 (Atleta_Perfil.html, subpestaña «Benchmarks»): la serie de un benchmark del socio.
// - GET /athletes/{id}/benchmarks (los chips; se piden páginas de 200 hasta 1.000 y se avisa si no caben) y
//   GET /athletes/{id}/benchmarks/{benchmark_id} (la serie: hasta 200 intentos por fecha ascendente, sin paginar).
// - Chips en el grupo «Benchmark» con `?bm=<id>`; sin parámetro (o con uno que no está en la lista) vale el primero.
// - Tabla «Intentos del socio en <nombre>»: Fecha, Marca, Nivel y Diferencia, del intento más reciente al más antiguo (como el diseño);
//   la gráfica va en orden cronológico. La diferencia se calcula contra el intento ANTERIOR EN EL TIEMPO, sea cual sea el orden de pintado.
// - «Mejor» con texto; «Primera vez»; «Cambió de nivel» (sin número) si el nivel cambió; «—» si no se puede comparar (rondas + repeticiones, DNF).
// - Solo lectura: no hay acciones, así que un socio dado de baja se ve igual.
// DESIGN-GAP: la columna «Escaló» del diseño no está en el contrato (AttemptOut no trae lo que escaló); «Solo se compara entre intentos del mismo
// nivel.» va como nota. El selector del diseño es un <select>; el plan manda chips.
import { useSearchParams } from "react-router";
import type { ApiError } from "../../../core/api/errors";
import { formatCount, formatDate } from "../../../core/i18n/format";
import { LEVEL_LABELS } from "../../../shared/data/results";
import { formatScore, formatScoreDelta, type ScoreKind, type ScoreValues } from "../../../shared/data/score";
import { Button } from "../../../shared/ui/Button";
import { Chips } from "../../../shared/ui/Chips";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { TrendChart, type TrendPoint } from "../../../shared/ui/TrendChart";
import { BENCHMARKS_MAX_PAGES, BENCHMARKS_PAGE_LIMIT, useAthleteBenchmarks, useBenchmarkSeries } from "../api";
import { benchmarkSeriesError, benchmarksListError } from "../recordErrors";
import { SERIES_MAX_ATTEMPTS, type AttemptView, type BenchmarkRowView, type BenchmarkSeriesView } from "../schemas";
import styles from "./BenchmarksTab.module.css";

export interface BenchmarksTabProps {
  memberId: string;
}

export const BENCHMARKS_EMPTY = "Sin intentos en benchmarks";
const BENCHMARKS_EMPTY_HELP = "Aquí aparecen los benchmarks que el socio haga en una clase con resultado validado.";
const SAME_LEVEL_NOTE = "Solo se compara entre intentos del mismo nivel.";
const TRUNCATED_SERIES = `Se muestran los ${String(SERIES_MAX_ATTEMPTS)} intentos más recientes.`;
const TRUNCATED_LIST = `Se muestran los primeros ${formatCount(BENCHMARKS_PAGE_LIMIT * BENCHMARKS_MAX_PAGES)} benchmarks.`;
const FIRST_TIME = "Primera vez";
const LEVEL_CHANGED = "Cambió de nivel";
const NO_DELTA = "—";
const ROUNDS_FACTOR = 1000;
/** Las repeticiones de una ronda parcial caben en 0 a 999: así «rondas × 1000 + reps» ordena como la marca. */
const MAX_PLOT_REPS = ROUNDS_FACTOR - 1;
/** El benchmark elegido; no se llama `benchmark` porque la pestaña Resultados usa `?benchmark=true` (V7, M2). */
const PARAM = "bm";

interface AttemptRow {
  attempt: AttemptView;
  mark: string;
  delta: string;
}

const valuesOf = (attempt: AttemptView): ScoreValues => ({ seconds: attempt.seconds, rounds: attempt.rounds, reps: attempt.reps, load_g: attempt.load_g, capped: attempt.capped });

/**
 * La diferencia de un intento con el anterior en el tiempo (`previous`, undefined en el primero). Con la serie truncada el más antiguo
 * mostrado no es el primero del socio: no se puede decir «Primera vez».
 */
function deltaText(kind: ScoreKind, attempt: AttemptView, previous: AttemptView | undefined, truncated: boolean): string {
  if (previous === undefined) return truncated ? NO_DELTA : FIRST_TIME;
  if (attempt.level !== previous.level) return LEVEL_CHANGED;
  return formatScoreDelta(kind, valuesOf(attempt), valuesOf(previous)) ?? NO_DELTA;
}

/** Los intentos por fecha ascendente (la fecha manda; a igual fecha, el orden del api) con su marca y su diferencia. */
function chronology(attempts: readonly AttemptView[], kind: ScoreKind, truncated: boolean): AttemptRow[] {
  const sorted = attempts.map((attempt, index) => ({ attempt, index })).sort((a, b) => a.attempt.wod_date.localeCompare(b.attempt.wod_date) || a.index - b.index);
  return sorted.map(({ attempt }, position) => ({
    attempt,
    mark: formatScore(kind, valuesOf(attempt)),
    delta: deltaText(kind, attempt, sorted[position - 1]?.attempt, truncated),
  }));
}

/** Un número que crece con el resultado y se puede dibujar; null si el intento no trae la marca de su tipo. */
function plotValue(kind: ScoreKind, attempt: AttemptView): number | null {
  switch (kind) {
    case "time":
      return attempt.seconds;
    case "reps":
      return attempt.reps;
    case "load":
      return attempt.load_g;
    case "rounds_reps":
      return attempt.rounds === null ? null : attempt.rounds * ROUNDS_FACTOR + Math.min(attempt.reps ?? 0, MAX_PLOT_REPS);
    default:
      return null;
  }
}

/** Solo los intentos del MISMO nivel que el más reciente y sin cortar (DNF): lo demás no se compara (la tabla los sigue mostrando). */
function chartPoints(rows: readonly AttemptRow[], kind: ScoreKind, level: AttemptView["level"]): TrendPoint[] {
  return rows.flatMap(({ attempt, mark }) => {
    if (attempt.capped || attempt.level !== level) return [];
    const value = plotValue(kind, attempt);
    return value === null ? [] : [{ id: attempt.result_id, label: formatDate(attempt.wod_date), value, text: mark, isBest: attempt.is_best }];
  });
}

const COLUMNS: Column<AttemptRow>[] = [
  { key: "wod_date", header: "Fecha", render: ({ attempt }) => <span className={styles.nowrap}>{formatDate(attempt.wod_date)}</span> },
  {
    key: "mark",
    header: "Marca",
    render: ({ attempt, mark }) => (
      <span className={styles.nowrap}>
        <b>{mark}</b>
        {attempt.is_best ? <StatusTag mark="best" className={styles.best} /> : null}
      </span>
    ),
  },
  { key: "level", header: "Nivel", render: ({ attempt }) => LEVEL_LABELS[attempt.level] },
  { key: "delta", header: "Diferencia", render: ({ delta }) => <span className={styles.nowrap}>{delta}</span> },
];

function ErrorNotice({ error, onRetry }: { error: ApiError; onRetry: () => void }) {
  return (
    <div role="alert" className={styles.error}>
      <p className={styles.errorText}>{error.message}</p>
      <Button variant="secondary" onClick={onRetry}>
        Reintentar
      </Button>
    </div>
  );
}

function SeriesBody({ benchmark, series, kind }: { benchmark: BenchmarkRowView; series: BenchmarkSeriesView; kind: ScoreKind }) {
  const chronological = chronology(series.attempts, kind, series.truncated);
  const latest = chronological[chronological.length - 1];
  const rows = [...chronological].reverse();
  return (
    <div className={styles.panel}>
      {latest ? (
        <div className={styles.chart}>
          <p className={styles.legend}>{`Gráfica de intentos en ${LEVEL_LABELS[latest.attempt.level]}`}</p>
          <TrendChart title={benchmark.name} points={chartPoints(chronological, kind, latest.attempt.level)} lowerIsBetter={kind === "time"} />
        </div>
      ) : null}
      <DataTable caption={`Intentos del socio en ${benchmark.name}`} columns={COLUMNS} rows={rows} total={rows.length} rowKey={(row) => row.attempt.result_id} />
      <p className={styles.note}>{SAME_LEVEL_NOTE}</p>
      {series.truncated ? <p className={styles.note}>{TRUNCATED_SERIES}</p> : null}
    </div>
  );
}

function Series({ memberId, benchmark }: { memberId: string; benchmark: BenchmarkRowView }) {
  const series = useBenchmarkSeries(memberId, benchmark.benchmark_id);
  const error = benchmarkSeriesError(series.error);
  const data = series.data;
  const notice = error ? (
    <ErrorNotice
      error={error}
      onRetry={() => {
        void series.refetch();
      }}
    />
  ) : null;
  // Sin datos el error es toda la serie; con datos (falló una relectura de fondo) va junto a ellos y no los tapa (V7, M10).
  if (data === undefined) {
    return notice ?? <DataTable caption={`Cargando los intentos del socio en ${benchmark.name}`} columns={COLUMNS} rows={undefined} isLoading rowKey={(row) => row.attempt.result_id} />;
  }
  if (data.attempts.length === 0) {
    return (
      <>
        {notice}
        <p className={styles.emptyHelp}>{`Este socio todavía no tiene intentos validados en ${benchmark.name}.`}</p>
      </>
    );
  }
  return (
    <>
      {notice}
      <SeriesBody benchmark={benchmark} series={data} kind={data.score_type} />
    </>
  );
}

function ListState({ isLoading, error, onRetry }: { isLoading: boolean; error: ApiError | null; onRetry: () => void }) {
  if (isLoading) return <p role="status">Cargando benchmarks…</p>;
  return error ? <ErrorNotice error={error} onRetry={onRetry} /> : null;
}

export function BenchmarksTab({ memberId }: BenchmarksTabProps) {
  const [params, setParams] = useSearchParams();
  const list = useAthleteBenchmarks(memberId);
  const rows = list.data?.items ?? [];
  const selected = rows.find((row) => row.benchmark_id === params.get(PARAM)) ?? rows[0];
  const choose = (next: string[]): void => {
    const id = next[0];
    if (id === undefined) return;
    setParams((current) => {
      const copy = new URLSearchParams(current);
      copy.set(PARAM, id);
      return copy;
    });
  };

  return (
    <div className={styles.tab}>
      <h2 className={styles.title}>Benchmarks</h2>
      <ListState
        isLoading={list.isLoading}
        error={benchmarksListError(list.error)}
        onRetry={() => {
          void list.refetch();
        }}
      />
      {list.isSuccess && rows.length === 0 ? (
        <div className={styles.empty}>
          <p className={styles.emptyTitle}>{BENCHMARKS_EMPTY}</p>
          <p className={styles.emptyHelp}>{BENCHMARKS_EMPTY_HELP}</p>
        </div>
      ) : null}
      {selected ? (
        <>
          <Chips label="Benchmark" mode="single" options={rows.map((row) => ({ value: row.benchmark_id, label: row.name }))} value={[selected.benchmark_id]} onChange={choose} />
          {list.data?.truncated ? <p className={styles.note}>{TRUNCATED_LIST}</p> : null}
          <Series key={selected.benchmark_id} memberId={memberId} benchmark={selected} />
        </>
      ) : null}
    </div>
  );
}

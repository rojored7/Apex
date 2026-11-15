// S8-F2 · US-166 (front): /wods (WOD_Lista.html), admin y coach (`wods.view`).
// - Vista «Semana» (por defecto): `?semana=AAAA-Www`, GET /wods?week=; hoy resaltado y «+ Crear» a /wods/nuevo?date=.
// - Vista «Lista» (`?vista=lista`): GET /wods?q&benchmark&limit&offset paginado en el servidor, con «Solo benchmarks».
// - `?dia=hoy` lleva a la semana actual. Estados: carga, vacío con camino a crear, error con Reintentar y permiso denegado.
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { formatDate, todayBogota } from "../../../core/i18n/format";
import { currentWeek, parseWeek, shiftWeek, weekDates, weekLabel } from "../../../shared/data/weeks";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { FilterBar } from "../../../shared/ui/FilterBar";
import { MessagePage } from "../../../shared/ui/MessagePage";
import { PageHeader } from "../../../shared/ui/PageHeader";
import { Pagination } from "../../../shared/ui/Pagination";
import { Segmented } from "../../../shared/ui/Segmented";
import { resultsText, WeekCalendar } from "../components/WeekCalendar";
import { wodsListError } from "../wodFormErrors";
import { WOD_SCORE_LABELS, type WodRowView } from "../wodSchemas";
import { useWods, type WodsParams } from "../wodsApi";
import styles from "./WodListPage.module.css";

export const WEEK_EMPTY = "Esta semana todavía no tiene WODs.";
export const LIST_EMPTY = "Todavía no hay WODs. Crea el primero para que los coaches registren resultados.";
export const LIST_EMPTY_FILTERED = "No hay WODs que coincidan con la búsqueda";
const WEEK_LIMIT = 50;
const VIEWS = [
  { value: "semana", label: "Semana" },
  { value: "lista", label: "Lista" },
] as const;

const LIST_COLUMNS: Column<WodRowView>[] = [
  { key: "date", header: "Fecha", render: (row) => formatDate(row.date) },
  {
    key: "title",
    header: "WOD",
    render: (row) => (
      <Link to={`/wods/${encodeURIComponent(row.id)}`}>
        <b>{row.title}</b>
      </Link>
    ),
  },
  { key: "score_type", header: "Tipo de marca", render: (row) => WOD_SCORE_LABELS[row.score_type] },
  { key: "benchmark", header: "Benchmark", render: (row) => (row.is_benchmark ? "Benchmark" : "—") },
  { key: "movements", header: "Movimientos", render: (row) => row.movement_names.join(" · ") },
  { key: "results", header: "Resultados", align: "end", render: (row) => resultsText(row.result_count) },
];

function WeekView() {
  const [search, setSearch] = useSearchParams();
  const week = search.get("dia") === "hoy" ? currentWeek() : (parseWeek(search.get("semana")) ?? currentWeek());
  const wods = useWods({ limit: WEEK_LIMIT, offset: 0, week });
  const dates = weekDates(week);
  const go = (target: string | null): void => {
    if (target === null) return;
    setSearch((current) => {
      const next = new URLSearchParams(current);
      next.delete("dia");
      next.set("semana", target);
      return next;
    });
  };
  const items = wods.data?.items ?? [];
  const settled = wods.data !== undefined && !wods.isPlaceholderData;

  return (
    <div className={styles.content}>
      <div className={styles.weekBar}>
        <Button
          variant="secondary"
          onClick={() => {
            go(shiftWeek(week, -1));
          }}
        >
          Semana anterior
        </Button>
        <p className={styles.weekLabel} aria-live="polite">
          {weekLabel(week)}
        </p>
        <Button
          variant="secondary"
          onClick={() => {
            go(shiftWeek(week, 1));
          }}
        >
          Semana siguiente
        </Button>
        <Button
          variant="ghost"
          onClick={() => {
            go(currentWeek());
          }}
        >
          Hoy
        </Button>
      </div>
      {wods.isError ? (
        <div role="alert" className={styles.error}>
          <p>{wodsListError(wods.error)?.message}</p>
          <Button variant="secondary" onClick={() => void wods.refetch()}>
            Reintentar
          </Button>
        </div>
      ) : wods.isLoading ? (
        <p role="status" className={styles.loading}>
          Cargando la semana…
        </p>
      ) : (
        <>
          {settled && items.length === 0 ? <p className={styles.empty}>{WEEK_EMPTY} Elige un día para crear el primero.</p> : null}
          <WeekCalendar dates={dates} wods={items} today={todayBogota()} />
        </>
      )}
    </div>
  );
}

function ListView() {
  const list = useListParams<"benchmark">({ filters: ["benchmark"], localQuery: true });
  const onlyBenchmarks = list.filters.benchmark[0] === "true";
  const { limit, offset } = list.params;
  const { q } = list;
  const params = useMemo<WodsParams>(() => ({ limit, offset, ...(q ? { q } : {}), ...(onlyBenchmarks ? { benchmark: true } : {}) }), [limit, offset, q, onlyBenchmarks]);
  const wods = useWods(params);
  const page = wods.data;
  const isFiltered = Boolean(q) || onlyBenchmarks;

  return (
    <div className={styles.content}>
      <FilterBar query={list.q} onQueryChange={list.setQuery} onClear={list.clear} searchLabel="Buscar WOD" searchPlaceholder="Buscar por título (Fran, Cindy…)" />
      <label className={styles.check}>
        <input
          type="checkbox"
          checked={onlyBenchmarks}
          onChange={(event) => {
            list.setFilter("benchmark", event.target.checked ? "true" : undefined);
          }}
        />
        Solo benchmarks
      </label>
      <DataTable
        caption="WODs"
        columns={LIST_COLUMNS}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(row) => row.id}
        isLoading={wods.isLoading || wods.isPlaceholderData}
        error={wodsListError(wods.error)}
        onRetry={() => {
          void wods.refetch();
        }}
        emptyMessage={isFiltered ? LIST_EMPTY_FILTERED : LIST_EMPTY}
        emptyAction={
          isFiltered ? (
            <Button variant="secondary" onClick={list.clear}>
              Limpiar filtros
            </Button>
          ) : (
            <Link to="/wods/nuevo">Crear el primer WOD</Link>
          )
        }
      />
      {page && page.total > 0 ? <Pagination total={page.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
    </div>
  );
}

export default function WodListPage() {
  const canView = useCan("wods.view");
  const [search, setSearch] = useSearchParams();
  const view = search.get("vista") === "lista" ? "lista" : "semana";

  if (!canView) {
    return <MessagePage title="No tienes permiso para ver los WODs" message="Los WODs los ven el administrador y los coaches. Si lo necesitas, pídeselo a un administrador." linkLabel="Ir al inicio" linkTo="/" />;
  }

  const changeView = (next: string): void => {
    setSearch(next === "lista" ? { vista: "lista" } : {});
  };

  return (
    <div className={styles.page}>
      <PageHeader title="WODs" actions={[{ id: "new", label: "+ Nuevo WOD", href: "/wods/nuevo" }]} />
      <Segmented label="Vista de WODs" options={VIEWS} value={view} onChange={changeView} />
      {view === "lista" ? <ListView /> : <WeekView />}
    </div>
  );
}

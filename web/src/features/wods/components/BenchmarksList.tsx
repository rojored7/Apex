// S8-F1 · US-166 (front, S8-D6): lista de benchmarks de la pestaña ?tab=benchmarks.
// - FilterBar (búsqueda en memoria), DataTable paginada en el servidor: Benchmark (con su descripción), Tipo de marca,
//   Usado en WODs y Acción; «+ Nuevo benchmark» y «Editar» abren BenchmarkPanel.
// - Estados: carga, vacío (guía a crear el primero), sin coincidencias, página fuera de rango, error con Reintentar.
// DESIGN-GAP (S8-D6): el diseño no dibuja esta pestaña; usa el mismo DataTable y SidePanel que Movimientos.
import { useMemo, useState } from "react";
import { formatCount } from "../../../core/i18n/format";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { FilterBar } from "../../../shared/ui/FilterBar";
import { Pagination } from "../../../shared/ui/Pagination";
import { useBenchmarks } from "../../../shared/data/catalog";
import type { BenchmarksParams, BenchmarkView } from "../api";
import { countText, SCORE_TYPE_LABELS } from "../schemas";
import { benchmarksListError } from "../wodErrors";
import { BenchmarkPanel } from "./BenchmarkPanel";
import styles from "./Catalog.module.css";

export const BENCHMARKS_EMPTY = "Todavía no hay benchmarks. Crea el primero para usarlo al armar un WOD.";
export const BENCHMARKS_EMPTY_FILTERED = "No hay benchmarks que coincidan con la búsqueda";
export const BENCHMARKS_PAST_END = "Esta página ya no tiene benchmarks.";
export const BENCHMARKS_NOTE = "Un benchmark usado en WODs conserva su tipo de marca: así los resultados anteriores siguen siendo comparables.";

export function BenchmarksList() {
  const list = useListParams({ localQuery: true });
  const [editing, setEditing] = useState<BenchmarkView | null>(null);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const { limit, offset } = list.params;
  const { q } = list;
  const params = useMemo<BenchmarksParams>(() => ({ limit, offset, ...(q ? { q } : {}) }), [limit, offset, q]);
  const benchmarks = useBenchmarks(params);
  const page = benchmarks.data;
  const settled = benchmarks.isPlaceholderData ? undefined : page;
  const isFiltered = Boolean(q);
  const isPastEnd = settled !== undefined && settled.total > 0 && settled.items.length === 0;
  const openNew = (): void => {
    setCreating(true);
  };

  const columns: Column<BenchmarkView>[] = [
    {
      key: "name",
      header: "Benchmark",
      render: (row) => (
        <>
          <b>{row.name}</b>
          {row.description ? <span className={styles.description}>{row.description}</span> : null}
        </>
      ),
    },
    { key: "score_type", header: "Tipo de marca", render: (row) => SCORE_TYPE_LABELS[row.score_type] },
    { key: "wod_count", header: "Usado en WODs", render: (row) => <span className={styles.number}>{formatCount(row.wod_count)}</span> },
    {
      key: "actions",
      header: "Acción",
      align: "end",
      wide: true,
      render: (row) => (
        <span className={styles.actions}>
          <Button
            variant="ghost"
            aria-label={`Editar ${row.name}`}
            onClick={() => {
              setEditing(row);
            }}
          >
            Editar
          </Button>
        </span>
      ),
    },
  ];

  return (
    <div className={styles.content}>
      <div className={styles.toolbar}>
        <p className={styles.count}>{settled ? countText(settled.total, "benchmark", "benchmarks") : ""}</p>
        <Button onClick={openNew}>+ Nuevo benchmark</Button>
      </div>
      {notice ? (
        <p className={styles.notice} role="status">
          {notice}
        </p>
      ) : null}
      <FilterBar query={list.q} onQueryChange={list.setQuery} onClear={list.clear} searchLabel="Buscar benchmark" searchPlaceholder="Buscar por nombre (Fran, Grace…)" />
      <DataTable
        caption="Benchmarks"
        columns={columns}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(row) => row.id}
        isLoading={benchmarks.isLoading || benchmarks.isPlaceholderData}
        error={benchmarksListError(benchmarks.error)}
        onRetry={() => {
          void benchmarks.refetch();
        }}
        emptyMessage={isPastEnd ? BENCHMARKS_PAST_END : isFiltered ? BENCHMARKS_EMPTY_FILTERED : BENCHMARKS_EMPTY}
        emptyAction={
          isPastEnd ? (
            <Button
              variant="secondary"
              onClick={() => {
                list.setPage(1);
              }}
            >
              Ir a la primera página
            </Button>
          ) : isFiltered ? (
            <Button variant="secondary" onClick={list.clear}>
              Limpiar filtros
            </Button>
          ) : (
            <Button onClick={openNew}>Crear el primer benchmark</Button>
          )
        }
      />
      {page && page.total > 0 ? <Pagination total={page.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
      <p className={styles.note}>{BENCHMARKS_NOTE}</p>
      <BenchmarkPanel
        key="new"
        open={creating}
        benchmark={null}
        onClose={() => {
          setCreating(false);
        }}
        onSaved={(saved) => {
          setNotice(`Benchmark «${saved.name}» creado.`);
        }}
      />
      {editing ? (
        <BenchmarkPanel
          key={editing.id}
          open
          benchmark={editing}
          onClose={() => {
            setEditing(null);
          }}
          onSaved={(saved) => {
            setNotice(`Benchmark «${saved.name}» guardado.`);
          }}
        />
      ) : null}
    </div>
  );
}

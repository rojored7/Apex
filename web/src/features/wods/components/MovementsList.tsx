// S8-F1 · US-165 (front): lista del catálogo de movimientos (Movimientos.html).
// - FilterBar con búsqueda (en memoria, S2-D41), Chips «Todos · Fuerza · Gimnástico · Mono-estructural · Otro · Inactivos»
//   (uno solo a la vez; la categoría y «Inactivos» viajan al servidor como `category` y `active=false`), DataTable
//   paginada en el servidor con «Usado en WODs» y Pagination.
// - «+ Nuevo movimiento» y «Editar» abren MovementPanel; al guardar, un aviso lo dice y la lista se vuelve a pedir.
// - Estados: carga, vacío (guía a crear el primero), sin coincidencias (limpiar filtros), página fuera de rango, error.
import { useMemo, useState } from "react";
import { formatCount } from "../../../core/i18n/format";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { Chips, type ChipOption } from "../../../shared/ui/Chips";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { FilterBar } from "../../../shared/ui/FilterBar";
import { Pagination } from "../../../shared/ui/Pagination";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { useMovements } from "../../../shared/data/catalog";
import type { MovementsParams, MovementView } from "../api";
import { CATEGORY_LABELS, countText, MOVEMENT_CATEGORIES, UNIT_LABELS, type MovementCategory } from "../schemas";
import { movementsListError } from "../wodErrors";
import styles from "./Catalog.module.css";
import { MovementPanel } from "./MovementPanel";

export const MOVEMENTS_EMPTY = "Todavía no hay movimientos. Crea el primero para poder armar WODs.";
export const MOVEMENTS_EMPTY_FILTERED = "No hay movimientos que coincidan con la búsqueda";
export const MOVEMENTS_PAST_END = "Esta página ya no tiene movimientos.";
export const MOVEMENTS_NOTE = "Un movimiento usado en WODs no se borra: se desactiva y deja de aparecer al crear WODs. El histórico guarda su propia copia.";

const FILTERS = ["category", "active"] as const;
const ALL = "all";
const INACTIVE = "inactive";

const CHIP_OPTIONS: ChipOption[] = [
  { value: ALL, label: "Todos" },
  ...MOVEMENT_CATEGORIES.map((value) => ({ value, label: CATEGORY_LABELS[value] })),
  { value: INACTIVE, label: "Inactivos" },
];

function pickCategory(values: readonly string[]): MovementCategory | undefined {
  const [first] = values;
  return MOVEMENT_CATEGORIES.find((value) => value === first);
}

const COLUMNS_BASE: Column<MovementView>[] = [
  {
    key: "name",
    header: "Movimiento",
    render: (row) => <b>{row.name}</b>,
  },
  { key: "category", header: "Categoría", render: (row) => CATEGORY_LABELS[row.category] },
  { key: "unit", header: "Unidad", render: (row) => UNIT_LABELS[row.unit] },
  { key: "wod_count", header: "Usado en WODs", render: (row) => <span className={styles.number}>{formatCount(row.wod_count)}</span> },
  { key: "is_active", header: "Estado", render: (row) => <StatusTag account={row.is_active ? "active" : "inactive"} /> },
];

export function MovementsList() {
  const list = useListParams<(typeof FILTERS)[number]>({ filters: FILTERS, localQuery: true });
  const [editing, setEditing] = useState<MovementView | null>(null);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const category = pickCategory(list.filters.category);
  const onlyInactive = list.filters.active[0] === "false";
  const { limit, offset } = list.params;
  const { q } = list;

  const params = useMemo<MovementsParams>(
    () => ({ limit, offset, ...(q ? { q } : {}), ...(category ? { category } : {}), ...(onlyInactive ? { active: false } : {}) }),
    [limit, offset, q, category, onlyInactive],
  );
  const movements = useMovements(params);
  const page = movements.data;
  const settled = movements.isPlaceholderData ? undefined : page;
  const isFiltered = Boolean(q) || category !== undefined || onlyInactive;
  const isPastEnd = settled !== undefined && settled.total > 0 && settled.items.length === 0;
  const chip = category ?? (onlyInactive ? INACTIVE : ALL);
  const openNew = (): void => {
    setCreating(true);
  };

  const columns: Column<MovementView>[] = [
    ...COLUMNS_BASE,
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

  const onChip = (values: string[]): void => {
    const [value] = values;
    if (value === undefined || value === ALL) list.setFilters({ category: undefined, active: undefined });
    else if (value === INACTIVE) list.setFilters({ category: undefined, active: "false" });
    else list.setFilters({ category: value, active: undefined });
  };

  return (
    <div className={styles.content}>
      <div className={styles.toolbar}>
        <p className={styles.count}>{settled ? countText(settled.total, "movimiento", "movimientos") : ""}</p>
        <Button onClick={openNew}>+ Nuevo movimiento</Button>
      </div>
      {notice ? (
        <p className={styles.notice} role="status">
          {notice}
        </p>
      ) : null}
      <Chips label="Categoría" mode="single" options={CHIP_OPTIONS} value={[chip]} onChange={onChip} />
      <FilterBar query={list.q} onQueryChange={list.setQuery} onClear={list.clear} searchLabel="Buscar movimiento" searchPlaceholder="Buscar por nombre (sentadilla, squat…)" />
      <DataTable
        caption="Movimientos"
        columns={columns}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(row) => row.id}
        isLoading={movements.isLoading || movements.isPlaceholderData}
        error={movementsListError(movements.error)}
        onRetry={() => {
          void movements.refetch();
        }}
        emptyMessage={isPastEnd ? MOVEMENTS_PAST_END : isFiltered ? MOVEMENTS_EMPTY_FILTERED : MOVEMENTS_EMPTY}
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
            <Button onClick={openNew}>Crear el primer movimiento</Button>
          )
        }
      />
      {page && page.total > 0 ? <Pagination total={page.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
      <p className={styles.note}>{MOVEMENTS_NOTE}</p>
      <MovementPanel
        key="new"
        open={creating}
        movement={null}
        onClose={() => {
          setCreating(false);
        }}
        onSaved={(saved) => {
          setNotice(`Movimiento «${saved.name}» creado.`);
        }}
      />
      {editing ? (
        <MovementPanel
          key={editing.id}
          open
          movement={editing}
          onClose={() => {
            setEditing(null);
          }}
          onSaved={(saved) => {
            setNotice(`Movimiento «${saved.name}» guardado.`);
          }}
        />
      ) : null}
    </div>
  );
}

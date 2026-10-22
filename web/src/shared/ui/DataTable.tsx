// US-063 T4: tabla de las listas (Socios_Lista.html) y tarjetas en celular (Socios_Movil.html).
// Caja con desplazamiento propio, cabecera en mayúsculas, primera columna como enlace a la
// ficha y sin botones de editar o borrar en las filas. Estados de carga, vacío y error.
// N-01: no existe un tipo de columna "enmascarada"; las listas no muestran datos cifrados.
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { isApiError } from "../../core/api/errors";
import type { SortState } from "../hooks/useListParams";
import { MOBILE_QUERY, useMediaQuery } from "../hooks/useMediaQuery";
import { Button } from "./Button";
import { cx } from "./cx";
import styles from "./DataTable.module.css";

export interface Column<T> {
  /** Campo del api; es también el campo de orden. */
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  sortable?: boolean;
  align?: "start" | "end";
  /** En celular, la tarjeta da a este campo todo el ancho (S2-F4b: las acciones de la fila). */
  wide?: boolean;
}

export interface DataTableProps<T> {
  /** Nombre accesible de la tabla ("Socios"). */
  caption: string;
  columns: Column<T>[];
  rows: T[] | undefined;
  total?: number | undefined;
  /** Tamaño de página: define las filas del esqueleto (máximo 10). */
  limit?: number;
  rowKey: (row: T) => string;
  rowHref: (row: T) => string;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  emptyMessage?: string;
  emptyAction?: ReactNode;
  sort?: SortState | null;
  onSortChange?: (sort: SortState) => void;
}

const MAX_SKELETON_ROWS = 10;
export const LIST_GENERIC_ERROR = "No se pudo cargar la lista. Intenta de nuevo.";
export const LIST_EMPTY_MESSAGE = "No hay resultados. Prueba con otra búsqueda o limpia los filtros.";

type AriaSort = "ascending" | "descending" | "none";

function ariaSortOf(column: { key: string }, sort: SortState | null | undefined): AriaSort {
  if (sort?.field !== column.key) return "none";
  return sort.direction === "asc" ? "ascending" : "descending";
}

function SortIcon({ state }: { state: AriaSort }) {
  if (state === "ascending") return <ArrowUp size={16} aria-hidden="true" />;
  if (state === "descending") return <ArrowDown size={16} aria-hidden="true" />;
  return <ArrowUpDown size={16} aria-hidden="true" />;
}

function HeaderCell<T>({ column, sort, onSortChange }: { column: Column<T>; sort: SortState | null | undefined; onSortChange?: ((s: SortState) => void) | undefined }) {
  const className = cx(styles.th, column.align === "end" && styles.end);
  if (!column.sortable || !onSortChange) {
    return (
      <th scope="col" className={className}>
        {column.header}
      </th>
    );
  }
  const state = ariaSortOf(column, sort);
  return (
    <th scope="col" className={className} aria-sort={state}>
      <button
        type="button"
        className={styles.sortButton}
        onClick={() => {
          onSortChange({ field: column.key, direction: state === "ascending" ? "desc" : "asc" });
        }}
      >
        {column.header}
        <SortIcon state={state} />
      </button>
    </th>
  );
}

function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: (() => void) | undefined }) {
  return (
    <div className={cx(styles.box, styles.status)}>
      <p role="alert" className={styles.errorText}>
        {isApiError(error) ? error.message : LIST_GENERIC_ERROR}
      </p>
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry}>
          Reintentar
        </Button>
      ) : null}
    </div>
  );
}

function EmptyBox({ message, action }: { message: string; action: ReactNode }) {
  return (
    <div className={cx(styles.box, styles.status)}>
      <p className={styles.emptyText}>{message}</p>
      {action}
    </div>
  );
}

function Cards<T>({ caption, columns, rows, rowKey, rowHref }: Pick<DataTableProps<T>, "caption" | "columns" | "rowKey" | "rowHref"> & { rows: T[] }) {
  const [first, ...rest] = columns;
  return (
    <ul aria-label={caption} className={styles.cards}>
      {rows.map((row) => (
        <li key={rowKey(row)} className={styles.card}>
          {first ? (
            <Link to={rowHref(row)} className={cx(styles.link, styles.cardTitle)}>
              {first.render(row)}
            </Link>
          ) : null}
          <dl className={styles.cardFields}>
            {rest.map((column) => (
              <div key={column.key} className={cx(styles.cardField, column.wide && styles.cardFieldWide)}>
                <dt className={styles.cardLabel}>{column.header}</dt>
                <dd className={styles.cardValue}>{column.render(row)}</dd>
              </div>
            ))}
          </dl>
        </li>
      ))}
    </ul>
  );
}

export function DataTable<T>({
  caption,
  columns,
  rows,
  total,
  limit = MAX_SKELETON_ROWS,
  rowKey,
  rowHref,
  isLoading = false,
  error,
  onRetry,
  emptyMessage = LIST_EMPTY_MESSAGE,
  emptyAction = null,
  sort,
  onSortChange,
}: DataTableProps<T>) {
  const isMobile = useMediaQuery(MOBILE_QUERY);

  if (error) return <ErrorBox error={error} onRetry={onRetry} />;

  const items = rows ?? [];
  if (!isLoading && (total === 0 || items.length === 0)) return <EmptyBox message={emptyMessage} action={emptyAction} />;

  if (isMobile && !isLoading) {
    return <Cards caption={caption} columns={columns} rows={items} rowKey={rowKey} rowHref={rowHref} />;
  }

  const skeletonRows = Math.max(1, Math.min(limit, MAX_SKELETON_ROWS));

  return (
    <div
      role="region"
      aria-label={caption}
      aria-busy={isLoading ? true : undefined}
      tabIndex={0}
      className={cx(styles.box, styles.scroll)}
    >
      <table className={styles.table}>
        <caption className={styles.srOnly}>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <HeaderCell key={column.key} column={column} sort={sort} onSortChange={onSortChange} />
            ))}
          </tr>
        </thead>
        <tbody>
          {isLoading
            ? Array.from({ length: skeletonRows }, (_, index) => (
                <tr key={`skeleton-${String(index)}`} data-testid="skeleton-row">
                  {columns.map((column) => (
                    <td key={column.key} className={styles.td}>
                      <span className={styles.skeleton} aria-hidden="true" />
                    </td>
                  ))}
                </tr>
              ))
            : items.map((row) => (
                <tr key={rowKey(row)}>
                  {columns.map((column, index) => (
                    <td key={column.key} className={cx(styles.td, column.align === "end" && styles.end)}>
                      {index === 0 ? (
                        <Link to={rowHref(row)} className={styles.link}>
                          {column.render(row)}
                        </Link>
                      ) : (
                        column.render(row)
                      )}
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
      {isLoading ? <span className={styles.srOnly}>Cargando</span> : null}
    </div>
  );
}

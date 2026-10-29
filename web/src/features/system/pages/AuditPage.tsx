// S4A-F1 · US-102 a US-104 (front; S4A-D31, S4A-D58): /sistema/auditoria (Auditoria.html), solo admin.
// - PageHeader "Auditoría" con el total; VerifyChainButton con la última verificación y "Verificar ahora".
// - AuditFilters: Registro (búsqueda en memoria, S2-D41), Fecha (días de Bogotá), Usuario, Entidad y
//   Acción. En la URL quedan los nombres del api (`from`, `to`, `table`, `user_id`, `action`,
//   `record_id`, `subject_member_id`), `limit` y `offset`; auditFilters.toApiParams decide qué viaja.
// - DataTable (fecha y hora, usuario, acción, entidad y registro) con carga, vacío, error con
//   reintento y sin permiso; Pagination por offset (25/50/100).
// - `?seq=` abre AuditDetailPanel sin perder los filtros; al cerrarlo se quita de la URL.
// DESIGN-GAP: Auditoria.html tiene la columna "Qué cambió (anterior → nuevo)"; la lista del api no trae
// antes ni después (RN-13, S4A-D16): los cambios se ven solo en el detalle de cada entrada.
// DESIGN-GAP: "Exportar rango" llega en v0.2 (US de exportación); aquí no hay botón.
// DESIGN-GAP: la columna "Ver" con "Detalle" se une al enlace de la primera columna (DESIGN.md: la
// primera columna enlaza al detalle) para no repetir dos enlaces por fila.
// DESIGN-GAP: el api satura `total` en 100.001 (S4A-D106): el encabezado dice "Más de 100.000 entradas".
import { useMemo } from "react";
import { useSearchParams } from "react-router";
import { formatCount, formatDateTime } from "../../../core/i18n/format";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import type { DateRange } from "../../../shared/ui/FilterBar";
import { PageHeader } from "../../../shared/ui/PageHeader";
import { Pagination } from "../../../shared/ui/Pagination";
import { useAudit, useUsers } from "../api";
import { auditListError } from "../auditErrors";
import { AUDIT_FILTERS, MAX_AUDIT_OFFSET, SEQ_PARAM, actionLabel, auditUserLabel, readAuditFilters, tableLabel, toApiParams, type AuditFilter } from "../auditFilters";
import { AuditDetailPanel } from "../components/AuditDetailPanel";
import { AuditFilters } from "../components/AuditFilters";
import { VerifyChainButton } from "../components/VerifyChainButton";
import type { AuditRowView } from "../schemas";
import styles from "./AuditPage.module.css";

export const AUDIT_EMPTY = "No hay entradas de auditoría con estos filtros";
const ALL_USERS = { limit: 200, offset: 0 } as const;
/** Los primeros caracteres de un id: basta para distinguir registros en la lista. */
const SHORT_ID = 8;

const COLUMNS: Column<AuditRowView>[] = [
  { key: "at", header: "Fecha y hora", render: (row) => <span className={styles.nowrap}>{formatDateTime(row.at)}</span> },
  { key: "user", header: "Usuario", render: (row) => auditUserLabel(row) },
  { key: "action", header: "Acción", render: (row) => actionLabel(row.action) },
  {
    key: "entity",
    header: "Entidad · registro",
    render: (row) => (row.record_id ? `${tableLabel(row.table_name)} · #${row.record_id.slice(0, SHORT_ID)}` : tableLabel(row.table_name)),
  },
];

function totalText(total: number): string {
  if (total > MAX_AUDIT_OFFSET) return `Más de ${formatCount(MAX_AUDIT_OFFSET)} entradas`;
  return total === 1 ? "1 entrada" : `${formatCount(total)} entradas`;
}

function withParam(search: string, name: string, value: string | null): string {
  const next = new URLSearchParams(search);
  if (value === null) next.delete(name);
  else next.set(name, value);
  return next.toString();
}

export default function AuditPage() {
  const list = useListParams<AuditFilter>({ filters: AUDIT_FILTERS, localQuery: true });
  const [searchParams, setSearchParams] = useSearchParams();
  const search = searchParams.toString();
  const { q } = list;
  const filters = useMemo(() => readAuditFilters(search), [search]);
  const apiParams = useMemo(() => toApiParams(search, q), [search, q]);
  const limit = Number(apiParams.get("limit"));
  const offset = Number(apiParams.get("offset"));
  const audit = useAudit(apiParams);
  const users = useUsers(ALL_USERS);
  const page = audit.data;
  const { setFilter } = list;

  const closeDetail = (): void => {
    setSearchParams((previous) => new URLSearchParams(withParam(previous.toString(), SEQ_PARAM, null)), { replace: true });
  };
  const setRange = (range: DateRange): void => {
    // FilterBar avisa el rango completo; solo cambia una fecha a la vez (dos navegaciones seguidas se pisarían).
    if (range.from !== filters.from) setFilter("from", range.from || undefined);
    else if (range.to !== filters.to) setFilter("to", range.to || undefined);
  };

  return (
    <div className={styles.page}>
      <PageHeader title="Auditoría" {...(page ? { total: totalText(page.total) } : {})} />
      <VerifyChainButton />
      <AuditFilters
        filters={filters}
        query={q}
        onQueryChange={list.setQuery}
        onClear={list.clear}
        onFilterChange={(name, value) => {
          setFilter(name, value || undefined);
        }}
        onRangeChange={setRange}
        users={users.data?.items ?? []}
      />
      {filters.record_id || filters.subject_member_id ? (
        <div className={styles.scope}>
          {filters.record_id ? (
            <p className={styles.scopeLine}>
              <span>
                Filtrando por el registro <code className={styles.mono}>{filters.record_id}</code>
                {filters.table ? null : ". Elige también la entidad para aplicar este filtro."}
              </span>
              <Button
                variant="secondary"
                onClick={() => {
                  setFilter("record_id", undefined);
                }}
              >
                Quitar el filtro de registro
              </Button>
            </p>
          ) : null}
          {filters.subject_member_id ? (
            <p className={styles.scopeLine}>
              <span>Filtrando por las entradas de un socio.</span>
              <Button
                variant="secondary"
                onClick={() => {
                  setFilter("subject_member_id", undefined);
                }}
              >
                Quitar el filtro de socio
              </Button>
            </p>
          ) : null}
        </div>
      ) : null}
      <DataTable
        caption="Auditoría"
        columns={COLUMNS}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(row) => String(row.seq)}
        rowHref={(row) => `?${withParam(search, SEQ_PARAM, String(row.seq))}`}
        isLoading={audit.isLoading || audit.isPlaceholderData}
        error={auditListError(audit.error)}
        onRetry={() => {
          void audit.refetch();
        }}
        emptyMessage={AUDIT_EMPTY}
        emptyAction={
          <Button variant="secondary" onClick={list.clear}>
            Limpiar filtros
          </Button>
        }
      />
      {page && page.total > 0 ? <Pagination total={Math.min(page.total, MAX_AUDIT_OFFSET + limit)} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
      <p className={styles.note}>
        Solo lectura: nada se edita ni se borra desde aquí. La misma vista filtrada por registro es la pestaña Historial de cada ficha.
      </p>
      <AuditDetailPanel rawSeq={searchParams.get(SEQ_PARAM)} onClose={closeDetail} />
    </div>
  );
}

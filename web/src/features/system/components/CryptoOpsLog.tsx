// S6-F2 · US-144 (Llaves.html, pestaña Bitácora; S6-D16): bitácora de operaciones de cifrado, inmutable y
// paginada. Nunca aparece texto en claro: solo quién, qué operación, sobre qué clase, con qué versión de llave,
// cuántos registros y si salió bien.
// - Filtros en la URL: `from` y `to` (días de Bogotá → [from, to) en UTC), `verb`; la búsqueda por clase de dato
//   viaja al api como `q` y no queda en la URL ni en la caché (`gcTime: 0`). El rango se valida en el cliente con la regla del api (cryptoFilters.opsRangeProblem:
//   piso 2020, techo hoy, orden correcto, 366 días): un rango inválido no viaja y se explica sobre la tabla.
// - Pagination por offset (25/50/100).
// DESIGN-GAP: el diseño filtra también por usuario, llave y resultado, y la fila dice el nombre del usuario y el
// socio afectado. El api devuelve el id del usuario (sin correo) y el registro es un UUID de dato personal que no
// se muestra: el usuario se ve como «Usuario <8 hex>» y la bitácora filtra por operación y fechas (BRECHAS 14.7).
import { useMemo } from "react";
import { useSearchParams } from "react-router";
import { formatCount, formatDateTime } from "../../../core/i18n/format";
import { SYSTEM_USER_ID } from "../../../shared/lib/audit-labels";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { FilterBar, type DateRange, type FilterOption } from "../../../shared/ui/FilterBar";
import { Pagination } from "../../../shared/ui/Pagination";
import { useCryptoOps } from "../api";
import { OPS_FILTERS, opsRangeProblem, readOpsFilters, toOpsApiParams, type OpsFilter } from "../cryptoFilters";
import { VERB_LABELS } from "../cryptoLabels";
import { SYSTEM_USER_LABEL } from "../auditFilters";
import { opsListError } from "../keysErrors";
import { CRYPTO_VERBS, type CryptoOpView } from "../schemas";
import styles from "./CryptoOpsLog.module.css";

export const OPS_EMPTY = "No hay operaciones con estos filtros";
const SHORT_ID = 8;
const EMPTY = "—";

const VERB_OPTIONS: FilterOption[] = CRYPTO_VERBS.map((value) => ({ value, label: VERB_LABELS[value] }));

export function opUserLabel(userId: string): string {
  return userId === SYSTEM_USER_ID ? SYSTEM_USER_LABEL : `Usuario ${userId.slice(0, SHORT_ID)}`;
}

const COLUMNS: Column<CryptoOpView>[] = [
  { key: "at", header: "Fecha y hora", render: (op) => <span className={styles.nowrap}>{formatDateTime(op.at)}</span> },
  { key: "user_id", header: "Usuario", render: (op) => opUserLabel(op.user_id) },
  { key: "verb", header: "Operación", render: (op) => VERB_LABELS[op.verb] },
  { key: "data_class", header: "Clase de dato", render: (op) => op.data_class ?? EMPTY },
  { key: "key_version", header: "Llave", render: (op) => (op.key_version === null ? EMPTY : `v${String(op.key_version)}`) },
  { key: "count", header: "Registros", align: "end", render: (op) => formatCount(op.count) },
  { key: "result", header: "Resultado", render: (op) => (op.result === "ok" ? "Correcto" : "Con error") },
];

export function CryptoOpsLog() {
  const list = useListParams<OpsFilter>({ filters: OPS_FILTERS, localQuery: true });
  const [searchParams] = useSearchParams();
  const search = searchParams.toString();
  const { q, setFilter } = list;
  const filters = useMemo(() => readOpsFilters(search), [search]);
  const rangeProblem = useMemo(() => opsRangeProblem(filters), [filters]);
  const params = useMemo(() => toOpsApiParams(search, q), [search, q]);
  const ops = useCryptoOps(params);
  const limit = Number(params.get("limit"));
  const offset = Number(params.get("offset"));
  const page = ops.data;
  const isFiltered = q !== "" || filters.from !== "" || filters.to !== "" || filters.verb !== "";

  const setRange = (range: DateRange): void => {
    // FilterBar avisa el rango completo; solo cambia una fecha a la vez (dos navegaciones seguidas se pisarían).
    if (range.from !== filters.from) setFilter("from", range.from || undefined);
    else if (range.to !== filters.to) setFilter("to", range.to || undefined);
  };

  return (
    <div className={styles.root}>
      <FilterBar
        query={q}
        onQueryChange={list.setQuery}
        onClear={list.clear}
        searchLabel="Clase de dato"
        searchPlaceholder="member.document"
        dateRange={{ label: "Fecha", from: filters.from, to: filters.to, onChange: setRange }}
        selects={[{ name: "verb", label: "Operación", value: filters.verb, options: VERB_OPTIONS }]}
        onSelectChange={(name, value) => {
          if (name === "verb") setFilter("verb", value || undefined);
        }}
      />
      {rangeProblem ? (
        <p role="alert" className={styles.problem}>
          {rangeProblem}
        </p>
      ) : null}
      <DataTable
        caption="Bitácora de operaciones"
        columns={COLUMNS}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(op) => op.id}
        isLoading={ops.isLoading || ops.isPlaceholderData}
        error={opsListError(ops.error)}
        onRetry={() => {
          void ops.refetch();
        }}
        emptyMessage={OPS_EMPTY}
        emptyAction={
          isFiltered ? (
            <Button variant="secondary" onClick={list.clear}>
              Limpiar filtros
            </Button>
          ) : undefined
        }
      />
      {page && page.total > 0 ? <Pagination total={page.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
      <p className={styles.help}>La bitácora es de solo lectura: ninguna fila se edita ni se borra, y nunca contiene texto en claro de los datos.</p>
    </div>
  );
}

// S8-F5 · US-173 (front): pestaña Resultados de la ficha (/socios/:id/resultados), admin y coach (`results.record`). Ruta hija de
// /socios/:id (S3-D65, E3): la ficha la pinta en su <Outlet /> y le pasa el socio por el contexto (useMemberTab, shared/data); esta
// feature no importa features/members y la ficha la carga de forma diferida (lazy en la tabla de rutas).
// - Lista GET /members/{id}/results paginada en el servidor (25, 50 o 100; `offset` en la URL) con «Solo benchmarks» (`?benchmark=`).
// - Columnas: WOD (enlace a su detalle), fecha, nivel, marca (formatScore: gramos a kg, DNF) y dónde se registró («En tablet» o
//   «En recepción»); un resultado pendiente lleva «Por validar» y uno anulado, «Anulado».
// - Estados: carga, vacío («Todavía no tiene resultados», guía a los WODs), error con Reintentar (404, 403, 429, 5xx) y página fuera de rango.
// DESIGN-GAP: Socio_Ficha.html manda esta pestaña al detalle de un WOD (WOD_Detalle.html) y su tarjeta «Último WOD» no existe (EP-24):
// aquí es una lista propia. No hay «vs. su anterior», «PR» ni el gráfico de progreso (EP-24).
import { Link, useParams } from "react-router";
import { formatDate } from "../../../core/i18n/format";
import { formatScore } from "../../../shared/data/score";
import { useMemberTab } from "../../../shared/data/members";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { Pagination } from "../../../shared/ui/Pagination";
import { useMemberResults } from "../api";
import { memberResultsError } from "../resultErrors";
import { LEVEL_FULL, type MemberResultRowView } from "../schemas";
import styles from "./MemberResultsTab.module.css";

export const MEMBER_RESULTS_EMPTY = "Todavía no tiene resultados. Aparecen cuando el coach los registra en la tablet o en el panel después de una clase.";
const PAST_END = "Esta página ya no tiene resultados.";
const SOURCE_LABELS = { kiosk: "En tablet", desk: "En recepción" } as const;

function statusNote(row: MemberResultRowView) {
  if (row.status === "pending") return <span className={styles.pending}>Por validar</span>;
  if (row.status === "voided") return <span className={styles.pending}>Anulado</span>;
  return null;
}

const COLUMNS: Column<MemberResultRowView>[] = [
  {
    key: "wod",
    header: "WOD",
    render: (row) => (
      <Link className={styles.link} to={`/wods/${encodeURIComponent(row.wod_id)}`}>
        {row.wod_title}
      </Link>
    ),
  },
  { key: "wod_date", header: "Fecha", render: (row) => <span className={styles.nowrap}>{formatDate(row.wod_date)}</span> },
  { key: "level", header: "Nivel", render: (row) => LEVEL_FULL[row.level] },
  {
    key: "mark",
    header: "Marca",
    render: (row) => (
      <span className={styles.mark}>
        {formatScore(row.score_type, row)} {statusNote(row)}
      </span>
    ),
  },
  { key: "source", header: "Dónde", render: (row) => SOURCE_LABELS[row.source] },
];

export default function MemberResultsTab() {
  const member = useMemberTab();
  const { id: routeId = "" } = useParams();
  const memberId = member?.id ?? routeId;
  const list = useListParams<"benchmark">({ filters: ["benchmark"] });
  const { limit, offset } = list.params;
  const onlyBenchmarks = list.filters.benchmark[0] === "true";
  const results = useMemberResults(memberId, { limit, offset, ...(onlyBenchmarks ? { benchmark: true } : {}) });
  const page = results.isPlaceholderData ? undefined : results.data;
  const isPastEnd = page !== undefined && page.total > 0 && page.items.length === 0;

  return (
    <div className={styles.tab}>
      <h2 className={styles.title}>Resultados</h2>
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
        caption="Resultados del socio"
        columns={COLUMNS}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(row) => row.id}
        isLoading={results.isLoading || results.isPlaceholderData}
        error={memberResultsError(results.error)}
        onRetry={() => {
          void results.refetch();
        }}
        emptyMessage={isPastEnd ? PAST_END : MEMBER_RESULTS_EMPTY}
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
          ) : (
            <Link className={styles.link} to="/wods">
              Ver los WODs
            </Link>
          )
        }
      />
      {page && page.total > 0 ? <Pagination total={page.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
    </div>
  );
}

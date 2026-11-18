// S9-F2 · US-180, US-181 (Atleta_Perfil.html, subpestaña «RMs por movimiento»): el RM vigente de cada movimiento, paginado en el servidor.
// - GET /athletes/{id}/rms?limit&offset (25, 50 o 100; `offset` en la URL). Una fila por movimiento: Movimiento, 1RM (kg), Último cambio y Origen.
// - Origen con palabras, nunca solo color: «Manual» o «Automático del WOD». RmOut no trae `result_source`: «Automático (tablet)» solo se
//   puede decir en Récords (RecordOut.result_source, L-4).
// - Vacío con guía; error con Reintentar (403, 404, 429, 5xx). Sin acciones: invalidar vive en Récords.
// DESIGN-GAP: 3RM, 5RM, «máx. reps» y la unidad preferida del diseño (S9-D25; N-45 fija RM = 1RM en kg).
import { formatDate } from "../../../core/i18n/format";
import { formatLoadKg } from "../../../shared/data/score";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { originText } from "../recordFormat";
import { Pagination } from "../../../shared/ui/Pagination";
import { useRms } from "../api";
import { rmsListError } from "../recordErrors";
import type { RmView } from "../schemas";
import styles from "./RecordsTab.module.css";

export interface RmsTabProps {
  memberId: string;
}

export const RMS_EMPTY = "Todavía no hay RMs registrados. Usa «Registrar récord» para guardar el primero.";
const PAST_END = "Esta página ya no tiene RMs.";
const NO_NAME = "Movimiento sin nombre";

const COLUMNS: Column<RmView>[] = [
  { key: "movement_name", header: "Movimiento", render: (row) => row.movement_name ?? <span className={styles.muted}>{NO_NAME}</span> },
  { key: "value_g", header: "1RM", render: (row) => <span className={styles.nowrap}>{formatLoadKg(row.value_g)}</span> },
  { key: "achieved_on", header: "Último cambio", render: (row) => <span className={styles.nowrap}>{formatDate(row.achieved_on)}</span> },
  { key: "source", header: "Origen", render: (row) => originText(row) },
];

export function RmsTab({ memberId }: RmsTabProps) {
  const list = useListParams();
  const { limit, offset } = list.params;
  const rms = useRms(memberId, { limit, offset });
  const page = rms.isPlaceholderData ? undefined : rms.data;
  const isPastEnd = page !== undefined && page.total > 0 && page.items.length === 0;

  return (
    <div className={styles.tab}>
      <h2 className={styles.title}>RMs por movimiento</h2>
      <DataTable
        caption="RMs por movimiento del socio"
        columns={COLUMNS}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(row) => row.record_id}
        isLoading={rms.isLoading || rms.isPlaceholderData}
        error={rmsListError(rms.error)}
        onRetry={() => {
          void rms.refetch();
        }}
        emptyMessage={isPastEnd ? PAST_END : RMS_EMPTY}
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
          ) : undefined
        }
      />
      {page && page.total > 0 ? <Pagination total={page.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
    </div>
  );
}

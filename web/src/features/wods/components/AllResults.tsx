// S8-F3 · US-172 (front): «Todos los resultados» del WOD (GET /wods/{id}/results), con quién y cuándo lo registró. Los resultados
// son inmutables: una corrección es un resultado nuevo y el anterior se ve con «Incluir corregidos». Un resultado en el socio o la
// clase equivocados lo anula un administrador con motivo (S8-D46 b); no hay «mover a otra sesión».
// DESIGN-GAP: «Por validar» y «Validar» llegan con EP-25 (S8-D29).
import { useState } from "react";
import { Can } from "../../../core/auth/Can";
import { formatDateTime } from "../../../core/i18n/format";
import { resultsLoadError, VOID_MESSAGES, voidMessage } from "../../../shared/data/resultErrors";
import { LEVEL_LABELS, useVoidResult, useWodResults, type WodResultRowView } from "../../../shared/data/results";
import { formatScore } from "../../../shared/data/score";
import { toFormError } from "../../../shared/lib/apiMessages";
import { Button } from "../../../shared/ui/Button";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { Pagination } from "../../../shared/ui/Pagination";
import { WOD_SCORE_LABELS, type WodScoreType } from "../wodSchemas";
import styles from "./Leaderboard.module.css";

export const RESULTS_EMPTY = "Todavía no hay resultados. Los coaches los registran desde la tablet de cada clase.";
export const VOID_REASON_MAX = 200;

function stateOf(row: WodResultRowView): string {
  if (row.status === "voided") return "Anulado";
  if (row.status === "pending") return "Por validar";
  return row.is_current ? "Vigente" : "Corregido";
}

export function AllResults({ wodId, scoreType }: { wodId: string; scoreType: WodScoreType }) {
  const [includeSuperseded, setIncludeSuperseded] = useState(false);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(50);
  const [toVoid, setToVoid] = useState<WodResultRowView | null>(null);
  const results = useWodResults(wodId, { limit, offset, includeSuperseded });
  const voidResult = useVoidResult();
  const page = results.data;

  const columns: Column<WodResultRowView>[] = [
    { key: "athlete", header: "Atleta", render: (row) => `${row.first_name} ${row.last_name}` },
    { key: "score", header: WOD_SCORE_LABELS[scoreType], render: (row) => <b>{formatScore(scoreType, row)}</b> },
    { key: "level", header: "Nivel", render: (row) => LEVEL_LABELS[row.level] },
    {
      key: "recorded",
      header: "Registró",
      render: (row) => `${row.recorded_by_name ?? "—"} · ${formatDateTime(row.created_at)}${row.source === "kiosk" ? " · en tablet" : ""}`,
    },
    { key: "state", header: "Estado", render: stateOf },
    {
      key: "actions",
      header: "Acción",
      align: "end",
      wide: true,
      render: (row) =>
        row.is_current && row.status === "validated" ? (
          <Can action="results.void">
            <Button
              variant="ghost"
              onClick={() => {
                setToVoid(row);
              }}
            >
              Anular
            </Button>
          </Can>
        ) : null,
    },
  ];

  return (
    <div className={styles.board}>
      <label className={styles.check}>
        <input
          type="checkbox"
          checked={includeSuperseded}
          onChange={(event) => {
            setIncludeSuperseded(event.target.checked);
            setOffset(0);
          }}
        />
        Incluir corregidos y anulados
      </label>
      <DataTable
        caption="Todos los resultados"
        columns={columns}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(row) => row.id}
        isLoading={results.isLoading || results.isPlaceholderData}
        error={resultsLoadError(results.error)}
        onRetry={() => {
          void results.refetch();
        }}
        emptyMessage={RESULTS_EMPTY}
      />
      {page && page.total > 0 ? (
        <Pagination
          total={page.total}
          limit={limit}
          offset={offset}
          onPageChange={(next) => {
            setOffset((next - 1) * limit);
          }}
          onLimitChange={(next) => {
            setLimit(next);
            setOffset(0);
          }}
        />
      ) : null}
      <ConfirmModal
        open={toVoid !== null}
        title="¿Anular este resultado?"
        consequence={toVoid ? `Se anula la marca de ${toVoid.first_name} ${toVoid.last_name}: sale del leaderboard y queda en el historial con tu motivo. Después se puede registrar otra.` : ""}
        confirmLabel="Anular resultado"
        tone="danger"
        reasonRequired
        minReasonLength={1}
        maxReasonLength={VOID_REASON_MAX}
        reasonHint="Di qué pasó (por ejemplo, socio equivocado). No escribas teléfonos ni documentos."
        onConfirm={async (reason) => {
          if (toVoid === null) return;
          try {
            await voidResult.mutateAsync({ id: toVoid.id, reason: reason ?? "" });
          } catch (error) {
            throw toFormError(error, (e) => voidMessage(e), VOID_MESSAGES.failed);
          }
        }}
        onClose={() => {
          setToVoid(null);
        }}
      />
    </div>
  );
}

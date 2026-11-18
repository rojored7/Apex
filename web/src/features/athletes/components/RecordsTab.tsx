// S9-F2 · US-180, US-181, US-182 (Atleta_Perfil.html, subpestaña «Récords»): la lista completa de récords, paginada en el servidor.
// - GET /athletes/{id}/records?limit&offset[&kind][&include_invalidated] (`kind` e `invalidated=1` en la URL).
// - Chips «RMs» y «Benchmarks» (grupo «Tipo de récord», uno u ninguno) y «Ver invalidados» (grupo «Estado del récord»).
// - Estado y origen con palabras, nunca solo color: «Vigente», «Histórico», «Invalidado»; «Manual · quien», «Automático del WOD» o «Automático (tablet)».
// - Un derivado enlaza a su WOD y explica que se corrige desde el resultado; no tiene «Invalidar». «Invalidar» solo en un manual vivo
//   (athletes.write, socio vivo), con ConfirmModal sin motivo y POST .../invalidate sin cuerpo.
// DESIGN-GAP: «editar» un récord del diseño (se invalida y se registra otro, S9-D13).
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { formatDate } from "../../../core/i18n/format";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { Chips } from "../../../shared/ui/Chips";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { cx } from "../../../shared/ui/cx";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { Pagination } from "../../../shared/ui/Pagination";
import { useInvalidateRecord, useRecords } from "../api";
import { invalidateRecordError, recordsListError } from "../recordErrors";
import { recordTitle, recordValue } from "../recordFormat";
import type { RecordView } from "../schemas";
import styles from "./RecordsTab.module.css";

export interface RecordsTabProps {
  memberId: string;
  /** El socio está dado de baja: sin «Invalidar» (S9-D14). */
  memberDeleted: boolean;
}

export const RECORDS_EMPTY = "Todavía no hay récords registrados. Usa «Registrar récord» para guardar el primero.";
const FILTERED_EMPTY = "No hay récords con estos filtros. Quita un filtro para ver más.";
const PAST_END = "Esta página ya no tiene récords.";
const DERIVED_NOTE = "Se corrige corrigiendo el resultado que lo originó.";
const REASON_TEXT = { superseded: "Resultado corregido", voided: "Resultado anulado", manual_error: "Error de digitación" } as const;
const KIND_OPTIONS = [
  { value: "rm", label: "RMs" },
  { value: "benchmark", label: "Benchmarks" },
];
const INVALIDATED_OPTIONS = [{ value: "1", label: "Ver invalidados" }];

type Kind = "rm" | "benchmark";
const asKind = (value: string | undefined): Kind | undefined => (value === "rm" || value === "benchmark" ? value : undefined);

function originText(row: RecordView): string {
  if (row.source === "manual") return row.recorded_by_name ? `Manual · ${row.recorded_by_name}` : "Manual";
  return row.result_source === "kiosk" ? "Automático (tablet)" : "Automático del WOD";
}

function StateCell({ row }: { row: RecordView }) {
  if (row.invalidated_at !== null) {
    return (
      <span className={styles.stack}>
        <span className={styles.state}>Invalidado</span>
        {row.invalidated_reason ? <span className={styles.note}>{REASON_TEXT[row.invalidated_reason]}</span> : null}
      </span>
    );
  }
  return <span className={styles.state}>{row.is_current ? "Vigente" : "Histórico"}</span>;
}

interface ActionsProps {
  row: RecordView;
  canInvalidate: boolean;
  onInvalidate: (row: RecordView) => void;
}

function ActionsCell({ row, canInvalidate, onInvalidate }: ActionsProps) {
  if (row.source === "derived") {
    return (
      <span className={styles.stack}>
        {row.wod_id ? (
          <Link className={styles.link} to={`/wods/${encodeURIComponent(row.wod_id)}`} aria-label={`Ver el WOD de ${recordTitle(row)}`}>
            Ver el WOD
          </Link>
        ) : null}
        <span className={styles.note}>{DERIVED_NOTE}</span>
      </span>
    );
  }
  if (row.invalidated_at !== null || !canInvalidate) return null;
  return (
    <Button
      variant="ghost"
      aria-label={`Invalidar ${recordTitle(row)} del ${formatDate(row.achieved_on)}`}
      onClick={() => {
        onInvalidate(row);
      }}
    >
      Invalidar
    </Button>
  );
}

function buildColumns(canInvalidate: boolean, onInvalidate: (row: RecordView) => void): Column<RecordView>[] {
  return [
    { key: "achieved_on", header: "Fecha", render: (row) => <span className={styles.nowrap}>{formatDate(row.achieved_on)}</span> },
    { key: "title", header: "Récord", render: (row) => recordTitle(row) },
    { key: "value", header: "Valor", render: (row) => <span className={cx(styles.nowrap, row.invalidated_at !== null && styles.invalidated)}>{recordValue(row)}</span> },
    { key: "source", header: "Origen", render: (row) => originText(row) },
    { key: "state", header: "Estado", render: (row) => <StateCell row={row} /> },
    { key: "actions", header: "Acciones", wide: true, render: (row) => <ActionsCell row={row} canInvalidate={canInvalidate} onInvalidate={onInvalidate} /> },
  ];
}

export function RecordsTab({ memberId, memberDeleted }: RecordsTabProps) {
  const canWrite = useCan("athletes.write");
  const list = useListParams<"kind" | "invalidated">({ filters: ["kind", "invalidated"] });
  const { limit, offset } = list.params;
  const kind = asKind(list.filters.kind[0]);
  const withInvalidated = list.filters.invalidated[0] === "1";
  const records = useRecords(memberId, { limit, offset, ...(kind ? { kind } : {}), ...(withInvalidated ? { include_invalidated: true } : {}) });
  const invalidate = useInvalidateRecord(memberId);
  const [invalidating, setInvalidating] = useState<RecordView | null>(null);
  const refocus = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const page = records.isPlaceholderData ? undefined : records.data;
  const isPastEnd = page !== undefined && page.total > 0 && page.items.length === 0;
  const hasFilters = kind !== undefined || withInvalidated;
  const canInvalidate = canWrite && !memberDeleted;
  const changeKind = (next: string[]): void => {
    list.setFilter("kind", next[0]);
  };
  const changeInvalidated = (next: string[]): void => {
    list.setFilter("invalidated", next[0]);
  };
  const columns = useMemo(() => buildColumns(canInvalidate, setInvalidating), [canInvalidate]);

  // Al invalidar con éxito el botón de la fila desaparece al releer: el foco pasa al encabezado de la sección (no se pierde en <body>).
  useEffect(() => {
    if (!refocus.current || invalidating !== null) return;
    refocus.current = false;
    heading.current?.focus();
  }, [invalidating]);

  const confirmInvalidate = async (): Promise<void> => {
    if (invalidating === null) return;
    try {
      await invalidate.mutateAsync(invalidating.id);
      refocus.current = true;
    } catch (error) {
      throw invalidateRecordError(error);
    }
  };

  return (
    <div className={styles.tab}>
      <h2 ref={heading} tabIndex={-1} className={styles.title}>
        Récords
      </h2>
      <div className={styles.filters}>
        <Chips label="Tipo de récord" mode="single" options={KIND_OPTIONS} value={kind ? [kind] : []} onChange={changeKind} />
        <Chips label="Estado del récord" mode="multiple" options={INVALIDATED_OPTIONS} value={withInvalidated ? ["1"] : []} onChange={changeInvalidated} />
      </div>
      <DataTable
        caption="Récords del socio"
        columns={columns}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(row) => row.id}
        isLoading={records.isLoading || records.isPlaceholderData}
        error={recordsListError(records.error)}
        onRetry={() => {
          void records.refetch();
        }}
        emptyMessage={isPastEnd ? PAST_END : hasFilters ? FILTERED_EMPTY : RECORDS_EMPTY}
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
      <ConfirmModal
        open={invalidating !== null}
        title="¿Invalidar este récord?"
        consequence="El récord deja de contarse y se conserva en la auditoría. El mejor récord que quede pasa a ser el vigente. No se puede deshacer."
        confirmLabel="Invalidar récord"
        cancelLabel="Cancelar"
        onConfirm={confirmInvalidate}
        onClose={() => {
          setInvalidating(null);
        }}
      />
    </div>
  );
}

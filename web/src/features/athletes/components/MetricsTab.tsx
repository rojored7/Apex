// S9-F1 · US-178, US-179 (Atleta_Perfil.html, subpestaña «Medidas corporales»): la lista completa y paginada en el servidor.
// - GET /athletes/{id}/metrics?limit&offset (25, 50 o 100; `offset` en la URL). Solo `has_*`: ningún valor llega en la lista; cada campo
//   con valor es «•••» con su «Mostrar» (MetricField, reveal de 60 s).
// - «Anular» (athletes.write, sin motivo) abre un ConfirmModal y llama a POST .../void sin cuerpo; con el socio dado de baja no hay
//   «Anular» y el reveal del coach da un 403 explicado (S9-D34).
// - Estados: carga, vacío con guía, error con Reintentar (403, 404, 429, 5xx) y página fuera de rango.
// DESIGN-GAP: la gráfica de peso y la columna «Cintura» del diseño no están en el contrato; los valores no se ven en claro en la tabla (S9-D16).
import { useEffect, useMemo, useRef, useState } from "react";
import { formatDate } from "../../../core/i18n/format";
import { useCan } from "../../../core/auth/useCan";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { cx } from "../../../shared/ui/cx";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { Pagination } from "../../../shared/ui/Pagination";
import { useMetrics, useVoidMetric } from "../api";
import { metricsListError, voidMetricError } from "../athleteErrors";
import type { MetricView } from "../schemas";
import { MetricField } from "./MetricField";
import styles from "./MetricsTab.module.css";

export interface MetricsTabProps {
  memberId: string;
  /** El socio está dado de baja: sin «Anular»; el `reveal` del coach da 403 (S9-D34). */
  memberDeleted: boolean;
  /** La ficha del socio no está cargada: se trata como solo lectura, pero sin decir que está dado de baja (V7, M11). */
  memberUnknown?: boolean;
  /** Se llama tras anular con éxito (la pestaña Atleta lo avisa en su región de avisos). */
  onVoided?: () => void;
}

export const METRICS_EMPTY = "Todavía no hay medidas registradas. Usa «Registrar medidas» para guardar la primera.";
const PAST_END = "Esta página ya no tiene medidas.";
const EMPTY_CELL = "—";

interface ColumnsOptions {
  memberId: string;
  memberDeleted: boolean;
  memberUnknown: boolean;
  canVoid: boolean;
  onVoid: (metric: MetricView) => void;
}

function buildColumns({ memberId, memberDeleted, memberUnknown, canVoid, onVoid }: ColumnsOptions): Column<MetricView>[] {
  const field = (row: MetricView, name: "weight_g" | "height_cm" | "body_fat_pct" | "notes", has: boolean) => (
    <MetricField memberId={memberId} metricId={row.id} field={name} has={has} memberDeleted={memberDeleted} memberUnknown={memberUnknown} measuredOn={row.measured_on} />
  );
  const columns: Column<MetricView>[] = [
    {
      key: "measured_on",
      header: "Fecha",
      render: (row) => <span className={cx(styles.cell, styles.nowrap)}>{formatDate(row.measured_on)}</span>,
    },
    { key: "weight", header: "Peso", render: (row) => field(row, "weight_g", row.has_weight) },
    { key: "height", header: "Altura", render: (row) => field(row, "height_cm", row.has_height) },
    { key: "body_fat", header: "% grasa", render: (row) => field(row, "body_fat_pct", row.has_body_fat) },
    { key: "notes", header: "Notas", render: (row) => <span className={styles.notes}>{field(row, "notes", row.has_notes)}</span> },
    { key: "recorded_by", header: "Registró", render: (row) => <span className={styles.cell}>{row.recorded_by_name ?? <span className={styles.muted}>{EMPTY_CELL}</span>}</span> },
  ];
  if (!canVoid) return columns;
  return [
    ...columns,
    {
      key: "actions",
      header: "Acciones",
      wide: true,
      render: (row) => (
        <Button
          variant="ghost"
          aria-label={`Anular medición del ${formatDate(row.measured_on)}`}
          onClick={() => {
            onVoid(row);
          }}
        >
          Anular
        </Button>
      ),
    },
  ];
}

export function MetricsTab({ memberId, memberDeleted, memberUnknown = false, onVoided }: MetricsTabProps) {
  const canWrite = useCan("athletes.write");
  const list = useListParams();
  const { limit, offset } = list.params;
  const metrics = useMetrics(memberId, { limit, offset });
  const voidMetric = useVoidMetric(memberId);
  const [voiding, setVoiding] = useState<MetricView | null>(null);
  const refocus = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const page = metrics.isPlaceholderData ? undefined : metrics.data;
  const isPastEnd = page !== undefined && page.total > 0 && page.items.length === 0;
  const canVoid = canWrite && !memberDeleted;
  const columns = useMemo(
    () => buildColumns({ memberId, memberDeleted, memberUnknown, canVoid, onVoid: setVoiding }),
    [memberId, memberDeleted, memberUnknown, canVoid],
  );

  // Al anular con éxito la fila (y su botón) desaparece al releer: el foco pasa al encabezado de la sección (no se pierde en <body>).
  useEffect(() => {
    if (!refocus.current || voiding !== null) return;
    refocus.current = false;
    heading.current?.focus();
  }, [voiding]);

  const confirmVoid = async (): Promise<void> => {
    if (voiding === null) return;
    try {
      await voidMetric.mutateAsync(voiding.id);
      refocus.current = true;
      onVoided?.();
    } catch (error) {
      throw voidMetricError(error);
    }
  };

  return (
    <div className={styles.tab}>
      <h2 ref={heading} tabIndex={-1} className={styles.title}>
        Medidas corporales
      </h2>
      <DataTable
        caption="Medidas corporales del socio"
        columns={columns}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(row) => row.id}
        isLoading={metrics.isLoading || metrics.isPlaceholderData}
        error={metricsListError(metrics.error)}
        onRetry={() => {
          void metrics.refetch();
        }}
        emptyMessage={isPastEnd ? PAST_END : METRICS_EMPTY}
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
        open={voiding !== null}
        title="¿Anular esta medición?"
        consequence="La medición deja de contarse y se conserva en la auditoría. No se puede deshacer."
        confirmLabel="Anular medición"
        cancelLabel="Cancelar"
        onConfirm={confirmVoid}
        onClose={() => {
          setVoiding(null);
        }}
      />
    </div>
  );
}

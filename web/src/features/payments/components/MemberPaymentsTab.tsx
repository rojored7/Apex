// S3-F7 · US-101 (front): pestaña Pagos de la ficha (/socios/:id/pagos), admin y coach
// (`payments.view`). Vive en features/payments (S3-D65): es una ruta hija de /socios/:id que la ficha
// pinta en su <Outlet /> y le pasa el socio por el contexto (useMemberTab, shared/data).
// - GET /members/{id}/payments (B11, useMemberPayments), paginada en el servidor (25, 50 o 100;
//   `offset` en la URL) en el orden del api (`paid_at` descendente): fecha y hora de Bogotá,
//   membresía, valor (tachado si está anulado), medio (etiqueta de Configuración), referencia,
//   registró (correo parcial, S3-D57), StatusTag "Válido" o "Anulado" con su motivo y la marca
//   "Retroactivo" (S3-D51).
// - "Ocultar anulados" deja `voided=false` en la URL y en la petición (vuelve a la primera página).
// - "Registrar pago" abre el panel de pagos con el socio (?pago=nuevo&socio=, S3-D65); no aparece
//   para un dado de baja. "Anular" solo con `payments.void` (admin), en los válidos, y abre
//   VoidPaymentModal; el api vuelve a verificar. Sin la ficha (la pestaña sola) no hay botones.
// - Estados: carga, vacío ("Este socio no tiene pagos." o "... pagos válidos." con el filtro), error
//   con Reintentar (404, 403 y el resto en palabras de la pantalla).
// DESIGN-GAP:
// - Socio_Ficha.html no dibuja la pestaña (enlaza a Pagos.html): la tabla de Pagos.html sin "Socio"
//   (es el de la ficha) y con "Anular" en la fila en lugar de "Ver"; "Ocultar anulados" no está
//   dibujado. Fechas con año y hora en 12 h (DESIGN.md regla 7).
import { useState } from "react";
import { Link, useLocation, useParams } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { EMPTY_VALUE, formatCop, formatDateTime } from "../../../core/i18n/format";
import { useMemberTab } from "../../../shared/data/members";
import { usePaymentMethodOptions } from "../../../shared/data/paymentMethods";
import { useMemberPayments, type MemberPaymentsParams, type PaymentRowView } from "../../../shared/data/payments";
import { useListParams } from "../../../shared/hooks/useListParams";
import { paymentPanelHref } from "../../../shared/lib/paymentPanel";
import buttonStyles from "../../../shared/ui/Button.module.css";
import { cx } from "../../../shared/ui/cx";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { Pagination } from "../../../shared/ui/Pagination";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { membershipText } from "../lib/paymentText";
import { memberTabError } from "../paymentErrors";
import styles from "./MemberPaymentsTab.module.css";
import { VoidPaymentModal, type VoidTarget } from "./VoidPaymentModal";

export const MEMBER_PAYMENTS_EMPTY = "Este socio no tiene pagos.";
export const MEMBER_PAYMENTS_EMPTY_VALID = "Este socio no tiene pagos válidos.";
export const MEMBER_PAYMENTS_LOADING = "Cargando los pagos…";
export const BACKDATED_MARK = "Retroactivo";
const PAST_END = "Esta página ya no tiene pagos.";
const FILTERS = ["voided"] as const;

/** "Anular el pago de $ 60.000 en Nequi del 20 oct 2026, 2:10 p. m." (revisión S3-F7, L8: con el medio, dos pagos iguales del mismo minuto rara vez se llaman igual). */
export const voidLabel = (row: Pick<PaymentRowView, "amount_cop" | "paid_at">, method: string): string => `Anular el pago de ${formatCop(row.amount_cop)} en ${method} del ${formatDateTime(row.paid_at)}`;

interface ColumnOptions {
  methodLabel: (code: PaymentRowView["method"]) => string;
  /** null: la fila no ofrece "Anular". */
  onVoid: ((row: PaymentRowView) => void) | null;
}

function columnsFor({ methodLabel, onVoid }: ColumnOptions): Column<PaymentRowView>[] {
  return [
    { key: "paid_at", header: "Fecha", render: (row) => <span className={styles.nowrap}>{formatDateTime(row.paid_at)}</span> },
    { key: "membership", header: "Membresía", render: (row) => <span className={styles.nowrap}>{membershipText(row)}</span> },
    {
      key: "amount_cop",
      header: "Valor",
      render: (row) => (row.voided ? <s className={styles.amount}>{formatCop(row.amount_cop)}</s> : <span className={styles.amount}>{formatCop(row.amount_cop)}</span>),
    },
    { key: "method", header: "Medio", render: (row) => methodLabel(row.method) },
    { key: "reference", header: "Referencia", render: (row) => row.reference ?? EMPTY_VALUE },
    { key: "registered_by", header: "Registró", render: (row) => row.registered_by_name ?? EMPTY_VALUE },
    {
      key: "status",
      header: "Estado",
      render: (row) => (
        <span className={styles.status}>
          <StatusTag payment={row.voided ? "voided" : "valid"} />
          {row.backdated ? <span className={styles.mark}>{BACKDATED_MARK}</span> : null}
          {row.voided && row.void_reason ? <span className={styles.reason}>{`Motivo: ${row.void_reason}`}</span> : null}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Acción",
      align: "end",
      render: (row) =>
        onVoid && !row.voided ? (
          <button
            type="button"
            className={styles.void}
            aria-label={voidLabel(row, methodLabel(row.method))}
            onClick={() => {
              onVoid(row);
            }}
          >
            Anular
          </button>
        ) : (
          EMPTY_VALUE
        ),
    },
  ];
}

export default function MemberPaymentsTab() {
  const { id = "" } = useParams();
  const member = useMemberTab();
  const location = useLocation();
  const list = useListParams({ filters: FILTERS });
  const hideVoided = list.filters.voided[0] === "false";
  const params: MemberPaymentsParams = { limit: list.params.limit, offset: list.params.offset, ...(hideVoided ? { voided: false } : {}) };
  const payments = useMemberPayments(id === "" ? null : id, params);
  const { methods } = usePaymentMethodOptions();
  const canRegister = useCan("payments.register");
  const canVoid = useCan("payments.void");
  const [voiding, setVoiding] = useState<VoidTarget | null>(null);

  // Sin la ficha no se sabe si el socio está dado de baja: sin botones. El dado de baja no recibe
  // pagos nuevos; un pago suyo mal registrado sí se puede anular.
  const showRegister = canRegister && member !== null && member.deleted_at === null;
  const methodLabel = (code: PaymentRowView["method"]): string => methods.find((m) => m.code === code)?.label ?? code;
  const columns = columnsFor({
    methodLabel,
    onVoid:
      canVoid && member !== null
        ? (row) => {
            setVoiding({ id: row.id, membership_id: row.membership_id, amount_cop: row.amount_cop, method: row.method });
          }
        : null,
  });

  if (payments.data === undefined && !payments.isError) {
    return (
      <p className={styles.loading} role="status">
        {MEMBER_PAYMENTS_LOADING}
      </p>
    );
  }
  const data = payments.data;
  const isPastEnd = data !== undefined && data.total > 0 && data.items.length === 0;

  return (
    <div className={styles.tab}>
      <div className={styles.toolbar}>
        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={hideVoided}
            onChange={(event) => {
              list.setFilter("voided", event.target.checked ? "false" : undefined);
            }}
          />
          Ocultar anulados
        </label>
        {showRegister ? (
          <Link className={cx(buttonStyles.button, buttonStyles.primary, buttonStyles.md)} to={paymentPanelHref(location, { memberId: id })}>
            Registrar pago
          </Link>
        ) : null}
      </div>
      <DataTable
        caption="Pagos del socio"
        columns={columns}
        rows={data?.items}
        total={data?.total}
        limit={params.limit}
        rowKey={(row) => row.id}
        isLoading={payments.isPlaceholderData}
        error={memberTabError(payments.error)}
        onRetry={() => {
          void payments.refetch();
        }}
        emptyMessage={isPastEnd ? PAST_END : hideVoided ? MEMBER_PAYMENTS_EMPTY_VALID : MEMBER_PAYMENTS_EMPTY}
      />
      {data && data.total > 0 ? <Pagination total={data.total} limit={params.limit} offset={params.offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
      <VoidPaymentModal
        payment={voiding}
        onClose={() => {
          setVoiding(null);
        }}
      />
    </div>
  );
}

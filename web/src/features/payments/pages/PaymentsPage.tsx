// S3-F6 · US-098, US-099 y US-100 (front): /pagos (Pagos.html), admin y coach (`payments.view`).
// - PageHeader "Pagos" con el total y "Registrar pago" (`payments.register`): abre el panel de pagos
//   sobre la lista con `?pago=nuevo` (S3-D65), conservando los filtros.
// - Resumen del mes arriba (MonthSummary, `?mes=AAAA-MM`).
// - FilterBar: búsqueda por socio o referencia en memoria (S2-D41), fecha del pago (días de Bogotá;
//   hacia el api en UTC con `to` exclusivo), medio, registró, estado (Todos, Válidos, Anulados; D37) y
//   retroactivos. Filtros en la URL (usePaymentFilters).
// - DataTable: socio (enlace a la ficha), fecha y hora de Bogotá, membresía ("Mensual 29 oct–28 nov"),
//   valor, medio (etiqueta de Configuración), referencia, registró (el correo parcial tal cual,
//   S3-D57), StatusTag "Válido" o "Anulado" y la marca "Retroactivo" (S3-D51), y "Ver" que abre el
//   detalle (PaymentDetailModal, donde el admin anula). Sin editar ni borrar (DESIGN.md regla 4).
// - Estados: carga (esqueleto), vacío sin filtros (invita a registrar), vacío con filtros, página
//   pasada del final, error con Reintentar (403, 422, 429, 5xx y red en palabras de la pantalla).
// DESIGN-GAP:
// - La primera columna es el socio (DESIGN.md: la primera columna es el enlace a la ficha); Pagos.html
//   pone primero la fecha.
// - Sin "Exportar": la exportación es US-076 (fuera del Sprint 3).
// - "Registró" muestra el correo parcial ("c•••@apex.test", S3-D57) y no el nombre ("Carlos") hasta
//   US-110; sus opciones son "Yo" y quienes aparecen en la página (no hay lista de usuarios para el
//   coach).
// - Fechas con año y hora en 12 h ("20 oct 2026, 2:10 p. m."; DESIGN.md regla 7); el diseño escribe
//   "20 oct 14:10". Sin la nota "abono" en el valor (la fila no trae el saldo de la membresía).
// - El estado arranca en "Todos" (D37); Pagos.html dibuja "Válidos" primero. "Retroactivos" no está en
//   el diseño (S3-D51).
import { useMemo, useState } from "react";
import { Link, useLocation } from "react-router";
import { useSession } from "../../../core/auth";
import { useCan } from "../../../core/auth/useCan";
import { EMPTY_VALUE, formatCop, formatCount, formatDateTime } from "../../../core/i18n/format";
import { usePaymentMethodOptions } from "../../../shared/data/paymentMethods";
import { paymentPanelHref, readPaymentPanel } from "../../../shared/lib/paymentPanel";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { FilterBar, type FilterOption } from "../../../shared/ui/FilterBar";
import { PageHeader, type PageAction } from "../../../shared/ui/PageHeader";
import { Pagination } from "../../../shared/ui/Pagination";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { usePayments } from "../api";
import { MonthSummary } from "../components/MonthSummary";
import { PaymentDetailModal } from "../components/PaymentDetailModal";
import { memberHref, memberName, membershipText } from "../lib/paymentText";
import { paymentListError } from "../paymentErrors";
import type { PaymentRowView } from "../schemas";
import styles from "./PaymentsPage.module.css";
import { usePaymentFilters } from "./usePaymentFilters";

export const PAYMENTS_EMPTY = "Todavía no hay pagos registrados.";
export const PAYMENTS_EMPTY_FILTERED = "No hay pagos con estos filtros";
export const PAYMENTS_PAST_END = "Esta página ya no tiene pagos.";
export const RANGE_INVERTED = "La fecha 'Hasta' es anterior a 'Desde'. Corrígela para filtrar por fecha.";
export const BACKDATED_MARK = "Retroactivo";

const STATUS_OPTIONS: FilterOption[] = [
  { value: "false", label: "Válidos" },
  { value: "true", label: "Anulados" },
];

const BACKDATED_OPTIONS: FilterOption[] = [
  { value: "true", label: "Solo retroactivos" },
  { value: "false", label: "Sin retroactivos" },
];

interface Registrar {
  id: string;
  name: string | null;
}

/** Las opciones de "Registró": cada correo parcial repetido lleva un número para distinguirlo. */
export function registeredByOptions(sessionUser: { id: string; email: string } | null, seen: readonly Registrar[], selected: string): FilterOption[] {
  const options: FilterOption[] = sessionUser ? [{ value: sessionUser.id, label: `Yo (${sessionUser.email})` }] : [];
  const repeats = new Map<string, number>();
  for (const registrar of seen) {
    if (options.some((option) => option.value === registrar.id)) continue;
    const base = registrar.name ?? "Usuario sin correo";
    const count = (repeats.get(base) ?? 0) + 1;
    repeats.set(base, count);
    options.push({ value: registrar.id, label: count === 1 ? base : `${base} (${String(count)})` });
  }
  if (selected && !options.some((option) => option.value === selected)) options.push({ value: selected, label: "Usuario elegido" });
  return options;
}

/**
 * "Yo" (la sesión) y quienes registraron los pagos vistos en esta pantalla, sin repetir; el de la URL
 * siempre. Revisión S3-F6 (M2): las personas vistas se acumulan, así al filtrar por una (la página
 * solo trae sus pagos) las demás siguen en la lista.
 */
function useRegisteredByOptions(rows: readonly PaymentRowView[] | undefined, selected: string): FilterOption[] {
  const { user } = useSession();
  const [seen, setSeen] = useState<readonly Registrar[]>([]);
  const fresh = (rows ?? []).filter((row, index, all) => !seen.some((r) => r.id === row.registered_by) && all.findIndex((other) => other.registered_by === row.registered_by) === index);
  if (fresh.length > 0) setSeen([...seen, ...fresh.map((row) => ({ id: row.registered_by, name: row.registered_by_name }))]);
  return useMemo(() => registeredByOptions(user ? { id: user.id, email: user.email } : null, seen, selected), [user, seen, selected]);
}

function columnsFor(methodLabel: (code: PaymentRowView["method"]) => string, onView: (row: PaymentRowView) => void): Column<PaymentRowView>[] {
  return [
    { key: "member", header: "Socio", render: (row) => memberName(row) },
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
        </span>
      ),
    },
    {
      key: "actions",
      header: "Acción",
      align: "end",
      render: (row) => (
        <button
          type="button"
          className={styles.view}
          aria-label={`Ver el pago de ${memberName(row)}`}
          onClick={() => {
            onView(row);
          }}
        >
          Ver
        </button>
      ),
    },
  ];
}

export default function PaymentsPage() {
  const filters = usePaymentFilters();
  const { list, params } = filters;
  const location = useLocation();
  const canRegister = useCan("payments.register");
  const { methods } = usePaymentMethodOptions();
  const payments = usePayments(params);
  const page = payments.data;
  const registeredByOptions = useRegisteredByOptions(page?.items, filters.registeredBy);
  const [detailId, setDetailId] = useState<string | null>(null);
  // Al abrir el panel de pagos (p. ej. "Registrar pago nuevo" tras anular) el detalle se cierra: dos
  // diálogos a la vez se pelearían el foco.
  const panelOpen = readPaymentPanel(location.search) !== null;
  const [panelSeen, setPanelSeen] = useState(panelOpen);
  if (panelOpen !== panelSeen) {
    setPanelSeen(panelOpen);
    if (panelOpen) setDetailId(null);
  }
  // Un offset viejo (marcador, o el total bajó): hay pagos, pero esta página quedó vacía.
  const isPastEnd = page !== undefined && page.total > 0 && page.items.length === 0;

  const columns = useMemo(() => {
    const labels = new Map(methods.map((method) => [method.code, method.label]));
    return columnsFor(
      (code) => labels.get(code) ?? code,
      (row) => {
        setDetailId(row.id);
      },
    );
  }, [methods]);

  const registerHref = paymentPanelHref(location, { memberId: null });
  const actions: PageAction[] = canRegister ? [{ id: "register", label: "Registrar pago", href: registerHref, variant: "primary" }] : [];
  const methodOptions = methods.map((method) => ({ value: method.code, label: method.label }));

  return (
    <div className={styles.page}>
      {/* Revisión S3-F6 (L6): mientras llega la página nueva no se muestra el total de la anterior. */}
      <PageHeader title="Pagos" {...(page && !payments.isPlaceholderData ? { total: `${formatCount(page.total)} en total` } : {})} actions={actions} />
      <MonthSummary />
      <FilterBar
        query={list.q}
        onQueryChange={list.setQuery}
        onClear={list.clear}
        searchLabel="Buscar"
        searchPlaceholder="Socio o referencia"
        selects={[
          { name: "method", label: "Medio", value: filters.method, options: methodOptions, anyLabel: "Todos" },
          { name: "registered_by", label: "Registró", value: filters.registeredBy, options: registeredByOptions },
          { name: "voided", label: "Estado", value: filters.voided, options: STATUS_OPTIONS, anyLabel: "Todos" },
          { name: "backdated", label: "Retroactivos", value: filters.backdated, options: BACKDATED_OPTIONS, anyLabel: "Todos" },
        ]}
        onSelectChange={(name, value) => {
          if (name === "method" || name === "registered_by" || name === "voided" || name === "backdated") filters.setFilter(name, value);
        }}
        dateRange={{ label: "Fecha del pago", ...filters.range, onChange: filters.setRange }}
      />
      {filters.rangeInverted ? <p className={styles.rangeError}>{RANGE_INVERTED}</p> : null}
      <DataTable
        caption="Pagos"
        columns={columns}
        rows={page?.items}
        total={page?.total}
        limit={params.limit}
        rowKey={(row) => row.id}
        rowHref={(row) => memberHref(row.member_id)}
        // Mientras llega la página nueva no se muestran las filas de la anterior como si fueran ella.
        isLoading={payments.isLoading || payments.isPlaceholderData}
        error={paymentListError(payments.error)}
        onRetry={() => {
          void payments.refetch();
        }}
        emptyMessage={isPastEnd ? PAYMENTS_PAST_END : filters.isFiltered ? PAYMENTS_EMPTY_FILTERED : PAYMENTS_EMPTY}
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
          ) : filters.isFiltered ? (
            <Button variant="secondary" onClick={list.clear}>
              Limpiar filtros
            </Button>
          ) : canRegister ? (
            <Link className={styles.firstPayment} to={registerHref}>
              Registrar el primer pago
            </Link>
          ) : null
        }
      />
      {page && page.total > 0 ? <Pagination total={page.total} limit={params.limit} offset={params.offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
      {/* Revisión S3-F6 (M1): se monta solo con un pago elegido, así cada apertura empieza en el detalle. */}
      {detailId !== null ? (
        <PaymentDetailModal
          key={detailId}
          paymentId={detailId}
          onClose={() => {
            setDetailId(null);
          }}
        />
      ) : null}
    </div>
  );
}

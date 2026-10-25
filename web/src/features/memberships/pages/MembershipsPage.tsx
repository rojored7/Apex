// S3-F5 · US-089, US-090, US-091 y US-092 (front): /membresias (Membresias.html), admin y coach
// (`memberships.view`).
// - PageHeader "Membresías" con el total y "Vender membresía" (`memberships.sell`).
// - Resumen de socios por estado (MembershipsSummary, GET /memberships/summary).
// - Chips de estado, varios a la vez (Activas, Por vencer, Vencidas, Congeladas, Pendiente de pago,
//   Anuladas), plan y rango "Vence entre"; búsqueda por nombre o documento en memoria (S2-D41).
//   Filtros en la URL; `status` viaja separado por comas (useMembershipFilters, D18).
// - DataTable: socio (enlace a la ficha), plan y precio, inicio, fin, clases restantes, pagado y
//   StatusTag con texto; acciones de la fila (MembershipRowActions). Pagination de 25, 50 o 100.
// - Congelar y anular abren su modal (FreezeModal, CancelMembershipModal); al terminar, un aviso de la
//   página dice qué cambió y la lista y el resumen se releen (invalidación de las mutaciones).
// - Estados: carga (esqueleto), vacío sin filtros (invita a vender), vacío con filtros, página
//   pasada del final, error con Reintentar (403, 422, 429, 5xx y red en palabras de la pantalla).
// DESIGN-GAP:
// - "Pendiente de pago" (pending_payment, Q3) no está dibujado en Membresias.html: chip y StatusTag
//   con el tono de "Por vencer" y su texto (DESIGN.md).
// - Sin "Exportar": la exportación es US-076 (fuera del Sprint 3).
// - Sin el chip "Historial completo": sin estados la lista ya muestra todas menos las anuladas (D18);
//   marcar todos los chips muestra el historial completo.
// - Los conteos van en el resumen y no en los chips (ver MembershipsSummary).
// - Las fechas llevan el año ("29 sept 2026"; DESIGN.md regla 7); el diseño escribe "29 sep".
// - Estados de la fila con la etiqueta común del StatusTag ("Por vencer"), no "Vence en 8 días".
import { X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { formatCop, formatCount, formatDate } from "../../../core/i18n/format";
import type { MembershipRowView } from "../../../shared/data/memberships";
import { usePlans, type PlansParams } from "../../../shared/data/plans";
import { Button } from "../../../shared/ui/Button";
import { Chips, type ChipOption } from "../../../shared/ui/Chips";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { FilterBar, type FilterOption } from "../../../shared/ui/FilterBar";
import { PageHeader, type PageAction } from "../../../shared/ui/PageHeader";
import { Pagination } from "../../../shared/ui/Pagination";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { useMemberships } from "../api";
import { CancelMembershipModal, type CancelTarget } from "../components/CancelMembershipModal";
import { FreezeModal, type FreezeTarget } from "../components/FreezeModal";
import { MembershipRowActions } from "../components/MembershipRowActions";
import { MembershipsSummary } from "../components/MembershipsSummary";
import { classesRemainingText, paidText } from "../lib/rules";
import { listError } from "../membershipErrors";
import { memberHref, SELL_PATH } from "../membershipLinks";
import styles from "./MembershipsPage.module.css";
import { useMembershipFilters } from "./useMembershipFilters";

export const MEMBERSHIPS_EMPTY = "Todavía no hay membresías vigentes. Las anuladas se ven con el chip Anuladas.";
export const MEMBERSHIPS_EMPTY_FILTERED = "No hay membresías con estos filtros";
export const MEMBERSHIPS_PAST_END = "Esta página ya no tiene membresías.";
export const RANGE_INVERTED = "La segunda fecha de 'Vence entre' es anterior a la primera. Corrígela para filtrar por vencimiento.";

const STATUS_CHIPS: ChipOption[] = [
  { value: "active", label: "Activas" },
  { value: "expiring", label: "Por vencer" },
  { value: "expired", label: "Vencidas" },
  { value: "frozen", label: "Congeladas" },
  // DESIGN-GAP (Q3): no dibujado en Membresias.html; mismo tono que "Por vencer".
  { value: "pending_payment", label: "Pendiente de pago", tone: "warning" },
  { value: "cancelled", label: "Anuladas" },
];

/** El coach solo lee los planes activos (S2-D26); el admin, todos (también los de membresías viejas). */
const ALL_PLANS: PlansParams = { limit: 200, offset: 0 };
const ACTIVE_PLANS: PlansParams = { limit: 200, offset: 0, active: true };

type Notice = { kind: "frozen"; name: string; endDate: string } | { kind: "cancelled"; name: string };

function noticeText(notice: Notice): string {
  return notice.kind === "frozen"
    ? `Membresía de ${notice.name} congelada. Ahora termina el ${formatDate(notice.endDate)}.`
    : `Membresía de ${notice.name} anulada. Sus pagos siguen registrados.`;
}

/** El aviso de la página; la región existe siempre para que se anuncie. */
function PageNotice({ notice, onDismiss }: { notice: Notice | null; onDismiss: () => void }) {
  // Revisión S3-F5 (L7): tras congelar o anular el foco va al aviso; el botón que abrió el modal pudo
  // desaparecer de la lista (una anulada sale de la vista por defecto) y el foco caería en body.
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (notice) ref.current?.focus();
  }, [notice]);
  return (
    <div role="status">
      {notice ? (
        <div ref={ref} tabIndex={-1} className={styles.notice}>
          <p className={styles.noticeText}>{noticeText(notice)}</p>
          <button type="button" className={styles.dismiss} aria-label="Cerrar aviso" onClick={onDismiss}>
            <X size={20} aria-hidden="true" />
          </button>
        </div>
      ) : null}
    </div>
  );
}

function usePlanOptions(selectedId: string): FilterOption[] {
  const canSeeAllPlans = useCan("plans.view");
  const plans = usePlans(canSeeAllPlans ? ALL_PLANS : ACTIVE_PLANS);
  const options = (plans.data?.items ?? []).map((plan) => ({ value: plan.id, label: plan.name }));
  // Un plan de la URL que la lista no trae (inactivo para el coach) sigue visible como elegido.
  return selectedId && !options.some((option) => option.value === selectedId) ? [...options, { value: selectedId, label: "Plan elegido" }] : options;
}

function columnsFor(onFreeze: (row: MembershipRowView) => void, onCancel: (row: MembershipRowView) => void): Column<MembershipRowView>[] {
  return [
    { key: "member_name", header: "Socio", render: (row) => row.member_name },
    { key: "plan", header: "Plan", render: (row) => <span className={styles.nowrap}>{`${row.plan_name} · ${formatCop(row.agreed_price_cop)}`}</span> },
    { key: "start_date", header: "Inicio", render: (row) => <span className={styles.nowrap}>{formatDate(row.start_date)}</span> },
    { key: "end_date", header: "Fin", render: (row) => <span className={styles.nowrap}>{formatDate(row.end_date)}</span> },
    { key: "classes_remaining", header: "Clases restantes", render: (row) => classesRemainingText(row.classes_remaining, row.classes_total) },
    { key: "paid_cop", header: "Pagado", render: (row) => paidText(row.paid_cop, row.agreed_price_cop) },
    { key: "status", header: "Estado", render: (row) => <StatusTag status={row.status} /> },
    { key: "actions", header: "Acciones", align: "end", wide: true, render: (row) => <MembershipRowActions row={row} onFreeze={onFreeze} onCancel={onCancel} /> },
  ];
}

export default function MembershipsPage() {
  const filters = useMembershipFilters();
  const { list, params } = filters;
  const canSell = useCan("memberships.sell");
  const planOptions = usePlanOptions(filters.planId);
  const memberships = useMemberships(params);
  const page = memberships.data;
  const [freezeTarget, setFreezeTarget] = useState<FreezeTarget | null>(null);
  const [cancelTarget, setCancelTarget] = useState<CancelTarget | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  // Un offset viejo (marcador, o el total bajó): hay membresías, pero esta página quedó vacía.
  const isPastEnd = page !== undefined && page.total > 0 && page.items.length === 0;

  const columns = useMemo(
    () =>
      columnsFor(
        (row) => {
          setNotice(null);
          setFreezeTarget({ id: row.id, member_name: row.member_name, end_date: row.end_date });
        },
        (row) => {
          setNotice(null);
          setCancelTarget({ id: row.id, member_name: row.member_name });
        },
      ),
    [],
  );

  const actions: PageAction[] = canSell ? [{ id: "sell", label: "Vender membresía", href: SELL_PATH, variant: "primary" }] : [];

  return (
    <div className={styles.page}>
      <PageHeader title="Membresías" {...(page ? { total: `${formatCount(page.total)} en total` } : {})} actions={actions} />
      <PageNotice
        notice={notice}
        onDismiss={() => {
          setNotice(null);
        }}
      />
      <MembershipsSummary />
      <Chips label="Estado" mode="multiple" options={STATUS_CHIPS} value={filters.statuses} onChange={filters.setStatuses} />
      <FilterBar
        query={list.q}
        onQueryChange={list.setQuery}
        onClear={list.clear}
        searchLabel="Buscar socio"
        searchPlaceholder="Nombre o documento"
        selects={[{ name: "plan_id", label: "Plan", value: filters.planId, options: planOptions }]}
        onSelectChange={(_name, value) => {
          filters.setPlan(value);
        }}
        dateRange={{ label: "Vence entre", ...filters.range, onChange: filters.setRange }}
      />
      {filters.rangeInverted ? <p className={styles.rangeError}>{RANGE_INVERTED}</p> : null}
      <DataTable
        caption="Membresías"
        columns={columns}
        rows={page?.items}
        total={page?.total}
        limit={params.limit}
        rowKey={(row) => row.id}
        rowHref={(row) => memberHref(row.member_id)}
        // Mientras llega la página nueva no se muestran las filas de la anterior como si fueran ella.
        isLoading={memberships.isLoading || memberships.isPlaceholderData}
        error={listError(memberships.error)}
        onRetry={() => {
          void memberships.refetch();
        }}
        emptyMessage={isPastEnd ? MEMBERSHIPS_PAST_END : filters.isFiltered ? MEMBERSHIPS_EMPTY_FILTERED : MEMBERSHIPS_EMPTY}
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
          ) : canSell ? (
            <Link className={styles.firstSale} to={SELL_PATH}>
              Vender la primera membresía
            </Link>
          ) : null
        }
      />
      {page && page.total > 0 ? <Pagination total={page.total} limit={params.limit} offset={params.offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
      <FreezeModal
        membership={freezeTarget}
        onClose={() => {
          setFreezeTarget(null);
        }}
        onFrozen={(target, endDate) => {
          setFreezeTarget(null);
          setNotice({ kind: "frozen", name: target.member_name, endDate });
        }}
      />
      <CancelMembershipModal
        membership={cancelTarget}
        onClose={() => {
          setCancelTarget(null);
        }}
        onCancelled={(target) => {
          setCancelTarget(null);
          setNotice({ kind: "cancelled", name: target.member_name });
        }}
      />
    </div>
  );
}

// S2-F7 · US-079 y US-078 (front): /planes (Planes.html). S2-D26: la ruta es solo admin
// (`plans.view`); la página igual respeta el alcance del api por si otro rol llega a montarla: sin
// `plans.manage` no hay "Nuevo plan" ni el filtro de estado y siempre pide `active=true`.
// - PageHeader "Planes" con el total y "Nuevo plan" (PlanForm en un SidePanel).
// - FilterBar: búsqueda por nombre con la espera de 300 ms de FilterBar y, por S2-D41, solo en
//   memoria (useListParams con localQuery); "Estado" (Todos, Activos, Inactivos) en la URL como
//   `active`. Un valor desconocido no viaja. Cambiar la búsqueda vuelve a la primera página y
//   cancela la petición anterior (signal).
// - DataTable: plan (enlace a /planes?plan=<id>), tipo, precio en COP, duración, clases y
//   StatusTag "Activo" o "Inactivo". Estados de carga, vacío, sin coincidencias, página fuera de
//   rango, error con Reintentar, 403 y respuesta inválida. Pagination.
// - `?plan=<id>` abre PlanDetailPanel (solo lectura); al cerrarlo se quita de la URL.
// - El 201 del alta deja el aviso "Plan creado: <nombre>." (se puede cerrar).
// DESIGN-GAP:
// - Sin la columna "Socios con él": el conteo llega con las membresías (Sprint 3).
// - Sin la acción "Editar" en la fila: la edición llega con el Sprint 4A; la fila abre el detalle.
// - El total no se parte en "N activos · M inactivos": GET /plans no da los dos conteos.
// - "Duración" y "Clases" van en columnas propias (blueprint F7); Planes.html las junta.
// - El filtro se llama "Estado" y no "Mostrar" (Planes.html): "Mostrar" ya es el tamaño de página
//   de Pagination y dos controles con el mismo nombre confunden al lector de pantalla.
import { X } from "lucide-react";
import { useMemo, useState } from "react";
import { useLocation, useSearchParams } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { EMPTY_VALUE, formatCop, formatCount } from "../../../core/i18n/format";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { FilterBar } from "../../../shared/ui/FilterBar";
import { PageHeader, type PageAction } from "../../../shared/ui/PageHeader";
import { Pagination } from "../../../shared/ui/Pagination";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { usePlans, type PlansParams } from "../api";
import { PlanDetailPanel } from "../components/PlanDetailPanel";
import { PlanForm } from "../components/PlanForm";
import { listError } from "../planErrors";
import { PLAN_PARAM, planHref } from "../planLinks";
import { ACTIVE_FILTERS, classesText, daysText, PLAN_KIND_LABELS, type ActiveFilter, type PlanRowView } from "../schemas";
import styles from "./PlansPage.module.css";

const FILTERS = ["active"] as const;

export const PLANS_EMPTY = "No hay planes.";
export const PLANS_EMPTY_SEARCH = "No hay planes que coincidan con la búsqueda";
export const PLANS_PAST_END = "Esta página ya no tiene planes.";
export const ACTIVE_ONLY_NOTE = "Ves solo los planes activos.";

const SHOW_OPTIONS = [
  { value: "true", label: "Activos" },
  { value: "false", label: "Inactivos" },
];

const COLUMNS: Column<PlanRowView>[] = [
  { key: "name", header: "Plan", render: (row) => row.name },
  { key: "kind", header: "Tipo", render: (row) => PLAN_KIND_LABELS[row.kind] },
  { key: "price_cop", header: "Precio", render: (row) => <span className={styles.number}>{formatCop(row.price_cop)}</span> },
  { key: "duration_days", header: "Duración", render: (row) => <span className={styles.number}>{daysText(row.duration_days)}</span> },
  {
    key: "class_count",
    header: "Clases",
    render: (row) => (row.kind === "classes" && row.class_count !== null ? <span className={styles.number}>{classesText(row.class_count)}</span> : EMPTY_VALUE),
  },
  { key: "is_active", header: "Estado", render: (row) => <StatusTag account={row.is_active ? "active" : "inactive"} /> },
];

function pickActive(values: readonly string[]): ActiveFilter | undefined {
  const [first] = values;
  return ACTIVE_FILTERS.find((value) => value === first);
}

/** El aviso del alta; la región existe siempre para que se anuncie. */
function CreatedNotice({ name, onDismiss }: { name: string | null; onDismiss: () => void }) {
  return (
    <div role="status">
      {name ? (
        <div className={styles.notice}>
          <p className={styles.noticeText}>{`Plan creado: ${name}.`}</p>
          <button type="button" className={styles.dismiss} aria-label="Cerrar aviso" onClick={onDismiss}>
            <X size={20} aria-hidden="true" />
          </button>
        </div>
      ) : null}
    </div>
  );
}

/** `?plan=<id>` abre el detalle; al cerrarlo se quita sin sumar una entrada al historial. */
function usePlanParam(): [string | null, () => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  // `?plan=` vacío no abre nada.
  const planId = searchParams.get(PLAN_PARAM) || null;
  const close = (): void => {
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.delete(PLAN_PARAM);
        return next;
      },
      { replace: true },
    );
  };
  return [planId, close];
}

export default function PlansPage() {
  const list = useListParams<(typeof FILTERS)[number]>({ filters: FILTERS, localQuery: true });
  const location = useLocation();
  const canManage = useCan("plans.manage");
  const [creating, setCreating] = useState(false);
  const [createdName, setCreatedName] = useState<string | null>(null);
  const [planId, closePlan] = usePlanParam();
  // S2-D26: sin plans.manage el api solo responde con active=true (si no, 403).
  const shown = canManage ? pickActive(list.filters.active) : "true";
  const { limit, offset } = list.params;
  const { q } = list;

  const params = useMemo<PlansParams>(
    () => ({ limit, offset, ...(q ? { q } : {}), ...(shown ? { active: shown === "true" } : {}) }),
    [limit, offset, q, shown],
  );
  const plans = usePlans(params);
  const page = plans.data;
  // Revisión L6: mientras llega la consulta nueva, el total y el "fuera de rango" de la anterior
  // no se muestran como si fueran de ella (las filas ya las cubre el estado de carga).
  const settled = plans.isPlaceholderData ? undefined : page;
  const isFiltered = Boolean(q) || (canManage && shown !== undefined);
  // Un offset viejo (marcador, o el total bajó): hay planes, pero esta página quedó vacía.
  const isPastEnd = settled !== undefined && settled.total > 0 && settled.items.length === 0;
  const openNew = (): void => {
    setCreating(true);
  };

  const actions: PageAction[] = canManage ? [{ id: "new-plan", label: "Nuevo plan", variant: "primary", onClick: openNew }] : [];

  return (
    <div className={styles.page}>
      <PageHeader title="Planes" {...(settled ? { total: `${formatCount(settled.total)} en total` } : {})} actions={actions} />
      <CreatedNotice
        name={createdName}
        onDismiss={() => {
          setCreatedName(null);
        }}
      />
      <FilterBar
        query={list.q}
        onQueryChange={list.setQuery}
        onClear={list.clear}
        searchPlaceholder="Nombre del plan"
        selects={canManage ? [{ name: "active", label: "Estado", value: shown ?? "", options: SHOW_OPTIONS, anyLabel: "Todos" }] : []}
        onSelectChange={(name, value) => {
          if (name === "active") list.setFilter("active", value || undefined);
        }}
      />
      {canManage ? null : <p className={styles.note}>{ACTIVE_ONLY_NOTE}</p>}
      <DataTable
        caption="Planes"
        columns={COLUMNS}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(row) => row.id}
        rowHref={(row) => planHref(row.id, location.search)}
        // Mientras llega la página nueva no se muestran las filas de la anterior como si fueran ella.
        isLoading={plans.isLoading || plans.isPlaceholderData}
        error={listError(plans.error)}
        onRetry={() => {
          void plans.refetch();
        }}
        emptyMessage={isPastEnd ? PLANS_PAST_END : isFiltered ? PLANS_EMPTY_SEARCH : PLANS_EMPTY}
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
          ) : isFiltered ? (
            <Button variant="secondary" onClick={list.clear}>
              Limpiar filtros
            </Button>
          ) : canManage ? (
            <Button onClick={openNew}>Crear el primer plan</Button>
          ) : null
        }
      />
      {page && page.total > 0 ? <Pagination total={page.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
      <p className={styles.note}>Las membresías ya vendidas guardan su propio precio: cambiar el precio de un plan no cambia lo vendido. Un plan con socios no se borra, se desactiva.</p>
      {canManage ? (
        <PlanForm
          open={creating}
          onClose={() => {
            setCreating(false);
          }}
          onCreated={(plan) => {
            setCreatedName(plan.name);
          }}
        />
      ) : null}
      <PlanDetailPanel planId={planId} onClose={closePlan} />
    </div>
  );
}

// S2-F7 · US-079 y US-078 (front): /planes (Planes.html). S2-D26: la ruta es solo admin
// (`plans.view`); la página igual respeta el alcance del api por si otro rol llega a montarla: sin
// `plans.manage` no hay "Nuevo plan", ni el filtro de estado, ni acciones, y siempre pide `active=true`.
// - PageHeader "Planes" con el total y "Nuevo plan" (PlanForm en un SidePanel).
// - FilterBar: búsqueda por nombre con la espera de 300 ms de FilterBar y, por S2-D41, solo en
//   memoria (useListParams con localQuery); "Estado" (Todos, Activos, Inactivos) en la URL como
//   `active`. Un valor desconocido no viaja. Cambiar la búsqueda vuelve a la primera página y
//   cancela la petición anterior (signal).
// - DataTable: plan (enlace a /planes?plan=<id>), tipo, precio en COP, duración, clases, socios con
//   él y StatusTag "Activo" o "Inactivo". Estados de carga, vacío, sin coincidencias, página fuera de
//   rango, error con Reintentar, 403 y respuesta inválida. Pagination.
// - `?plan=<id>` abre PlanDetailPanel (solo lectura); al cerrarlo se quita de la URL.
// S4A-F4 · US-080, US-081 y US-082 (S4A-D25, S4A-D34):
// - Columna "Socios con él" (`active_members_count`) y, con `plans.manage`, columna "Acción"
//   (PlanRowActions: Editar, Activar o Desactivar, Dar de baja).
// - El total del admin es "N activos · M inactivos" (dos GET /plans de limit=1, usePlanCount); no
//   depende de la búsqueda ni del filtro. Sin `plans.manage`, "N en total" de la lista.
// - Editar abre PlanForm en modo edición (un panel por plan, `key`); desactivar y dar de baja piden
//   confirmación (PlanConfirmDialog); activar va directo. Los avisos van en PlanNotices; el 409 de la
//   baja ofrece "Desactivar". El estado vive en usePlanRowActions.
// DESIGN-GAP:
// - "Duración" y "Clases" van en columnas propias (blueprint F7); Planes.html las junta ("12 clases ·
//   60 días para usarlas"): la columna no dice "Días para usarlas" y la duración se lee en "Duración".
// - Sin "Descripción" en la lista ni en el panel: el api no la tiene (S4A-D25).
// - Sin la casilla "Activo (se puede vender)" en el panel: Activar y Desactivar son acciones de la
//   fila (S4A-D23).
// - El filtro se llama "Estado" y no "Mostrar" (Planes.html): "Mostrar" ya es el tamaño de página
//   de Pagination y dos controles con el mismo nombre confunden al lector de pantalla.
// - La rama sin `plans.manage` (contradicción 7 de la revisión general del Sprint 2) hoy no se
//   alcanza: `plans.view` es solo admin en el front (S2-D26) aunque el api deja al coach leer los
//   planes activos (SPRINT-02.md). Se conserva, con sus pruebas, para que abrir /planes al coach
//   sea solo un cambio de la matriz y no deje la pantalla pidiendo inactivos (403).
import { useMemo, useState } from "react";
import { useLocation, useSearchParams } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { EMPTY_VALUE, formatCop, formatCount } from "../../../core/i18n/format";
import { useListParams } from "../../../shared/hooks/useListParams";
import { isUuid } from "../../../shared/lib/ids";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { FilterBar } from "../../../shared/ui/FilterBar";
import { PageHeader, type PageAction } from "../../../shared/ui/PageHeader";
import { Pagination } from "../../../shared/ui/Pagination";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { usePlanCount, usePlans, type PlansParams } from "../api";
import { PlanConfirmDialog, PlanNotices } from "../components/PlanActionDialogs";
import { PlanDetailPanel } from "../components/PlanDetailPanel";
import { PlanForm } from "../components/PlanForm";
import { PlanRowActions, type PlanRowAction } from "../components/PlanRowActions";
import { listError } from "../planErrors";
import { PLAN_PARAM, planHref } from "../planLinks";
import { ACTIVE_FILTERS, classesText, daysText, PLAN_KIND_LABELS, planTotalsText, type ActiveFilter, type PlanRowView } from "../schemas";
import styles from "./PlansPage.module.css";
import { PLAN_NOTICES, usePlanRowActions } from "./usePlanRowActions";

const FILTERS = ["active"] as const;

export const PLANS_EMPTY = "No hay planes.";
export const PLANS_EMPTY_SEARCH = "No hay planes que coincidan con la búsqueda";
export const PLANS_PAST_END = "Esta página ya no tiene planes.";
export const ACTIVE_ONLY_NOTE = "Ves solo los planes activos.";

const SHOW_OPTIONS = [
  { value: "true", label: "Activos" },
  { value: "false", label: "Inactivos" },
];

const BASE_COLUMNS: Column<PlanRowView>[] = [
  { key: "name", header: "Plan", render: (row) => row.name },
  { key: "kind", header: "Tipo", render: (row) => PLAN_KIND_LABELS[row.kind] },
  { key: "price_cop", header: "Precio", render: (row) => <span className={styles.number}>{formatCop(row.price_cop)}</span> },
  { key: "duration_days", header: "Duración", render: (row) => <span className={styles.number}>{daysText(row.duration_days)}</span> },
  {
    key: "class_count",
    header: "Clases",
    render: (row) => (row.kind === "classes" && row.class_count !== null ? <span className={styles.number}>{classesText(row.class_count)}</span> : EMPTY_VALUE),
  },
  { key: "active_members_count", header: "Socios con él", render: (row) => <span className={styles.number}>{formatCount(row.active_members_count)}</span> },
  { key: "is_active", header: "Estado", render: (row) => <StatusTag account={row.is_active ? "active" : "inactive"} /> },
];

function columnsFor(canManage: boolean, onAction: (action: PlanRowAction, row: PlanRowView) => void, isChangingState: boolean): Column<PlanRowView>[] {
  if (!canManage) return BASE_COLUMNS;
  return [...BASE_COLUMNS, { key: "actions", header: "Acción", align: "end", wide: true, render: (row) => <PlanRowActions row={row} onAction={onAction} isChangingState={isChangingState} /> }];
}

function pickActive(values: readonly string[]): ActiveFilter | undefined {
  const [first] = values;
  return ACTIVE_FILTERS.find((value) => value === first);
}

/** `?plan=<id>` abre el detalle; al cerrarlo se quita sin sumar una entrada al historial. */
function usePlanParam(): [string | null, () => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  // `?plan=` vacío o sin forma de UUID no abre nada ni pide nada (revisión de seguridad de F4, LOW-1).
  const raw = searchParams.get(PLAN_PARAM) ?? "";
  const planId = isUuid(raw) ? raw : null;
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

/** S4A-F4: "N activos · M inactivos" con `plans.manage`; sin él, el total de la lista. */
function useTotalText(canManage: boolean, listTotal: number | undefined): string | undefined {
  const activeCount = usePlanCount(true, canManage);
  const inactiveCount = usePlanCount(false, canManage);
  if (!canManage) return listTotal === undefined ? undefined : `${formatCount(listTotal)} en total`;
  if (activeCount.data === undefined || inactiveCount.data === undefined) return undefined;
  return planTotalsText(activeCount.data, inactiveCount.data);
}

export default function PlansPage() {
  const list = useListParams<(typeof FILTERS)[number]>({ filters: FILTERS, localQuery: true });
  const location = useLocation();
  const canManage = useCan("plans.manage");
  const actions = usePlanRowActions();
  const [creating, setCreating] = useState(false);
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
  const total = useTotalText(canManage, settled?.total);
  const isFiltered = Boolean(q) || (canManage && shown !== undefined);
  // Un offset viejo (marcador, o el total bajó): hay planes, pero esta página quedó vacía.
  const isPastEnd = settled !== undefined && settled.total > 0 && settled.items.length === 0;
  const columns = columnsFor(canManage, actions.onAction, actions.isChangingState);
  const openNew = (): void => {
    setCreating(true);
  };

  const headerActions: PageAction[] = canManage ? [{ id: "new-plan", label: "Nuevo plan", variant: "primary", onClick: openNew }] : [];

  return (
    <div className={styles.page}>
      <PageHeader title="Planes" {...(total ? { total } : {})} actions={headerActions} />
      <PlanNotices
        notice={actions.notice}
        problem={actions.problem}
        isDeactivating={actions.isChangingState}
        onDismissNotice={() => {
          actions.setNotice(null);
        }}
        onDismissProblem={actions.dismissProblem}
        onDeactivate={(row) => {
          void actions.deactivateInstead(row);
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
        columns={columns}
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
        <>
          <PlanForm
            open={creating}
            onClose={() => {
              setCreating(false);
            }}
            onCreated={(plan) => {
              actions.setNotice(PLAN_NOTICES.created(plan.name));
            }}
          />
          {actions.editing ? (
            <PlanForm
              key={actions.editing.id}
              open
              plan={actions.editing}
              onClose={actions.closeEditing}
              onSaved={(plan) => {
                actions.setNotice(PLAN_NOTICES.saved(plan.name));
              }}
            />
          ) : null}
          <PlanConfirmDialog confirming={actions.confirming} onDeactivate={actions.confirmDeactivate} onDelete={actions.confirmDelete} onClose={actions.closeConfirming} />
        </>
      ) : null}
      <PlanDetailPanel planId={planId} onClose={closePlan} />
    </div>
  );
}

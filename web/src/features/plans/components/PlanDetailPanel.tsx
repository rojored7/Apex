// S2-F7 · US-079 (front): detalle de solo lectura de un plan (`?plan=<id>` sobre /planes).
// - usePlan(id): carga, el plan en una lista de definiciones (precio en COP, tipo, clases o
//   duración, estado con StatusTag y fecha de creación) y los errores con mensaje propio: 403 (el
//   coach sobre un plan inactivo, S2-D26), 404 y el resto con "Reintentar".
// S4A-F4: la edición (PATCH /plans/{id}) se abre con "Editar" en la fila (PlanRowActions); este
// panel sigue de solo lectura y lo dice.
// DESIGN-GAP: Planes.html no tiene un detalle de solo lectura (el nombre abre "Editar plan"); el
// detalle se conserva para el enlace del 409 del alta y para quien no puede editar.
import { formatCop, formatDate } from "../../../core/i18n/format";
import { Button } from "../../../shared/ui/Button";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { usePlan } from "../api";
import { detailErrorMessage, isTransientError } from "../planErrors";
import { classesText, daysText, PLAN_KIND_LABELS, type PlanRowView } from "../schemas";
import styles from "./PlanDetailPanel.module.css";

export interface PlanDetailPanelProps {
  planId: string | null;
  onClose: () => void;
}

const LOADING_TITLE = "Plan";

function PlanFacts({ plan }: { plan: PlanRowView }) {
  const isByClasses = plan.kind === "classes" && plan.class_count !== null;
  return (
    <dl className={styles.facts}>
      <div className={styles.fact}>
        <dt>Precio</dt>
        <dd className={styles.number}>{formatCop(plan.price_cop)}</dd>
      </div>
      <div className={styles.fact}>
        <dt>Tipo</dt>
        <dd>{PLAN_KIND_LABELS[plan.kind]}</dd>
      </div>
      {isByClasses ? (
        <>
          <div className={styles.fact}>
            <dt>Número de clases</dt>
            <dd className={styles.number}>{classesText(plan.class_count ?? 0)}</dd>
          </div>
          <div className={styles.fact}>
            <dt>Días para usarlas</dt>
            <dd className={styles.number}>{daysText(plan.duration_days)}</dd>
          </div>
        </>
      ) : (
        <div className={styles.fact}>
          <dt>Duración</dt>
          <dd className={styles.number}>{daysText(plan.duration_days)}</dd>
        </div>
      )}
      <div className={styles.fact}>
        <dt>Estado</dt>
        <dd>
          <StatusTag account={plan.is_active ? "active" : "inactive"} />
        </dd>
      </div>
      <div className={styles.fact}>
        <dt>Creado</dt>
        <dd>{formatDate(plan.created_at)}</dd>
      </div>
    </dl>
  );
}

export function PlanDetailPanel({ planId, onClose }: PlanDetailPanelProps) {
  const query = usePlan(planId);
  const plan = query.data;
  // Un 403 o un 404 no cambian al reintentar; un 5xx o la red sí.
  const isRetryable = query.error !== null && !query.isFetching && isTransientError(query.error);

  return (
    <SidePanel open={planId !== null} title={plan?.name ?? LOADING_TITLE} onClose={onClose} cancelLabel="Volver a la lista">
      {plan ? (
        <div className={styles.body}>
          <PlanFacts plan={plan} />
          <p className={styles.note}>Para cambiarlo, usa Editar en la fila del plan.</p>
        </div>
      ) : query.error ? (
        <div className={styles.body}>
          <p className={styles.error} role="alert">
            {detailErrorMessage(query.error)}
          </p>
          {isRetryable ? (
            <Button
              variant="secondary"
              onClick={() => {
                void query.refetch();
              }}
            >
              Reintentar
            </Button>
          ) : null}
        </div>
      ) : (
        <p className={styles.note} role="status">
          Cargando el plan…
        </p>
      )}
    </SidePanel>
  );
}

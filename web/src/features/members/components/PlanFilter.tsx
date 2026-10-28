// S3-F2 · US-071 (front): el filtro "Plan" de /socios (Socios_Lista.html).
// - Es un `<select>` dentro de `Field`: lo pinta FilterBar a partir de la descripción que arma
//   usePlanFilter, así queda en la misma fila que la búsqueda y "Limpiar" también lo borra.
// - Las opciones salen de `usePlans({ active: true })` de shared/data (el coach no ve /planes,
//   pero sí GET /plans?active=true, S2-D26), hasta 200 planes sin paginar.
// - `plan_id` filtra por el plan de la membresía que decide el estado del socio (D22). Un plan de
//   la URL que la lista no trae (inactivo o de más de 200) sigue elegido como "Plan elegido". Si el
//   api tiene más de 200, el select lo dice bajo el control (plansShownNote, Fase 4 L8).
// - readPlanId: solo un UUID viaja al api; cualquier otro texto de la URL se ignora.
import { plansShownNote, usePlans, type PlansParams } from "../../../shared/data/plans";
import { isUuid } from "../../../shared/lib/ids";
import type { FilterSelect } from "../../../shared/ui/FilterBar";

export const PLAN_FILTER_NAME = "plan_id";
export const CHOSEN_PLAN_LABEL = "Plan elegido";

const ACTIVE_PLANS: PlansParams = { limit: 200, offset: 0, active: true };

/** El `plan_id` de la URL si es un UUID, o "". */
export function readPlanId(values: readonly string[]): string {
  const raw = values[0] ?? "";
  return isUuid(raw) ? raw : "";
}

/** La descripción del select "Plan" para FilterBar (`selects`). */
export function usePlanFilter(planId: string): FilterSelect {
  const plans = usePlans(ACTIVE_PLANS);
  const options = (plans.data?.items ?? []).map((plan) => ({ value: plan.id, label: plan.name }));
  const withChosen = planId && !options.some((option) => option.value === planId) ? [...options, { value: planId, label: CHOSEN_PLAN_LABEL }] : options;
  const hint = plansShownNote(plans.data);
  return { name: PLAN_FILTER_NAME, label: "Plan", value: planId, options: withChosen, ...(hint ? { hint } : {}) };
}

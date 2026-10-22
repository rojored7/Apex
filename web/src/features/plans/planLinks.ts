// S2-F7: enlace a un plan. No hay ficha de plan: es `?plan=<id>` sobre /planes, donde se abre su
// detalle de solo lectura (la edición llega con el Sprint 4A). Lo usan las filas de la tabla y el
// 409 del alta (plan existente). Con `search` (la búsqueda actual de la lista) se conservan los
// filtros de la URL; el id va escapado.
export const PLANS_PATH = "/planes";
export const PLAN_PARAM = "plan";

export function planHref(id: string, search = ""): string {
  const params = new URLSearchParams(search);
  params.delete(PLAN_PARAM);
  params.set(PLAN_PARAM, id);
  return `${PLANS_PATH}?${params.toString()}`;
}

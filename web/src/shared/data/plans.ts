// S3-F3 (S3-D65, condición 8): datos de planes que comparten varias features. Nació en S2-F7 en
// features/plans/api.ts y schemas.ts y se mueve aquí sin cambiar su comportamiento; esos dos
// archivos lo reexportan para que PlansPage y sus pruebas no cambien.
// - usePlans(params): GET /plans con la clave ["plans", params]; la página se valida con Zod (una
//   forma inesperada es `invalid_response`). Usa el `signal` de TanStack Query: al cambiar la
//   búsqueda, la anterior se cancela. `q` viaja solo en la petición (nunca en la URL de la app,
//   S2-D41) y mientras llega la página nueva se conserva la anterior.
// - El coach no ve /planes, pero sí `GET /plans?active=true` (S2-D26): la venta lo usa con
//   `{ active: true }`.
import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../../core/api/client";
import { pageSchema, type Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import { formatCount } from "../../core/i18n/format";
import type { components } from "../../core/api/types";

export type PlanKind = components["schemas"]["PlanCreate"]["kind"];

export const PLAN_KINDS = ["days", "classes"] as const satisfies readonly PlanKind[];

export const planRowSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  price_cop: z.number().int(),
  kind: z.enum(PLAN_KINDS),
  duration_days: z.number().int(),
  class_count: z.number().int().nullable(),
  is_active: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type PlanRowView = z.infer<typeof planRowSchema>;

export const plansPageSchema = pageSchema(planRowSchema);

export interface PlansParams {
  limit: number;
  offset: number;
  q?: string;
  active?: boolean;
}

export const PLANS_QUERY_KEY = ["plans"] as const;

export function plansQueryKey(params: PlansParams): readonly ["plans", PlansParams] {
  return ["plans", params];
}

export function usePlans(params: PlansParams): UseQueryResult<Page<PlanRowView>> {
  return useQuery({
    queryKey: plansQueryKey(params),
    queryFn: async ({ signal }) => parseResponse(plansPageSchema, await api.get<unknown>("/plans", { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
  });
}

/**
 * Fase 4 del Sprint 3 (L8): la venta pide hasta 100 planes activos y los filtros de Membresías y Socios
 * hasta 200, sin paginar (un gimnasio tiene pocos). Si el api tiene más, la pantalla lo dice en vez de
 * esconder los demás: "Se muestran 2 de 230 planes. …". null si trae todos.
 */
export function plansShownNote(page: Page<unknown> | undefined): string | null {
  if (!page || page.total <= page.items.length) return null;
  return `Se muestran ${formatCount(page.items.length)} de ${formatCount(page.total)} planes. Si falta el que buscas, avísale a un administrador.`;
}

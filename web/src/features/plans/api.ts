// S2-F7 · US-078 y US-079 (front): datos de planes (contrato de B9).
// - usePlans(params), PlansParams, plansQueryKey y PLANS_QUERY_KEY viven desde S3-F3 en
//   shared/data/plans.ts (S3-D65: los usa también la venta de membresías) y se reexportan aquí.
// - usePlan(id): GET /plans/{id} con la clave ["plans", "detail", id]; sin id no pide nada. El 403
//   (el coach sobre un plan inactivo, S2-D26) y el 404 no se reintentan (shouldRetry del cliente).
// - useCreatePlan(): POST /plans → 201 PlanOut. Al salir bien invalida ["plans"] (lista y
//   detalles). Los errores llegan como ApiError (409 con `existingId`, 422 con `field`) y los
//   traduce planErrors.ts.
// S4A-F4 · US-080, US-081 y US-082 (S4A-D34, S4A-D35): las tres escrituras nuevas pasan por
// useSensitiveMutation (gcTime 0 y reset() al terminar: la caché de mutaciones no guarda variables)
// y, al salir bien, invalidan ["plans"] (lista, totales y detalles).
// - useUpdatePlan(id): PATCH /plans/{id} con solo los campos modificados → 200 PlanOut.
// - useSetPlanActive(): POST /plans/{id}/activate o /deactivate (idempotentes) → 200 PlanOut.
// - usePlanCount(active, enabled): el total de activos o de inactivos ("N activos · M inactivos").
// - useDeletePlan(): DELETE /plans/{id} → 204; el 409 `plan_has_active_memberships` trae el conteo.
import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";
import { api } from "../../core/api/client";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import { useSensitiveMutation } from "../../core/api/useSensitiveMutation";
import { PLANS_QUERY_KEY, plansPageSchema, plansQueryKey, type PlansParams } from "../../shared/data/plans";
import { planRowSchema, type PlanCreateBody, type PlanPatchBody, type PlanRowView } from "./schemas";

export { PLANS_QUERY_KEY, plansQueryKey, usePlans, type PlansParams } from "../../shared/data/plans";

export function planQueryKey(id: string): readonly ["plans", "detail", string] {
  return ["plans", "detail", id];
}

const planPath = (id: string): string => `/plans/${encodeURIComponent(id)}`;

export function usePlan(id: string | null): UseQueryResult<PlanRowView> {
  return useQuery({
    queryKey: planQueryKey(id ?? ""),
    queryFn: async ({ signal }) => parseResponse(planRowSchema, await api.get<unknown>(planPath(id ?? ""), { signal })),
    enabled: Boolean(id),
  });
}

export function useCreatePlan(): UseMutationResult<PlanRowView, Error, PlanCreateBody> {
  const queryClient = useQueryClient();
  return useMutation<PlanRowView, Error, PlanCreateBody>({
    mutationFn: async (body) => parseResponse(planRowSchema, await api.post<unknown>("/plans", { body })),
    onSuccess: () => {
      // Sin esperar la relectura: el panel se cierra enseguida y la lista se actualiza sola.
      void queryClient.invalidateQueries({ queryKey: PLANS_QUERY_KEY });
    },
  });
}

/**
 * S4A-F4 (S4A-D25): el total de planes activos o inactivos, de GET /plans?limit=1&offset=0&active=.
 * Es usePlans con `limit` 1 (misma clave y misma validación), pero se puede apagar: sin
 * `plans.manage` el api no deja leer los inactivos (S2-D26) y la pantalla no lo pide.
 */
export function usePlanCount(active: boolean, enabled: boolean): UseQueryResult<number> {
  const params: PlansParams = { limit: 1, offset: 0, active };
  return useQuery({
    queryKey: plansQueryKey(params),
    queryFn: async ({ signal }) => parseResponse(plansPageSchema, await api.get<unknown>("/plans", { query: listParams({ ...params }), signal })),
    select: (page) => page.total,
    enabled,
  });
}

/** PATCH /plans/{id}: solo los campos modificados (toPlanPatch). */
export function useUpdatePlan(id: string): UseMutationResult<PlanRowView, Error, PlanPatchBody> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<PlanRowView, Error, PlanPatchBody>({
    mutationFn: async (body) => parseResponse(planRowSchema, await api.patch<unknown>(planPath(id), { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PLANS_QUERY_KEY });
    },
  });
}

export interface SetPlanActiveVariables {
  id: string;
  active: boolean;
}

/** POST /plans/{id}/activate o /deactivate. */
export function useSetPlanActive(): UseMutationResult<PlanRowView, Error, SetPlanActiveVariables> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<PlanRowView, Error, SetPlanActiveVariables>({
    mutationFn: async ({ id, active }) => parseResponse(planRowSchema, await api.post<unknown>(`${planPath(id)}/${active ? "activate" : "deactivate"}`)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PLANS_QUERY_KEY });
    },
  });
}

/** DELETE /plans/{id} → 204 sin cuerpo. */
export function useDeletePlan(): UseMutationResult<undefined, Error, string> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<undefined, Error, string>({
    mutationFn: async (id) => {
      await api.delete<unknown>(planPath(id));
      return undefined;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PLANS_QUERY_KEY });
    },
  });
}

// S2-F7 · US-078 y US-079 (front): datos de planes (contrato de B9).
// - usePlans(params), PlansParams, plansQueryKey y PLANS_QUERY_KEY viven desde S3-F3 en
//   shared/data/plans.ts (S3-D65: los usa también la venta de membresías) y se reexportan aquí.
// - usePlan(id): GET /plans/{id} con la clave ["plans", "detail", id]; sin id no pide nada. El 403
//   (el coach sobre un plan inactivo, S2-D26) y el 404 no se reintentan (shouldRetry del cliente).
// - useCreatePlan(): POST /plans → 201 PlanOut. Al salir bien invalida ["plans"] (lista y
//   detalles). Los errores llegan como ApiError (409 con `existingId`, 422 con `field`) y los
//   traduce planErrors.ts.
import { useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";
import { api } from "../../core/api/client";
import { parseResponse } from "../../core/api/response";
import { PLANS_QUERY_KEY } from "../../shared/data/plans";
import { planRowSchema, type PlanCreateBody, type PlanRowView } from "./schemas";

export { PLANS_QUERY_KEY, plansQueryKey, usePlans, type PlansParams } from "../../shared/data/plans";

export function planQueryKey(id: string): readonly ["plans", "detail", string] {
  return ["plans", "detail", id];
}

export function usePlan(id: string | null): UseQueryResult<PlanRowView> {
  return useQuery({
    queryKey: planQueryKey(id ?? ""),
    queryFn: async ({ signal }) => parseResponse(planRowSchema, await api.get<unknown>(`/plans/${encodeURIComponent(id ?? "")}`, { signal })),
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

// S2-F7 · US-078 y US-079 (front): datos de planes (contrato de B9).
// - usePlans(params): GET /plans con la clave ["plans", params]; la página se valida con Zod (una
//   forma inesperada es `invalid_response`). Usa el `signal` de TanStack Query: al cambiar la
//   búsqueda, la anterior se cancela. `q` viaja solo en la petición (nunca en la URL de la app,
//   S2-D41) y mientras llega la página nueva se conserva la anterior.
// - usePlan(id): GET /plans/{id} con la clave ["plans", "detail", id]; sin id no pide nada. El 403
//   (el coach sobre un plan inactivo, S2-D26) y el 404 no se reintentan (shouldRetry del cliente).
// - useCreatePlan(): POST /plans → 201 PlanOut. Al salir bien invalida ["plans"] (lista y
//   detalles). Los errores llegan como ApiError (409 con `existingId`, 422 con `field`) y los
//   traduce planErrors.ts.
import { keepPreviousData, useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";
import { api } from "../../core/api/client";
import { ApiError } from "../../core/api/errors";
import type { Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { INVALID_RESPONSE_MESSAGE } from "./planErrors";
import { planRowSchema, plansPageSchema, type PlanCreateBody, type PlanRowView } from "./schemas";

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

export function planQueryKey(id: string): readonly ["plans", "detail", string] {
  return ["plans", "detail", id];
}

function invalidResponse(): ApiError {
  return new ApiError({ status: 0, code: "invalid_response", message: INVALID_RESPONSE_MESSAGE });
}

function parsePlan(body: unknown): PlanRowView {
  const parsed = planRowSchema.safeParse(body);
  if (!parsed.success) throw invalidResponse();
  return parsed.data;
}

export function usePlans(params: PlansParams): UseQueryResult<Page<PlanRowView>> {
  return useQuery({
    queryKey: plansQueryKey(params),
    queryFn: async ({ signal }) => {
      const parsed = plansPageSchema.safeParse(await api.get<unknown>("/plans", { query: listParams({ ...params }), signal }));
      if (!parsed.success) throw invalidResponse();
      return parsed.data;
    },
    placeholderData: keepPreviousData,
  });
}

export function usePlan(id: string | null): UseQueryResult<PlanRowView> {
  return useQuery({
    queryKey: planQueryKey(id ?? ""),
    queryFn: async ({ signal }) => parsePlan(await api.get<unknown>(`/plans/${encodeURIComponent(id ?? "")}`, { signal })),
    enabled: Boolean(id),
  });
}

export function useCreatePlan(): UseMutationResult<PlanRowView, Error, PlanCreateBody> {
  const queryClient = useQueryClient();
  return useMutation<PlanRowView, Error, PlanCreateBody>({
    mutationFn: async (body) => parsePlan(await api.post<unknown>("/plans", { body })),
    onSuccess: () => {
      // Sin esperar la relectura: el panel se cierra enseguida y la lista se actualiza sola.
      void queryClient.invalidateQueries({ queryKey: PLANS_QUERY_KEY });
    },
  });
}

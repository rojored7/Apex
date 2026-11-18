// S9-F1 (US-178, US-179, US-184): datos de la pestaña Atleta.
// - useAthleteSummary: GET /athletes/{id}/summary (conteos y tres récords vigentes; ninguna medida).
// - useMetrics: GET /athletes/{id}/metrics?limit&offset (solo `has_*`, paginada en el servidor).
// - useAddMetric / useVoidMetric: escrituras con useSensitiveMutation; al terminar bien relee todo lo del atleta (invalidateAthleteViews).
// - useRevealMetric: POST .../metrics/{id}/reveal con UN campo. El valor en claro lo recibe solo quien llama (MetricField); la mutación
//   no lo deja en la caché de TanStack (gcTime 0 y reset() de useSensitiveMutation) y nunca va en una clave ni en la URL (L-7).
import { keepPreviousData, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";
import { api } from "../../core/api/client";
import { API_ERROR_CODES } from "../../core/api/errorCodes";
import { isApiError } from "../../core/api/errors";
import { HTTP_NOT_FOUND } from "../../core/api/status";
import { pageSchema, type Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { invalidResponseError, parseResponse } from "../../core/api/response";
import { useSensitiveMutation } from "../../core/api/useSensitiveMutation";
import { invalidateAthleteViews } from "../../shared/data/athletes";
import { athleteSummarySchema, isRevealValueFor, metricRevealSchema, metricSchema, type AthleteSummaryView, type MetricCreate, type MetricFieldName, type MetricView } from "./schemas";

export interface MetricsParams {
  limit: number;
  offset: number;
}

const base = (memberId: string): string => `/athletes/${encodeURIComponent(memberId)}`;

export function useAthleteSummary(memberId: string): UseQueryResult<AthleteSummaryView> {
  return useQuery({
    queryKey: ["athlete-summary", memberId],
    queryFn: async ({ signal }) => parseResponse(athleteSummarySchema, await api.get<unknown>(`${base(memberId)}/summary`, { signal })),
    enabled: memberId !== "",
  });
}

export function useMetrics(memberId: string, params: MetricsParams): UseQueryResult<Page<MetricView>> {
  return useQuery({
    queryKey: ["athlete-metrics", memberId, params],
    queryFn: async ({ signal }) => parseResponse(pageSchema(metricSchema), await api.get<unknown>(`${base(memberId)}/metrics`, { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
    enabled: memberId !== "",
  });
}

export function useAddMetric(memberId: string): UseMutationResult<MetricView, Error, MetricCreate> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<MetricView, Error, MetricCreate>({
    mutationFn: async (body) => parseResponse(metricSchema, await api.post<unknown>(`${base(memberId)}/metrics`, { body })),
    onSuccess: () => {
      invalidateAthleteViews(queryClient);
    },
  });
}

export function useVoidMetric(memberId: string): UseMutationResult<MetricView, Error, string> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<MetricView, Error, string>({
    mutationFn: async (metricId) => {
      try {
        return parseResponse(metricSchema, await api.post<unknown>(`${base(memberId)}/metrics/${encodeURIComponent(metricId)}/void`));
      } catch (error) {
        // Ya estaba anulada o ya no existe: la lista que se ve quedó vieja y los mensajes prometen actualizarla.
        if (isApiError(error) && (error.code === API_ERROR_CODES.metricAlreadyVoided || error.status === HTTP_NOT_FOUND)) invalidateAthleteViews(queryClient);
        throw error;
      }
    },
    onSuccess: () => {
      invalidateAthleteViews(queryClient);
    },
  });
}

export interface RevealMetricVariables {
  metricId: string;
  field: MetricFieldName;
  /** Cancela el POST si quien lo pidió se desmonta antes de la respuesta (el claro no llega a nadie). */
  signal?: AbortSignal;
}

/** POST .../metrics/{id}/reveal: devuelve el valor en claro de UN campo (`null` si está vacío). */
export function useRevealMetric(memberId: string): UseMutationResult<number | string | null, Error, RevealMetricVariables> {
  return useSensitiveMutation<number | string | null, Error, RevealMetricVariables>({
    mutationFn: async ({ metricId, field, signal }) => {
      const reply = parseResponse(metricRevealSchema, await api.post<unknown>(`${base(memberId)}/metrics/${encodeURIComponent(metricId)}/reveal`, { body: { field }, ...(signal ? { signal } : {}) }));
      // El campo y el tipo de la respuesta tienen que ser los pedidos: otra cosa no se muestra.
      if (reply.field !== field || !isRevealValueFor(field, reply.value)) throw invalidResponseError();
      return reply.value;
    },
  });
}

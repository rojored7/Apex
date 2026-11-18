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
import { invalidateAthleteViews, invalidateRecordViews } from "../../shared/data/athletes";
import { isStaleRecordError } from "./recordErrors";
import {
  athleteSummarySchema,
  isRevealValueFor,
  metricRevealSchema,
  metricSchema,
  recordSchema,
  rmSchema,
  type AthleteSummaryView,
  type MetricCreate,
  type MetricFieldName,
  type MetricView,
  type RecordCreate,
  type RecordView,
  type RmView,
} from "./schemas";

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

export interface RmsParams {
  limit: number;
  offset: number;
}

export interface RecordsParams {
  limit: number;
  offset: number;
  kind?: "rm" | "benchmark";
  include_invalidated?: boolean;
}

// S9-F2 (US-180 a US-182): RMs y récords. Las claves ["athlete-rms", id, ...] y ["athlete-records", id, ...] son las que relee
// invalidateAthleteViews al guardar o anular un resultado.
export function useRms(memberId: string, params: RmsParams): UseQueryResult<Page<RmView>> {
  return useQuery({
    queryKey: ["athlete-rms", memberId, params],
    queryFn: async ({ signal }) => parseResponse(pageSchema(rmSchema), await api.get<unknown>(`${base(memberId)}/rms`, { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
    enabled: memberId !== "",
  });
}

export function useRecords(memberId: string, params: RecordsParams): UseQueryResult<Page<RecordView>> {
  return useQuery({
    queryKey: ["athlete-records", memberId, params],
    queryFn: async ({ signal }) => parseResponse(pageSchema(recordSchema), await api.get<unknown>(`${base(memberId)}/records`, { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
    enabled: memberId !== "",
  });
}

export function useAddRecord(memberId: string): UseMutationResult<RecordView, Error, RecordCreate> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<RecordView, Error, RecordCreate>({
    mutationFn: async (body) => parseResponse(recordSchema, await api.post<unknown>(`${base(memberId)}/records`, { body })),
    onSuccess: () => {
      invalidateRecordViews(queryClient, memberId);
    },
  });
}

export function useInvalidateRecord(memberId: string): UseMutationResult<RecordView, Error, string> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<RecordView, Error, string>({
    mutationFn: async (recordId) => {
      try {
        return parseResponse(recordSchema, await api.post<unknown>(`${base(memberId)}/records/${encodeURIComponent(recordId)}/invalidate`));
      } catch (error) {
        // Ya no se puede invalidar (derivado, ya invalidado o inexistente): la lista que se ve quedó vieja y los mensajes prometen actualizarla.
        if (isStaleRecordError(error)) invalidateRecordViews(queryClient, memberId);
        throw error;
      }
    },
    onSuccess: () => {
      invalidateRecordViews(queryClient, memberId);
    },
  });
}

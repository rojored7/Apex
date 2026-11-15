// S8-F2 · US-166 y US-167 (front): datos de los WODs (contrato de A3).
// - useWods(params): GET /wods paginado (`week` para el calendario; `q` y `benchmark` para la lista).
// - useWod(id): GET /wods/{id}. useCreateWod y useUpdateWod(id): al salir bien invalidan las listas y el detalle.
import { keepPreviousData, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";
import { api } from "../../core/api/client";
import { pageSchema, type Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import { useSensitiveMutation } from "../../core/api/useSensitiveMutation";
import { wodRowSchema, wodSchema, type WodCreateBody, type WodPatchBody, type WodRowView, type WodView } from "./wodSchemas";

const wodsPageSchema = pageSchema(wodRowSchema);

export const WODS_QUERY_KEY = ["wods"] as const;
export const WOD_QUERY_KEY = ["wod"] as const;

export interface WodsParams {
  limit: number;
  offset: number;
  week?: string;
  q?: string;
  benchmark?: boolean;
}

const wodPath = (id: string): string => `/wods/${encodeURIComponent(id)}`;

export function useWods(params: WodsParams): UseQueryResult<Page<WodRowView>> {
  return useQuery({
    queryKey: [...WODS_QUERY_KEY, params],
    queryFn: async ({ signal }) => parseResponse(wodsPageSchema, await api.get<unknown>("/wods", { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
  });
}

export function useWod(id: string | undefined): UseQueryResult<WodView> {
  return useQuery({
    queryKey: [...WOD_QUERY_KEY, id],
    queryFn: async ({ signal }) => parseResponse(wodSchema, await api.get<unknown>(wodPath(id ?? ""), { signal })),
    enabled: id !== undefined,
  });
}

export function useCreateWod(): UseMutationResult<WodView, Error, WodCreateBody> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<WodView, Error, WodCreateBody>({
    mutationFn: async (body) => parseResponse(wodSchema, await api.post<unknown>("/wods", { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: WODS_QUERY_KEY });
    },
  });
}

export function useUpdateWod(id: string): UseMutationResult<WodView, Error, WodPatchBody> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<WodView, Error, WodPatchBody>({
    mutationFn: async (body) => parseResponse(wodSchema, await api.patch<unknown>(wodPath(id), { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: WODS_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: [...WOD_QUERY_KEY, id] });
    },
  });
}

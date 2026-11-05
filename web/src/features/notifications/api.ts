// S5-F1 · US-127 a US-129 (front): datos de "Por avisar hoy" (contrato de B7).
// - useToday(params): GET /notifications/today con la clave ["notifications", "today", params], la
//   página validada con Zod y la anterior mientras llega la nueva (keepPreviousData).
// - useWaLink(): POST /notifications/{id}/wa-link por useSensitiveMutation (gcTime 0 y reset() al
//   terminar, S5-D59, M-9): la respuesta lleva el teléfono dentro de la URL y no queda en ninguna
//   caché. Solo se acepta un enlace https://wa.me/. Al terminar relee ["notifications"], también
//   si falla con 404 o 409 (el aviso cambió); un 401, 403 o 429 no relee (S5-D244).
// - useSkip(): POST /notifications/{id}/skip {reason}; el motivo se valida y recorta antes de salir.
import { keepPreviousData, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";
import { api } from "../../core/api/client";
import { API_ERROR_CODES } from "../../core/api/errorCodes";
import { ApiError, isApiError } from "../../core/api/errors";
import type { Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import { HTTP_CONFLICT, HTTP_NOT_FOUND } from "../../core/api/status";
import { useSensitiveMutation } from "../../core/api/useSensitiveMutation";
import { notificationRowSchema, notificationsPageSchema, skipBodySchema, waLinkSchema, type NotificationRowView, type WaLinkView } from "./schemas";

export const NOTIFICATIONS_QUERY_KEY = ["notifications"] as const;

export interface TodayParams {
  limit: number;
  offset: number;
}

export function todayQueryKey(params: TodayParams): readonly ["notifications", "today", TodayParams] {
  return ["notifications", "today", params];
}

/** S5-D244: solo un 404 o un 409 quiere decir que lo que se ve quedó viejo; 401, 403, 429 y 5xx no releen. */
function refreshIfStale(refresh: () => void): (error: Error) => void {
  return (error) => {
    if (isApiError(error) && (error.status === HTTP_NOT_FOUND || error.status === HTTP_CONFLICT)) refresh();
  };
}

const notificationPath = (id: string): string => `/notifications/${encodeURIComponent(id)}`;

export function useToday(params: TodayParams): UseQueryResult<Page<NotificationRowView>> {
  return useQuery({
    queryKey: todayQueryKey(params),
    queryFn: async ({ signal }) => parseResponse(notificationsPageSchema, await api.get<unknown>("/notifications/today", { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
  });
}

export function useWaLink(): UseMutationResult<WaLinkView, Error, string> {
  const queryClient = useQueryClient();
  const refresh = (): void => {
    void queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
  };
  return useSensitiveMutation<WaLinkView, Error, string>({
    mutationFn: async (id) => parseResponse(waLinkSchema, await api.post<unknown>(`${notificationPath(id)}/wa-link`)),
    onSuccess: refresh,
    onError: refreshIfStale(refresh),
  });
}

export interface SkipVariables {
  id: string;
  reason: string;
}

export function useSkip(): UseMutationResult<NotificationRowView, Error, SkipVariables> {
  const queryClient = useQueryClient();
  const refresh = (): void => {
    void queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
  };
  return useSensitiveMutation<NotificationRowView, Error, SkipVariables>({
    mutationFn: async ({ id, reason }) => {
      const body = skipBodySchema.safeParse({ reason });
      if (!body.success) throw new ApiError({ status: 422, code: API_ERROR_CODES.validationError, field: "reason", message: "El motivo debe tener entre 3 y 500 caracteres." });
      return parseResponse(notificationRowSchema, await api.post<unknown>(`${notificationPath(id)}/skip`, { body: body.data }));
    },
    onSuccess: refresh,
    onError: refreshIfStale(refresh),
  });
}

// S8-F3 · S8-D27 (front): datos de resultados que comparten `wods` y `results` (una feature nunca importa de otra).
// - useLeaderboard: GET /wods/{id}/leaderboard?level&sex&limit&offset (la posición la calcula el servidor, empates 1-2-2-4).
// - useWodResults: GET /wods/{id}/results?include_superseded (todos los resultados, con quién y cuándo).
// - useWodSessions: GET /class-sessions?wod_id (las sesiones que usan el WOD).
// - useVoidResult: POST /results/{id}/void (solo admin, S8-D46 b); el motivo no queda en la caché de mutaciones.
import { keepPreviousData, useQuery, useQueryClient, type QueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../../core/api/client";
import { pageSchema, type Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import { useSensitiveMutation } from "../../core/api/useSensitiveMutation";
import { invalidateAthleteViews } from "./athletes";

export const RESULT_LEVELS = ["rx", "rx_plus", "scaled"] as const;
export type ResultLevel = (typeof RESULT_LEVELS)[number];
export type ResultSex = "f" | "m";

export const LEVEL_LABELS: Readonly<Record<ResultLevel, string>> = { rx: "RX", rx_plus: "RX+", scaled: "Escalado" };

const marks = {
  seconds: z.number().int().nullable(),
  rounds: z.number().int().nullable(),
  reps: z.number().int().nullable(),
  load_g: z.number().int().nullable(),
  capped: z.boolean(),
};

export const leaderboardRowSchema = z.object({
  position: z.number().int(),
  result_id: z.string().min(1),
  member_id: z.string().min(1),
  first_name: z.string(),
  last_initial: z.string(),
  level: z.enum(RESULT_LEVELS),
  ...marks,
});
export type LeaderboardRowView = z.infer<typeof leaderboardRowSchema>;

export const wodResultRowSchema = z.object({
  id: z.string().min(1),
  member_id: z.string().min(1),
  first_name: z.string(),
  last_name: z.string(),
  level: z.enum(RESULT_LEVELS),
  ...marks,
  is_current: z.boolean(),
  status: z.enum(["validated", "pending", "voided"]),
  source: z.enum(["desk", "kiosk"]),
  recorded_by: z.string(),
  recorded_by_name: z.string().nullable(),
  created_at: z.string(),
  session_id: z.string().nullable(),
  supersedes_id: z.string().nullable(),
});
export type WodResultRowView = z.infer<typeof wodResultRowSchema>;

export const wodSessionSchema = z.object({
  id: z.string().min(1),
  session_date: z.string(),
  starts_at: z.string(),
  coach_name: z.string().nullable(),
  name: z.string().nullable(),
  status: z.enum(["scheduled", "cancelled", "done"]),
  attendance_count: z.number().int().nonnegative(),
  capacity: z.number().int(),
});
export type WodSessionView = z.infer<typeof wodSessionSchema>;

export const LEADERBOARD_QUERY_KEY = ["wod-leaderboard"] as const;
export const WOD_RESULTS_QUERY_KEY = ["wod-results"] as const;

/** Todo lo que muestra un resultado: ranking, lista, WODs, ficha del socio, tablet de la clase y el WOD de hoy de Inicio (M-5). */
const RESULT_VIEW_KEYS = [["wod-leaderboard"], ["wod-results"], ["wods"], ["wod"], ["member-results"], ["session-results"], ["dashboard"]] as const;

/** Guardar o anular un resultado relee todas las vistas que lo muestran (también las del atleta, S9-F1). */
export function invalidateResultViews(queryClient: QueryClient): void {
  for (const queryKey of RESULT_VIEW_KEYS) void queryClient.invalidateQueries({ queryKey });
  // S9-F1: un resultado derivado deja un RM o un récord nuevo; la pestaña Atleta lo relee.
  invalidateAthleteViews(queryClient);
}
export const WOD_SESSIONS_QUERY_KEY = ["wod-sessions"] as const;

export interface LeaderboardParams {
  limit: number;
  offset: number;
  level?: ResultLevel;
  sex?: ResultSex;
}

export interface WodResultsParams {
  limit: number;
  offset: number;
  includeSuperseded: boolean;
}

const wodPath = (id: string): string => `/wods/${encodeURIComponent(id)}`;

export function useLeaderboard(wodId: string, params: LeaderboardParams): UseQueryResult<Page<LeaderboardRowView>> {
  return useQuery({
    queryKey: [...LEADERBOARD_QUERY_KEY, wodId, params],
    queryFn: async ({ signal }) =>
      parseResponse(pageSchema(leaderboardRowSchema), await api.get<unknown>(`${wodPath(wodId)}/leaderboard`, { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
    enabled: wodId !== "",
  });
}

export function useWodResults(wodId: string, params: WodResultsParams): UseQueryResult<Page<WodResultRowView>> {
  const { includeSuperseded, ...paging } = params;
  return useQuery({
    queryKey: [...WOD_RESULTS_QUERY_KEY, wodId, params],
    queryFn: async ({ signal }) =>
      parseResponse(
        pageSchema(wodResultRowSchema),
        await api.get<unknown>(`${wodPath(wodId)}/results`, { query: listParams({ ...paging, ...(includeSuperseded ? { include_superseded: true } : {}) }), signal }),
      ),
    placeholderData: keepPreviousData,
    enabled: wodId !== "",
  });
}

export interface WodSessionsParams {
  limit: number;
  offset: number;
  /** Ventana de fechas civiles (AAAA-MM-DD, Bogotá): el api exige `from` y `to` juntos (máx. 62 días); sin ellas, las del día del WOD. */
  from?: string;
  to?: string;
}

export function useWodSessions(wodId: string, params: WodSessionsParams): UseQueryResult<Page<WodSessionView>> {
  return useQuery({
    queryKey: [...WOD_SESSIONS_QUERY_KEY, wodId, params],
    queryFn: async ({ signal }) =>
      parseResponse(pageSchema(wodSessionSchema), await api.get<unknown>("/class-sessions", { query: listParams({ ...params, wod_id: wodId }), signal })),
    placeholderData: keepPreviousData,
    enabled: wodId !== "",
  });
}

export interface VoidResultVariables {
  id: string;
  reason: string;
}

const voidedSchema = z.object({ id: z.string().min(1) });

/** POST /results/{id}/void: la marca queda en la auditoría; el leaderboard y la lista se releen. */
export function useVoidResult(): UseMutationResult<null, Error, VoidResultVariables> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<null, Error, VoidResultVariables>({
    mutationFn: async ({ id, reason }) => {
      parseResponse(voidedSchema, await api.post<unknown>(`/results/${encodeURIComponent(id)}/void`, { body: { reason } }));
      return null;
    },
    onSuccess: () => {
      invalidateResultViews(queryClient);
    },
  });
}

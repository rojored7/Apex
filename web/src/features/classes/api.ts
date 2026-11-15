// S7-F2 · US-155 y US-158 (front): datos de franjas (contrato de A2 y B3). Toda respuesta se valida con Zod.
// - useSlots(params): GET /class-slots con la clave ["class-slots", params]; mientras llega la página nueva se ve la anterior.
// - useCreateSlot(): POST /class-slots → 201 SlotOut. useUpdateSlot(id): PATCH /class-slots/{id} con solo lo cambiado.
// - useCancelFutureSessions(): POST /class-slots/{id}/cancel-future-sessions con el motivo → { cancelled_count }.
//   Las escrituras pasan por useSensitiveMutation (el motivo no queda en la caché de mutaciones).
// - useCoachCandidates(enabled): GET /users activos (solo admin) y se quedan admin y coach; son los que el api acepta
//   como coach de una franja (S7-D7). El socio nunca aparece.
import { keepPreviousData, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../../core/api/client";
import { pageSchema, type Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import { useSensitiveMutation } from "../../core/api/useSensitiveMutation";
import { hhmm, type SessionCreateBody, type SlotCreateBody, type SlotPatchBody } from "./schemas";

export const slotSchema = z.object({
  id: z.string().min(1),
  name: z.string().nullable(),
  weekdays: z.array(z.number().int().min(0).max(6)),
  start_time: z.string().regex(/^\d{2}:\d{2}(:\d{2})?$/).transform(hhmm),
  duration_min: z.number().int(),
  capacity: z.number().int(),
  default_coach_id: z.string().nullable(),
  coach_name: z.string().nullable(),
  valid_from: z.string(),
  is_active: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type SlotView = z.infer<typeof slotSchema>;

export const slotsPageSchema = pageSchema(slotSchema);

export interface SlotsParams {
  limit: number;
  offset: number;
}

export const SLOTS_QUERY_KEY = ["class-slots"] as const;
/** Las sesiones dependen de las franjas (cancelar sesiones futuras las cambia). */
export const SESSIONS_QUERY_KEY = ["class-sessions"] as const;

export function slotsQueryKey(params: SlotsParams): readonly ["class-slots", SlotsParams] {
  return ["class-slots", params];
}

const slotPath = (id: string): string => `/class-slots/${encodeURIComponent(id)}`;

export function useSlots(params: SlotsParams, enabled = true): UseQueryResult<Page<SlotView>> {
  return useQuery({
    queryKey: slotsQueryKey(params),
    queryFn: async ({ signal }) => parseResponse(slotsPageSchema, await api.get<unknown>("/class-slots", { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useCreateSlot(): UseMutationResult<SlotView, Error, SlotCreateBody> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<SlotView, Error, SlotCreateBody>({
    mutationFn: async (body) => parseResponse(slotSchema, await api.post<unknown>("/class-slots", { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SLOTS_QUERY_KEY });
    },
  });
}

export function useUpdateSlot(id: string): UseMutationResult<SlotView, Error, SlotPatchBody> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<SlotView, Error, SlotPatchBody>({
    mutationFn: async (body) => parseResponse(slotSchema, await api.patch<unknown>(slotPath(id), { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SLOTS_QUERY_KEY });
    },
  });
}

const cancelFutureSchema = z.object({ cancelled_count: z.number().int().nonnegative() });

export interface CancelFutureVariables {
  id: string;
  reason: string;
}

/** POST /class-slots/{id}/cancel-future-sessions → cuántas sesiones se cancelaron. */
export function useCancelFutureSessions(): UseMutationResult<number, Error, CancelFutureVariables> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<number, Error, CancelFutureVariables>({
    mutationFn: async ({ id, reason }) => parseResponse(cancelFutureSchema, await api.post<unknown>(`${slotPath(id)}/cancel-future-sessions`, { body: { reason } })).cancelled_count,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SESSIONS_QUERY_KEY });
    },
  });
}

const coachUserSchema = z.object({
  id: z.string().min(1),
  email: z.string().min(1),
  status: z.string(),
});
export type CoachCandidate = Pick<z.infer<typeof coachUserSchema>, "id" | "email">;

const COACH_CANDIDATES_LIMIT = 200;
const COACH_ROLES = ["admin", "coach"] as const;

/** Admins y coaches activos, por correo (la lista de usuarios no trae nombre). Solo el admin puede leerla. */
export function useCoachCandidates(enabled: boolean): UseQueryResult<CoachCandidate[]> {
  return useQuery({
    queryKey: ["class-coaches"],
    queryFn: async ({ signal }) => {
      // El servidor filtra por rol y estado: una consulta por cada rol que el api acepta como coach de clases (S7-D7).
      const byRole = await Promise.all(
        COACH_ROLES.map(async (role) =>
          parseResponse(pageSchema(coachUserSchema), await api.get<unknown>("/users", { query: listParams({ limit: COACH_CANDIDATES_LIMIT, offset: 0, status: "active", role }), signal })),
        ),
      );
      const unique = new Map(byRole.flatMap((page) => page.items).map(({ id, email }) => [id, { id, email }] as const));
      return [...unique.values()].sort((x, y) => x.email.localeCompare(y.email, "es"));
    },
    enabled,
  });
}

// S7-F3 · US-157: sesiones de una semana (GET /class-sessions?week), sesión extra (POST) y cancelar (POST .../cancel).
// Crear o cancelar invalida todas las semanas leídas.
export const sessionSchema = z.object({
  id: z.string().min(1),
  slot_id: z.string().nullable(),
  session_date: z.string(),
  starts_at: z.string(),
  duration_min: z.number().int(),
  capacity: z.number().int(),
  coach_id: z.string().nullable(),
  coach_name: z.string().nullable(),
  name: z.string().nullable(),
  status: z.enum(["scheduled", "cancelled", "done"]),
  attendance_count: z.number().int().nonnegative(),
  cancel_reason: z.string().nullable(),
  cancelled_at: z.string().nullable(),
});
export type SessionView = z.infer<typeof sessionSchema>;

export const sessionsPageSchema = pageSchema(sessionSchema);

/** Una semana de un gimnasio cabe en una página (el api topa en 200); si no, la pantalla lo avisa. */
export const WEEK_SESSIONS_LIMIT = 200;

export function sessionsQueryKey(week: string): readonly ["class-sessions", { week: string }] {
  return ["class-sessions", { week }];
}

export function useSessions(week: string, enabled = true): UseQueryResult<Page<SessionView>> {
  return useQuery({
    queryKey: sessionsQueryKey(week),
    queryFn: async ({ signal }) => parseResponse(sessionsPageSchema, await api.get<unknown>("/class-sessions", { query: listParams({ limit: WEEK_SESSIONS_LIMIT, offset: 0, week }), signal })),
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** POST /class-sessions: sesión extra (sin franja). */
export function useCreateSession(): UseMutationResult<SessionView, Error, SessionCreateBody> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<SessionView, Error, SessionCreateBody>({
    mutationFn: async (body) => parseResponse(sessionSchema, await api.post<unknown>("/class-sessions", { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SESSIONS_QUERY_KEY });
    },
  });
}

export interface CancelSessionVariables {
  id: string;
  reason: string;
}

/** POST /class-sessions/{id}/cancel con el motivo. */
export function useCancelSession(): UseMutationResult<SessionView, Error, CancelSessionVariables> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<SessionView, Error, CancelSessionVariables>({
    mutationFn: async ({ id, reason }) => parseResponse(sessionSchema, await api.post<unknown>(`/class-sessions/${encodeURIComponent(id)}/cancel`, { body: { reason } })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SESSIONS_QUERY_KEY });
    },
  });
}

// S7-F5 · US-162 (front): lecturas de asistencia. Toda respuesta se valida con Zod.
// - useAttendance(params): GET /attendance (admin y coach) con la clave ["attendance", "list", params]; mientras llega la página
//   nueva se ve la anterior. `from` y `to` van en UTC y `to` es exclusivo ([from, to)); `q` nunca llega a la URL de la app.
// - useAttendanceSummary(from, to): GET /attendance/summary con días civiles de Bogotá (hasta 26 semanas) y una entrada por semana.
// - useMemberAttendance(id, params): GET /members/{id}/attendance paginado (pestaña de la ficha; no pide `q`, que no aporta ahí).
// - useMemberAttendanceStats(id, fromUtc): la última asistencia (GET /attendance?member_id&limit=1) y el total de los últimos
//   30 días (el mismo con `from`); el `total` de la página es el conteo, así no se traen filas de más.
// - Registrar o quitar una asistencia invalida ["attendance"] (ATTENDANCE_QUERY_KEY).
import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../../core/api/client";
import { pageSchema, type Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";

export const ATTENDANCE_QUERY_KEY = ["attendance"] as const;

export const attendanceRowSchema = z.object({
  id: z.string().min(1),
  member_id: z.string().min(1),
  first_name: z.string().nullable(),
  last_name: z.string().nullable(),
  session_id: z.string().min(1),
  session_date: z.string(),
  session_starts_at: z.string(),
  checked_in_at: z.string(),
  flagged: z.boolean(),
  flags: z.array(z.string()),
  membership_status_at_checkin: z.string(),
});
export type AttendanceRowView = z.infer<typeof attendanceRowSchema>;

export const attendancePageSchema = pageSchema(attendanceRowSchema);

const slotBucketSchema = z.object({
  slot_id: z.string().nullable(),
  label: z.string(),
  start_time: z.string().nullable(),
  sessions: z.number().int().nonnegative(),
  attendance: z.number().int().nonnegative(),
  capacity_sum: z.number().int().nonnegative(),
  occupancy_pct: z.number().int().nonnegative(),
  flagged: z.number().int().nonnegative(),
});
export type SlotBucketView = z.infer<typeof slotBucketSchema>;

const weekBucketSchema = z.object({
  week: z.string().min(1),
  week_start: z.string(),
  total: z.number().int().nonnegative(),
  flagged: z.number().int().nonnegative(),
  slots: z.array(slotBucketSchema),
});
export type WeekBucketView = z.infer<typeof weekBucketSchema>;

export const attendanceSummarySchema = z.object({ weeks: z.array(weekBucketSchema) });

export interface AttendanceParams {
  limit: number;
  offset: number;
  /** Instante UTC (incluido). */
  from?: string;
  /** Instante UTC (excluido). */
  to?: string;
  flagged?: boolean;
  q?: string;
  member_id?: string;
}

export function attendanceQueryKey(params: AttendanceParams): readonly ["attendance", "list", AttendanceParams] {
  return ["attendance", "list", params];
}

export function useAttendance(params: AttendanceParams, enabled = true): UseQueryResult<Page<AttendanceRowView>> {
  return useQuery({
    queryKey: attendanceQueryKey(params),
    queryFn: async ({ signal }) => parseResponse(attendancePageSchema, await api.get<unknown>("/attendance", { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export interface SummaryRange {
  /** Día civil de Bogotá, AAAA-MM-DD. */
  from: string;
  to: string;
}

export function useAttendanceSummary(range: SummaryRange, enabled = true): UseQueryResult<WeekBucketView[]> {
  return useQuery({
    queryKey: ["attendance", "summary", range],
    queryFn: async ({ signal }) => parseResponse(attendanceSummarySchema, await api.get<unknown>("/attendance/summary", { query: { from: range.from, to: range.to }, signal })).weeks,
    enabled,
  });
}

export interface MemberAttendanceParams {
  limit: number;
  offset: number;
}

export function useMemberAttendance(memberId: string, params: MemberAttendanceParams, enabled = true): UseQueryResult<Page<AttendanceRowView>> {
  return useQuery({
    queryKey: ["attendance", "member", memberId, params],
    queryFn: async ({ signal }) =>
      parseResponse(attendancePageSchema, await api.get<unknown>(`/members/${encodeURIComponent(memberId)}/attendance`, { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export interface MemberAttendanceStats {
  last: UseQueryResult<{ lastAt: string | null; total: number }>;
  recent: UseQueryResult<number>;
}

/** La última asistencia del socio (con su total de siempre) y cuántas lleva desde `fromUtc`. */
export function useMemberAttendanceStats(memberId: string, fromUtc: string, enabled = true): MemberAttendanceStats {
  const one = async (extra: Partial<AttendanceParams>, signal: AbortSignal): Promise<Page<AttendanceRowView>> =>
    parseResponse(attendancePageSchema, await api.get<unknown>("/attendance", { query: listParams({ limit: 1, offset: 0, member_id: memberId, ...extra }), signal }));
  const last = useQuery({
    queryKey: ["attendance", "member-last", memberId],
    queryFn: async ({ signal }) => {
      const page = await one({}, signal);
      return { lastAt: page.items[0]?.checked_in_at ?? null, total: page.total };
    },
    enabled,
  });
  const recent = useQuery({
    queryKey: ["attendance", "member-recent", memberId, fromUtc],
    queryFn: async ({ signal }) => (await one({ from: fromUtc }, signal)).total,
    enabled,
  });
  return { last, recent };
}

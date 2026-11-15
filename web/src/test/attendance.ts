// S7-F5: datos de prueba de la asistencia (GET /attendance, GET /attendance/summary, GET /members/{id}/attendance).
// Imitan AttendanceRowOut, AttendanceSummary, WeekBucket y SlotBucket del contrato (R1): nombre y apellido en claro, nunca nada cifrado.
import type { MockHandler, MockReply, RecordedCall } from "./server";

export const LAURA_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
export const JUAN_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

export interface AttendanceRowFixture {
  id: string;
  member_id: string;
  first_name: string | null;
  last_name: string | null;
  session_id: string;
  session_date: string;
  session_starts_at: string;
  checked_in_at: string;
  flagged: boolean;
  flags: string[];
  membership_status_at_checkin: string;
}

export function attendanceRow(id: string, memberId: string, first: string | null, last: string | null, startsAt: string, overrides: Partial<AttendanceRowFixture> = {}): AttendanceRowFixture {
  return {
    id,
    member_id: memberId,
    first_name: first,
    last_name: last,
    session_id: `s-${id}`,
    session_date: startsAt.slice(0, 10),
    session_starts_at: startsAt,
    checked_in_at: startsAt,
    flagged: false,
    flags: [],
    membership_status_at_checkin: "active",
    ...overrides,
  };
}

/** «Hoy» de las pruebas es mar 20 de oct de 2026, 10:00 a. m. en Bogotá (15:00 UTC). */
export const ATTENDANCE_NOW = new Date("2026-10-20T15:00:00Z");

export const ATTENDANCE_ROWS: AttendanceRowFixture[] = [
  attendanceRow("r1", LAURA_ID, "Laura", "Gómez", "2026-10-20T11:00:00Z", { checked_in_at: "2026-10-20T11:02:00Z" }),
  attendanceRow("r2", JUAN_ID, "Juan", "Pérez", "2026-10-19T23:00:00Z", {
    flagged: true,
    flags: ["expired", "other_day", "algo_nuevo"],
    membership_status_at_checkin: "expired",
    checked_in_at: "2026-10-19T23:05:00Z",
  }),
  attendanceRow("r3", LAURA_ID, "Laura", "Gómez", "2026-10-19T11:00:00Z", { flagged: true, flags: ["frozen"], membership_status_at_checkin: "frozen" }),
];

export function attendancePageReply(call: RecordedCall, rows: readonly unknown[] = ATTENDANCE_ROWS, total = rows.length): MockReply {
  const params = new URL(call.url, "http://apex.test").searchParams;
  return { status: 200, body: { items: rows, total, limit: Number(params.get("limit")), offset: Number(params.get("offset")) } };
}

import type { WeekBucketView } from "../features/classes/attendanceApi";

export interface SlotBucketFixture {
  slot_id: string | null;
  label: string;
  start_time: string | null;
  sessions: number;
  attendance: number;
  capacity_sum: number;
  occupancy_pct: number;
  flagged: number;
}

export const SLOT_BUCKETS: SlotBucketFixture[] = [
  { slot_id: "a1", label: "CrossFit", start_time: "06:00", sessions: 5, attendance: 45, capacity_sum: 60, occupancy_pct: 75, flagged: 2 },
  { slot_id: "a2", label: "Open box", start_time: "09:30", sessions: 1, attendance: 0, capacity_sum: 0, occupancy_pct: 0, flagged: 0 },
  { slot_id: null, label: "Extra", start_time: null, sessions: 1, attendance: 4, capacity_sum: 20, occupancy_pct: 20, flagged: 0 },
];

export const WEEK_BUCKETS: WeekBucketView[] = [
  { week: "2026-W42", week_start: "2026-10-12", total: 0, flagged: 0, slots: [] },
  { week: "2026-W43", week_start: "2026-10-19", total: 49, flagged: 2, slots: SLOT_BUCKETS },
];

export const summaryReply = (weeks: readonly unknown[] = WEEK_BUCKETS): MockReply => ({ status: 200, body: { weeks } });

export const handlersFor = (rows: readonly AttendanceRowFixture[] = ATTENDANCE_ROWS): Record<string, MockHandler> => ({
  "GET /attendance": (call) => attendancePageReply(call, rows),
  "GET /attendance/summary": summaryReply(),
});

/** Los parámetros de cada GET a `path`, en orden. */
export function paramsOf(mock: { callsTo: (key: string) => RecordedCall[] }, key: string): URLSearchParams[] {
  return mock.callsTo(key).map((call) => new URL(call.url, "http://apex.test").searchParams);
}

// S7-F2 y S7-F3: datos y montaje de prueba de Clases. Imitan SlotOut, SessionOut y UserRow del contrato (A2, B1 a B3).
import type { MockHandler, MockReply, RecordedCall } from "./server";

export const CARLOS_ID = "c0c0c0c0-0000-4000-8000-0000000000c1";
export const MARIA_ID = "c0c0c0c0-0000-4000-8000-0000000000c2";

export interface SlotFixture {
  id: string;
  name: string | null;
  weekdays: number[];
  start_time: string;
  duration_min: number;
  capacity: number;
  default_coach_id: string | null;
  coach_name: string | null;
  valid_from: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export function slot(id: string, overrides: Partial<SlotFixture> = {}): SlotFixture {
  return {
    id,
    name: null,
    weekdays: [0, 1, 2, 3, 4],
    start_time: "06:00",
    duration_min: 60,
    capacity: 12,
    default_coach_id: CARLOS_ID,
    coach_name: "Carlos",
    valid_from: "2026-10-01",
    is_active: true,
    created_at: "2026-10-01T15:00:00Z",
    updated_at: "2026-10-01T15:00:00Z",
    ...overrides,
  };
}

export const SLOTS = {
  manana: slot("a1a1a1a1-0000-4000-8000-000000000001", { name: "CrossFit" }),
  open: slot("a1a1a1a1-0000-4000-8000-000000000002", { weekdays: [5], start_time: "09:30", duration_min: 90, capacity: 20, default_coach_id: null, coach_name: null }),
  pausada: slot("a1a1a1a1-0000-4000-8000-000000000003", { weekdays: [0, 2, 4], start_time: "12:00", capacity: 8, is_active: false }),
} as const;

export const SLOT_ROWS: SlotFixture[] = [SLOTS.manana, SLOTS.open, SLOTS.pausada];

export const slotsPage = (rows: SlotFixture[] = SLOT_ROWS): MockReply => ({ status: 200, body: { items: rows, total: rows.length, limit: 25, offset: 0 } });

export const apiError = (status: number, code: string, extra: Record<string, unknown> = {}, headers?: Record<string, string>): MockReply => ({
  status,
  body: { error: { code, message: "Mensaje del api.", ...extra } },
  ...(headers ? { headers } : {}),
});

const user = (id: string, email: string, role: "admin" | "coach" | "member", status = "active") => ({
  id,
  email,
  role,
  status,
  member_id: null,
  active_sessions: 0,
  last_login_at: null,
  created_at: "2026-10-01T15:00:00Z",
});

export const USER_ROWS = [
  user(CARLOS_ID, "carlos@apex.test", "coach"),
  user(MARIA_ID, "maria@apex.test", "coach"),
  user("c0c0c0c0-0000-4000-8000-0000000000c3", "socio@apex.test", "member"),
];

/** GET /users como el api: filtra por `role` y `status` si vienen en la consulta. */
export const usersPage: MockHandler = (call: RecordedCall): MockReply => {
  const params = new URL(call.url, "http://apex.test").searchParams;
  const role = params.get("role");
  const items = USER_ROWS.filter((row) => (role === null || row.role === role) && (params.get("status") === null || row.status === params.get("status")));
  return { status: 200, body: { items, total: items.length, limit: 200, offset: 0 } };
};

export interface SessionFixture {
  id: string;
  slot_id: string | null;
  session_date: string;
  starts_at: string;
  duration_min: number;
  capacity: number;
  coach_id: string | null;
  coach_name: string | null;
  name: string | null;
  status: "scheduled" | "cancelled" | "done";
  attendance_count: number;
  cancel_reason: string | null;
  cancelled_at: string | null;
}

export function session(id: string, overrides: Partial<SessionFixture> = {}): SessionFixture {
  return {
    id,
    slot_id: SLOTS.manana.id,
    session_date: "2026-10-19",
    starts_at: "2026-10-19T11:00:00Z",
    duration_min: 60,
    capacity: 12,
    coach_id: CARLOS_ID,
    coach_name: "Carlos",
    name: null,
    status: "scheduled",
    attendance_count: 0,
    cancel_reason: null,
    cancelled_at: null,
    ...overrides,
  };
}

/** Semana 2026-W43: lun 19 a dom 25 de octubre; «hoy» es mar 20, 10:00 a. m. en Bogotá. */
export const WEEK = "2026-W43";
export const NOW = new Date("2026-10-20T15:00:00Z");

export const SESSIONS = {
  llena: session("e1e1e1e1-0000-4000-8000-000000000001", { attendance_count: 12 }),
  lunes7: session("e1e1e1e1-0000-4000-8000-000000000002", { starts_at: "2026-10-19T12:00:00Z", attendance_count: 9 }),
  hoy17: session("e1e1e1e1-0000-4000-8000-000000000003", { session_date: "2026-10-20", starts_at: "2026-10-20T22:00:00Z", coach_id: MARIA_ID, coach_name: "María", attendance_count: 3 }),
  cancelada: session("e1e1e1e1-0000-4000-8000-000000000004", {
    session_date: "2026-10-22",
    starts_at: "2026-10-22T22:00:00Z",
    coach_id: MARIA_ID,
    coach_name: "María",
    status: "cancelled",
    cancel_reason: "festivo",
    cancelled_at: "2026-10-15T15:00:00Z",
  }),
  open: session("e1e1e1e1-0000-4000-8000-000000000005", {
    slot_id: SLOTS.open.id,
    session_date: "2026-10-24",
    starts_at: "2026-10-24T14:30:00Z",
    duration_min: 90,
    capacity: 20,
    coach_id: null,
    coach_name: null,
  }),
} as const;

export const SESSION_ROWS: SessionFixture[] = [SESSIONS.llena, SESSIONS.lunes7, SESSIONS.hoy17, SESSIONS.cancelada, SESSIONS.open];

export const sessionsPage = (rows: SessionFixture[] = SESSION_ROWS): MockReply => ({ status: 200, body: { items: rows, total: rows.length, limit: 200, offset: 0 } });

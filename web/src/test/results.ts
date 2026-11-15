// S8-F4: datos de prueba de la tablet de resultados. Imitan SessionAttendanceOut y ResultOut del contrato (B3).
import { SESSIONS } from "./classes";
import type { MockReply } from "./server";

export const SESSION_ID = SESSIONS.hoy17.id;
export const WOD_ID = "f2f2f2f2-0000-4000-8000-0000000000aa";
export const MOV_KB = "d1d1d1d1-0000-4000-8000-0000000000b1";
export const MOV_PULL = "d1d1d1d1-0000-4000-8000-0000000000b2";
export const MOV_RUN = "d1d1d1d1-0000-4000-8000-0000000000b3";

export interface ScoringWodFixture {
  id: string;
  title: string;
  score_type: "time" | "rounds_reps" | "reps" | "load" | "none";
  time_cap_s: number | null;
  movements: { id: string; movement_id: string; movement_name: string; position: number; reps: string; load_rx_m_g: number | null; load_rx_f_g: number | null; is_primary: boolean; notes: string }[];
}

export function scoringWod(overrides: Partial<ScoringWodFixture> = {}): ScoringWodFixture {
  const base = { load_rx_m_g: null, load_rx_f_g: null, is_primary: false, notes: "" };
  return {
    id: WOD_ID,
    title: "Helen",
    score_type: "time",
    time_cap_s: 1200,
    movements: [
      { ...base, id: "w1", movement_id: MOV_RUN, movement_name: "Run 400 m", position: 1, reps: "1" },
      { ...base, id: "w2", movement_id: MOV_KB, movement_name: "Kettlebell swing", position: 2, reps: "21", load_rx_m_g: 24000, load_rx_f_g: 16000 },
      { ...base, id: "w3", movement_id: MOV_PULL, movement_name: "Pull-up", position: 3, reps: "12" },
    ],
    ...overrides,
  };
}

export interface ResultFixture {
  id: string;
  wod_id: string;
  member_id: string;
  session_id: string | null;
  wod_date: string;
  benchmark_id: string | null;
  level: "rx" | "rx_plus" | "scaled";
  seconds: number | null;
  rounds: number | null;
  reps: number | null;
  load_g: number | null;
  capped: boolean;
  scaled_movement_ids: string[];
  is_current: boolean;
  status: "validated" | "pending" | "voided";
  source: "desk" | "kiosk";
  recorded_by: string;
  supersedes_id: string | null;
  validated_by: string | null;
  validated_at: string | null;
  voided_by: string | null;
  voided_at: string | null;
  void_reason: string | null;
  created_at: string;
  updated_at: string;
}

export function resultOut(memberId: string, overrides: Partial<ResultFixture> = {}): ResultFixture {
  return {
    id: `e0e0e0e0-0000-4000-8000-${memberId.slice(-12)}`,
    wod_id: WOD_ID,
    member_id: memberId,
    session_id: SESSION_ID,
    wod_date: "2026-10-20",
    benchmark_id: null,
    level: "rx",
    seconds: 658,
    rounds: null,
    reps: null,
    load_g: null,
    capped: false,
    scaled_movement_ids: [],
    is_current: true,
    status: "validated",
    source: "kiosk",
    recorded_by: "c0c0c0c0-0000-4000-8000-0000000000c1",
    supersedes_id: null,
    validated_by: "c0c0c0c0-0000-4000-8000-0000000000c1",
    validated_at: "2026-10-20T22:00:00Z",
    voided_by: null,
    voided_at: null,
    void_reason: null,
    created_at: "2026-10-20T22:00:00Z",
    updated_at: "2026-10-20T22:00:00Z",
    ...overrides,
  };
}

export const mid = (n: number): string => `a0a0a0a0-0000-4000-8000-${String(n).padStart(12, "0")}`;

export interface AttendeeResultFixture {
  member_id: string;
  first_name: string;
  last_name: string;
  has_result: boolean;
  result: ResultFixture | null;
}

export function attendeeRow(n: number, first: string, last: string, result: ResultFixture | null = null): AttendeeResultFixture {
  return { member_id: mid(n), first_name: first, last_name: last, has_result: result !== null, result };
}

export const ATTENDEE_ROWS: AttendeeResultFixture[] = [
  attendeeRow(1, "Diego", "Mora", resultOut(mid(1), { seconds: 658 })),
  attendeeRow(2, "Sofía", "Pardo", resultOut(mid(2), { seconds: 820, level: "scaled", scaled_movement_ids: [MOV_PULL] })),
  attendeeRow(3, "Laura", "Gómez"),
  attendeeRow(4, "Juan", "Pérez"),
];

export function attendanceResults(rows: AttendeeResultFixture[] = ATTENDEE_ROWS, wod: ScoringWodFixture | null = scoringWod(), session: Record<string, unknown> = {}): MockReply {
  return {
    status: 200,
    body: {
      items: rows,
      total: rows.length,
      limit: 200,
      offset: 0,
      session: { ...SESSIONS.hoy17, attendance_count: rows.length, wod_id: wod?.id ?? null, effective_wod_id: wod?.id ?? null, ...session },
      wod: wod === null ? null : { ...wod, date: "2026-10-20", description: "", benchmark_id: null, benchmark_name: null, is_benchmark: false, result_count: 0, created_at: "2026-10-01T15:00:00Z", updated_at: "2026-10-01T15:00:00Z" },
    },
  };
}

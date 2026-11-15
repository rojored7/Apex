// S8-F1: datos de prueba de Movimientos y Benchmarks. Imitan CatalogMovementOut y BenchmarkOut del contrato (A1, A2).
import type { MockReply } from "./server";

export interface MovementFixture {
  id: string;
  name: string;
  category: "weightlifting" | "gymnastics" | "monostructural" | "other";
  unit: "kg" | "reps" | "m" | "cal" | "s";
  is_active: boolean;
  wod_count: number;
  created_at: string;
  updated_at: string;
}

export function movement(id: string, overrides: Partial<MovementFixture> = {}): MovementFixture {
  return {
    id,
    name: "Back Squat",
    category: "weightlifting",
    unit: "kg",
    is_active: true,
    wod_count: 38,
    created_at: "2026-10-01T15:00:00Z",
    updated_at: "2026-10-01T15:00:00Z",
    ...overrides,
  };
}

export const MOVEMENTS = {
  squat: movement("d1d1d1d1-0000-4000-8000-000000000001"),
  pullup: movement("d1d1d1d1-0000-4000-8000-000000000002", { name: "Pull-up", category: "gymnastics", unit: "reps", wod_count: 52 }),
  run: movement("d1d1d1d1-0000-4000-8000-000000000003", { name: "Run 400 m", category: "monostructural", unit: "m", wod_count: 44 }),
  viejo: movement("d1d1d1d1-0000-4000-8000-000000000004", { name: "Sled Push", category: "other", unit: "m", wod_count: 0, is_active: false }),
} as const;

export const MOVEMENT_ROWS: MovementFixture[] = [MOVEMENTS.squat, MOVEMENTS.pullup, MOVEMENTS.run, MOVEMENTS.viejo];

export const movementsPage = (rows: MovementFixture[] = MOVEMENT_ROWS, total = rows.length): MockReply => ({
  status: 200,
  body: { items: rows, total, limit: 25, offset: 0 },
});

export interface BenchmarkFixture {
  id: string;
  name: string;
  description: string;
  score_type: "time" | "rounds_reps" | "reps" | "load";
  wod_count: number;
  created_at: string;
  updated_at: string;
}

export function benchmark(id: string, overrides: Partial<BenchmarkFixture> = {}): BenchmarkFixture {
  return {
    id,
    name: "Fran",
    description: "21-15-9 de thrusters y pull-ups.",
    score_type: "time",
    wod_count: 0,
    created_at: "2026-10-01T15:00:00Z",
    updated_at: "2026-10-01T15:00:00Z",
    ...overrides,
  };
}

export const BENCHMARKS = {
  fran: benchmark("e1e1e1e1-0000-4000-8000-000000000001"),
  cindy: benchmark("e1e1e1e1-0000-4000-8000-000000000002", { name: "Cindy", description: "", score_type: "rounds_reps", wod_count: 3 }),
} as const;

export const BENCHMARK_ROWS: BenchmarkFixture[] = [BENCHMARKS.fran, BENCHMARKS.cindy];

export const benchmarksPage = (rows: BenchmarkFixture[] = BENCHMARK_ROWS, total = rows.length): MockReply => ({
  status: 200,
  body: { items: rows, total, limit: 25, offset: 0 },
});

// S8-F2: WodRowOut y WodOut del contrato (A3).
export interface WodRowFixture {
  id: string;
  date: string;
  title: string;
  score_type: "time" | "rounds_reps" | "reps" | "load" | "none";
  time_cap_s: number | null;
  benchmark_id: string | null;
  benchmark_name: string | null;
  is_benchmark: boolean;
  movement_count: number;
  movement_names: string[];
  result_count: number;
}

export function wodRow(id: string, overrides: Partial<WodRowFixture> = {}): WodRowFixture {
  return {
    id,
    date: "2026-10-21",
    title: "Fran",
    score_type: "time",
    time_cap_s: 600,
    benchmark_id: BENCHMARKS.fran.id,
    benchmark_name: "Fran",
    is_benchmark: true,
    movement_count: 2,
    movement_names: ["Thruster", "Pull-up"],
    result_count: 0,
    ...overrides,
  };
}

export const WODS = {
  fran: wodRow("f2f2f2f2-0000-4000-8000-000000000001"),
  fuerza: wodRow("f2f2f2f2-0000-4000-8000-000000000002", {
    date: "2026-10-22",
    title: "Back Squat 5x5",
    score_type: "load",
    time_cap_s: null,
    benchmark_id: null,
    benchmark_name: null,
    is_benchmark: false,
    movement_count: 1,
    movement_names: ["Back Squat"],
    result_count: 4,
  }),
} as const;

export const wodsPage = (rows: WodRowFixture[] = [WODS.fran, WODS.fuerza], total = rows.length): MockReply => ({
  status: 200,
  body: { items: rows, total, limit: 25, offset: 0 },
});

export interface WodMovementFixture {
  id: string;
  movement_id: string;
  movement_name: string;
  position: number;
  reps: string;
  load_rx_m_g: number | null;
  load_rx_f_g: number | null;
  is_primary: boolean;
  notes: string;
}

export function wodFull(row: WodRowFixture = WODS.fran, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const movements: WodMovementFixture[] = [
    { id: "a1", movement_id: MOVEMENTS.squat.id, movement_name: "Thruster", position: 1, reps: "21-15-9", load_rx_m_g: 43000, load_rx_f_g: 30000, is_primary: true, notes: "" },
    { id: "a2", movement_id: MOVEMENTS.pullup.id, movement_name: "Pull-up", position: 2, reps: "21-15-9", load_rx_m_g: null, load_rx_f_g: null, is_primary: false, notes: "" },
  ];
  return {
    id: row.id,
    date: row.date,
    title: row.title,
    description: "21-15-9",
    score_type: row.score_type,
    time_cap_s: row.time_cap_s,
    benchmark_id: row.benchmark_id,
    benchmark_name: row.benchmark_name,
    is_benchmark: row.is_benchmark,
    result_count: row.result_count,
    movements,
    created_at: "2026-10-01T15:00:00Z",
    updated_at: "2026-10-01T15:00:00Z",
    ...overrides,
  };
}

// S8-F3: LeaderboardRow, WodResultRow y sesiones del WOD del contrato (B4).
export interface LeaderboardFixture {
  position: number;
  result_id: string;
  member_id: string;
  first_name: string;
  last_initial: string;
  level: "rx" | "rx_plus" | "scaled";
  seconds: number | null;
  rounds: number | null;
  reps: number | null;
  load_g: number | null;
  capped: boolean;
}

export function boardRow(position: number, first: string, seconds: number | null, overrides: Partial<LeaderboardFixture> = {}): LeaderboardFixture {
  return {
    position,
    result_id: `b0b0b0b0-0000-4000-8000-0000000000${String(position).padStart(2, "0")}${String(first.length)}`,
    member_id: `a0a0a0a0-0000-4000-8000-0000000000${String(position).padStart(2, "0")}${String(first.length)}`,
    first_name: first,
    last_initial: "R",
    level: "rx",
    seconds,
    rounds: null,
    reps: null,
    load_g: null,
    capped: false,
    ...overrides,
  };
}

/** Empates: 1, 2, 2, 4. */
export const BOARD_ROWS: LeaderboardFixture[] = [boardRow(1, "Valentina", 598), boardRow(2, "Mariana", 644), boardRow(2, "Laura", 644), boardRow(4, "Paula", 750)];

export const boardPage = (rows: LeaderboardFixture[] = BOARD_ROWS, total = rows.length): MockReply => ({ status: 200, body: { items: rows, total, limit: 50, offset: 0 } });

export interface ResultRowFixture {
  id: string;
  member_id: string;
  first_name: string;
  last_name: string;
  level: "rx" | "rx_plus" | "scaled";
  seconds: number | null;
  rounds: number | null;
  reps: number | null;
  load_g: number | null;
  capped: boolean;
  is_current: boolean;
  status: "validated" | "pending" | "voided";
  source: "desk" | "kiosk";
  recorded_by: string;
  recorded_by_name: string | null;
  created_at: string;
  session_id: string | null;
  supersedes_id: string | null;
}

export function resultRow(id: string, first: string, overrides: Partial<ResultRowFixture> = {}): ResultRowFixture {
  return {
    id,
    member_id: `a0a0a0a0-0000-4000-8000-${id.slice(-12)}`,
    first_name: first,
    last_name: "Ríos",
    level: "rx",
    seconds: 598,
    rounds: null,
    reps: null,
    load_g: null,
    capped: false,
    is_current: true,
    status: "validated",
    source: "desk",
    recorded_by: "c0c0c0c0-0000-4000-8000-0000000000c1",
    recorded_by_name: "Carlos",
    created_at: "2026-10-21T12:48:00Z",
    session_id: null,
    supersedes_id: null,
    ...overrides,
  };
}

export const RESULT_ROWS: ResultRowFixture[] = [
  resultRow("c1c1c1c1-0000-4000-8000-000000000001", "Valentina", { source: "kiosk" }),
  resultRow("c1c1c1c1-0000-4000-8000-000000000002", "Mariana", { seconds: 644 }),
];

export const resultsPage = (rows: ResultRowFixture[] = RESULT_ROWS, total = rows.length): MockReply => ({ status: 200, body: { items: rows, total, limit: 50, offset: 0 } });

export const auditPage = (): MockReply => ({
  status: 200,
  body: {
    items: [
      { seq: 12, at: "2026-10-21T13:00:00Z", user_id: "c0c0c0c0-0000-4000-8000-0000000000c1", user_email: "carlos@ejemplo.local", user_name: "Carlos", action: "update", table_name: "wods.wods", record_id: WODS.fran.id, subject_member_id: null },
    ],
    total: 1,
    limit: 25,
    offset: 0,
  },
});

export const sessionsOfWod = (): MockReply => ({
  status: 200,
  body: {
    items: [
      {
        id: "d2d2d2d2-0000-4000-8000-000000000001",
        slot_id: null,
        session_date: "2026-10-21",
        starts_at: "2026-10-21T12:00:00Z",
        duration_min: 60,
        capacity: 20,
        coach_id: null,
        coach_name: "Carlos",
        name: null,
        status: "scheduled",
        attendance_count: 11,
        cancel_reason: null,
        cancelled_at: null,
        wod_id: WODS.fran.id,
        effective_wod_id: WODS.fran.id,
      },
    ],
    total: 1,
    limit: 50,
    offset: 0,
  },
});

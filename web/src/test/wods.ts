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

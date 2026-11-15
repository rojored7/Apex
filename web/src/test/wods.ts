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

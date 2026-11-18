// S9-F1 · US-178, US-179, US-184: datos y montaje de prueba de la pestaña Atleta.
// - Las filas imitan MetricOut de GET /athletes/{id}/metrics (S9-A1): solo `has_*` y fechas; NUNCA un valor (S9-D16).
// - SUMMARY imita AthleteSummaryOut de GET /athletes/{id}/summary (S9-A3): conteos, última fecha y tres récords vigentes.
// - Los valores en claro (CLEAR) solo los devuelve el reveal simulado; las pruebas comprueban que no quedan en la
//   URL, en un aria-label, en el almacenamiento ni en la caché de TanStack Query.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter, useLocation } from "react-router";
import type { components } from "../core/api/types";
import { SessionRoleProvider } from "../core/auth";
import { MEMBER_ID } from "./memberDetail";
import { mockApi, testQueryClient, type MockHandler, type MockReply, type RecordedCall } from "./server";

export { MEMBER_ID };

export type MetricFixture = components["schemas"]["MetricOut"];
export type SummaryFixture = components["schemas"]["AthleteSummaryOut"];
export type SummaryRecordFixture = components["schemas"]["SummaryRecordOut"];

export const SUMMARY_PATH = `/athletes/${MEMBER_ID}/summary`;
export const METRICS_PATH = `/athletes/${MEMBER_ID}/metrics`;
export const revealPath = (metricId: string): string => `${METRICS_PATH}/${metricId}/reveal`;
export const voidPath = (metricId: string): string => `${METRICS_PATH}/${metricId}/void`;

export const metricId = (n: number): string => `b0b0b0b0-0000-4000-8000-${String(n).padStart(12, "0")}`;

export const METRIC_RECORDER = "c0c0c0c0-0000-4000-8000-000000000001";

export function metric(n: number, overrides: Partial<MetricFixture> = {}): MetricFixture {
  return {
    id: metricId(n),
    measured_on: "2026-10-01",
    has_weight: true,
    has_height: true,
    has_body_fat: true,
    has_notes: false,
    recorded_by: METRIC_RECORDER,
    recorded_by_name: "Carlos",
    voided_at: null,
    created_at: "2026-10-01T15:00:00Z",
    ...overrides,
  };
}

/** Los valores en claro que devuelve el reveal simulado: 61,2 kg, 165 cm, 22 % y una nota. */
export const CLEAR = { weight_g: 61_200, height_cm: 165, body_fat_pct: 22, notes: "Vuelve tras la lesión de hombro" } as const;

/** Respuesta del reveal simulado: el valor en claro del campo pedido. */
export function revealReply(call: RecordedCall): MockReply {
  const field = (call.body as { field: keyof typeof CLEAR }).field;
  return { status: 200, body: { field, value: CLEAR[field] }, headers: { "Cache-Control": "no-store" } };
}

export function summary(overrides: Partial<SummaryFixture> = {}): SummaryFixture {
  return {
    metrics_count: 9,
    last_metric_on: "2026-10-01",
    current_rms: 14,
    benchmarks_with_attempts: 3,
    truncated: false,
    recent_records: [
      summaryRecord({ id: "d0d0d0d0-0000-4000-8000-000000000001", kind: "benchmark", benchmark_id: "e0e0e0e0-0000-4000-8000-000000000001", benchmark_name: "Helen", movement_id: null, movement_name: null, score_type: "time", seconds: 702, level: "rx", achieved_on: "2026-10-20", source: "derived", wod_id: "f2f2f2f2-0000-4000-8000-0000000000aa" }),
      summaryRecord({ id: "d0d0d0d0-0000-4000-8000-000000000002", kind: "rm", movement_id: "e1e1e1e1-0000-4000-8000-000000000001", movement_name: "Back Squat", value_g: 85_000, achieved_on: "2026-10-19", source: "derived", wod_id: "f2f2f2f2-0000-4000-8000-0000000000bb" }),
      summaryRecord({ id: "d0d0d0d0-0000-4000-8000-000000000003", kind: "rm", movement_id: "e1e1e1e1-0000-4000-8000-000000000002", movement_name: "Deadlift", value_g: 110_000, achieved_on: "2026-09-04", source: "manual", wod_id: null }),
    ],
    ...overrides,
  };
}

export function summaryRecord(overrides: Partial<SummaryRecordFixture> = {}): SummaryRecordFixture {
  return {
    id: "d0d0d0d0-0000-4000-8000-0000000000ff",
    kind: "rm",
    movement_id: null,
    movement_name: null,
    benchmark_id: null,
    benchmark_name: null,
    score_type: null,
    value_g: null,
    level: null,
    seconds: null,
    rounds: null,
    reps: null,
    load_g: null,
    capped: false,
    achieved_on: "2026-10-01",
    source: "manual",
    wod_id: null,
    ...overrides,
  };
}

/** Un resumen de un socio sin nada registrado. */
export const EMPTY_SUMMARY: SummaryFixture = { metrics_count: 0, last_metric_on: null, current_rms: 0, benchmarks_with_attempts: 0, truncated: false, recent_records: [] };

/** La página de una lista con el limit y el offset pedidos. */
export function pageReply(call: RecordedCall, rows: readonly unknown[], total = rows.length): MockReply {
  const url = new URL(call.url, "http://apex.test");
  return { status: 200, body: { items: rows, total, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) } };
}

export const apiError = (status: number, code: string, extra: Record<string, unknown> = {}, headers?: Record<string, string>): MockReply => ({
  status,
  body: { error: { code, message: "Mensaje del api.", ...extra } },
  ...(headers ? { headers } : {}),
});

/** Lo que la caché de TanStack Query guarda (consultas y mutaciones), como texto. */
export function cacheText(queryClient: QueryClient): string {
  const queries = queryClient
    .getQueryCache()
    .getAll()
    .map((q) => ({ key: q.queryKey, data: q.state.data }));
  const mutations = queryClient
    .getMutationCache()
    .getAll()
    .map((m) => m.state);
  return JSON.stringify({ queries, mutations });
}

function Where() {
  const location = useLocation();
  // <span> y no <output>: <output> tiene el rol «status» y chocaba con el «Cargando…» de la pantalla.
  return <span data-testid="where">{`${location.pathname}${location.search}`}</span>;
}

export interface RenderAthleteOptions {
  handlers?: Record<string, MockHandler>;
  queryClient?: QueryClient;
  route?: string;
}

/** Monta una pieza del atleta con sesión, caché de prueba, router y la API simulada; `where` muestra la URL. */
export function renderAthlete(ui: ReactElement, options: RenderAthleteOptions = {}) {
  const { handlers = {}, queryClient = testQueryClient(), route = `/socios/${MEMBER_ID}/atleta` } = options;
  const mock = mockApi(handlers);
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SessionRoleProvider>
        <MemoryRouter initialEntries={[route]}>
          {ui}
          <Where />
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, queryClient, user: userEvent.setup(), ...view };
}

// ---------------------------------------------------------------------------------------------------------------------------
// S9-F2 · US-180 a US-182: RMs, récords y catálogo (RmOut, RecordOut, CatalogMovementOut y BenchmarkOut del contrato).
export type RmFixture = components["schemas"]["RmOut"];
export type RecordFixture = components["schemas"]["RecordOut"];

export const RMS_PATH = `/athletes/${MEMBER_ID}/rms`;
export const RECORDS_PATH = `/athletes/${MEMBER_ID}/records`;
export const invalidatePath = (recordId: string): string => `${RECORDS_PATH}/${recordId}/invalidate`;

export const recordId = (n: number): string => `a1a1a1a1-0000-4000-8000-${String(n).padStart(12, "0")}`;
export const WOD_ID = "f2f2f2f2-0000-4000-8000-0000000000aa";
export const OTHER_WOD_ID = "f2f2f2f2-0000-4000-8000-0000000000bb";

/** El RM vigente de un movimiento (RmOut): gramos enteros. */
export function rm(n: number, overrides: Partial<RmFixture> = {}): RmFixture {
  return {
    record_id: recordId(n),
    movement_id: movementId(n),
    movement_name: "Back Squat",
    value_g: 85_000,
    achieved_on: "2026-10-19",
    source: "derived",
    ...overrides,
  };
}

export const movementId = (n: number): string => `d1d1d1d1-0000-4000-8000-${String(n).padStart(12, "0")}`;
export const benchmarkId = (n: number): string => `e1e1e1e1-0000-4000-8000-${String(n).padStart(12, "0")}`;

/** Un récord (RecordOut): por omisión un RM manual vigente de Deadlift. */
export function record(n: number, overrides: Partial<RecordFixture> = {}): RecordFixture {
  return {
    id: recordId(n),
    kind: "rm",
    movement_id: movementId(2),
    movement_name: "Deadlift",
    benchmark_id: null,
    benchmark_name: null,
    score_type: null,
    value_g: 110_000,
    level: null,
    seconds: null,
    rounds: null,
    reps: null,
    load_g: null,
    capped: false,
    achieved_on: "2026-09-04",
    source: "manual",
    wod_id: null,
    result_id: null,
    result_source: null,
    is_current: true,
    invalidated_at: null,
    invalidated_reason: null,
    recorded_by: METRIC_RECORDER,
    recorded_by_name: "Carlos",
    created_at: "2026-09-04T15:00:00Z",
    ...overrides,
  };
}

/** Un récord derivado de un RM por carga (viene del resultado de un WOD). */
export const derivedRm = (n: number, overrides: Partial<RecordFixture> = {}): RecordFixture =>
  record(n, { movement_id: movementId(1), movement_name: "Back Squat", value_g: 85_000, achieved_on: "2026-10-19", source: "derived", wod_id: WOD_ID, result_id: `c1c1c1c1-0000-4000-8000-${String(n).padStart(12, "0")}`, result_source: "desk", ...overrides });

/** Un récord derivado de un benchmark por tiempo (Helen 11:42 RX). */
export const derivedBenchmark = (n: number, overrides: Partial<RecordFixture> = {}): RecordFixture =>
  record(n, {
    kind: "benchmark",
    movement_id: null,
    movement_name: null,
    value_g: null,
    benchmark_id: benchmarkId(3),
    benchmark_name: "Helen",
    score_type: "time",
    seconds: 702,
    level: "rx",
    achieved_on: "2026-10-20",
    source: "derived",
    wod_id: OTHER_WOD_ID,
    result_id: `c1c1c1c1-0000-4000-8000-${String(n).padStart(12, "0")}`,
    result_source: "desk",
    ...overrides,
  });

/** Catálogo de prueba: tres movimientos en kg activos, uno en repeticiones, uno inactivo en kg y otro inactivo en metros. */
export const CATALOG_MOVEMENTS = [
  catalogMovement(1, "Back Squat", "kg", true),
  catalogMovement(2, "Deadlift", "kg", true),
  catalogMovement(3, "Pull-up", "reps", true),
  catalogMovement(4, "Clean viejo", "kg", false),
  catalogMovement(5, "Sled Push", "m", false),
];

function catalogMovement(n: number, name: string, unit: "kg" | "reps" | "m", isActive: boolean) {
  return { id: movementId(n), name, category: "weightlifting" as const, unit, is_active: isActive, wod_count: 3, created_at: "2026-10-01T15:00:00Z", updated_at: "2026-10-01T15:00:00Z" };
}

export const CATALOG_BENCHMARKS = [
  catalogBenchmark(1, "Fran", "time"),
  catalogBenchmark(2, "Cindy", "rounds_reps"),
  catalogBenchmark(3, "Helen", "time"),
  catalogBenchmark(4, "Max Pull-ups", "reps"),
  catalogBenchmark(5, "Max Clean", "load"),
];

function catalogBenchmark(n: number, name: string, scoreType: "time" | "rounds_reps" | "reps" | "load") {
  return { id: benchmarkId(n), name, description: "", score_type: scoreType, wod_count: 2, created_at: "2026-10-01T15:00:00Z", updated_at: "2026-10-01T15:00:00Z" };
}

/** GET /movements como el api: respeta `active` y devuelve la página pedida. */
export const movementsHandler: MockHandler = (call) => {
  const url = new URL(call.url, "http://apex.test");
  const onlyActive = url.searchParams.get("active") === "true";
  return pageReply(call, CATALOG_MOVEMENTS.filter((m) => !onlyActive || m.is_active));
};

export const benchmarksHandler: MockHandler = (call) => pageReply(call, CATALOG_BENCHMARKS);

/** Los dos catálogos simulados, para pantallas que los piden (el panel de récords). */
export const CATALOG_HANDLERS: Record<string, MockHandler> = { "GET /movements": movementsHandler, "GET /benchmarks": benchmarksHandler };

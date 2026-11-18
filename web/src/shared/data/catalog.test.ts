// S9-F2 (E8, S9-D40): useMovements y useBenchmarks salen de features/wods a shared/data/catalog.ts sin cambiar su comportamiento, y
// nacen dos lecturas de «opciones» para el panel de récords: movimientos activos que se miden en kg y benchmarks con su tipo de marca.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { apiError, benchmarkId, benchmarksHandler, CATALOG_BENCHMARKS, movementId, movementsHandler } from "../../test/athletes";
import { mockApi, testQueryClient } from "../../test/server";
import { BENCHMARKS_QUERY_KEY, MOVEMENTS_QUERY_KEY, useBenchmarkOptions, useBenchmarks, useKgMovementOptions, useMovements } from "./catalog";

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

const queryOf = (call: { url: string } | undefined): string => new URL(call?.url ?? "", "http://apex.test").searchParams.toString();

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("claves del catálogo", () => {
  it("son ['movements'] y ['benchmarks'], las que invalidan las escrituras de features/wods", () => {
    expect(MOVEMENTS_QUERY_KEY).toEqual(["movements"]);
    expect(BENCHMARKS_QUERY_KEY).toEqual(["benchmarks"]);
  });
});

describe("useMovements", () => {
  it("pide GET /movements con limit, offset y los filtros dados, y valida la página", async () => {
    const mock = mockApi({ "GET /movements": movementsHandler });
    const { result } = renderHook(() => useMovements({ limit: 100, offset: 0, active: true }), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(queryOf(mock.calls[0])).toBe("limit=100&offset=0&active=true");
    expect(result.current.data?.items.map((m) => m.name)).toEqual(["Back Squat", "Deadlift", "Pull-up"]);
  });

  it("con enabled=false no pide nada", () => {
    const mock = mockApi({ "GET /movements": movementsHandler });
    renderHook(() => useMovements({ limit: 25, offset: 0 }, false), { wrapper: wrapper(testQueryClient()) });

    expect(mock.calls).toHaveLength(0);
  });

  it("una unidad que el contrato no declara es invalid_response", async () => {
    mockApi({ "GET /movements": (call) => ({ status: 200, body: { items: [{ ...firstMovement(), unit: "parsec" }], total: 1, limit: Number(new URL(call.url, "http://apex.test").searchParams.get("limit")), offset: 0 } }) });
    const { result } = renderHook(() => useMovements({ limit: 25, offset: 0 }), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ code: "invalid_response" });
  });

  it("la clave de la consulta cuelga de ['movements']", async () => {
    mockApi({ "GET /movements": movementsHandler });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => useMovements({ limit: 25, offset: 0 }), { wrapper: wrapper(queryClient) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(queryClient.getQueryCache().findAll({ queryKey: MOVEMENTS_QUERY_KEY })).toHaveLength(1);
  });
});

describe("useBenchmarks", () => {
  it("pide GET /benchmarks con limit, offset y filtros, y valida la página", async () => {
    const mock = mockApi({ "GET /benchmarks": benchmarksHandler });
    const { result } = renderHook(() => useBenchmarks({ limit: 100, offset: 0, score_type: "time" }), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(queryOf(mock.calls[0])).toBe("limit=100&offset=0&score_type=time");
    expect(result.current.data?.items.map((b) => b.name)).toEqual(CATALOG_BENCHMARKS.map((b) => b.name));
  });

  it("un 500 queda como error de la consulta", async () => {
    mockApi({ "GET /benchmarks": apiError(500, "internal_error") });
    const { result } = renderHook(() => useBenchmarks({ limit: 25, offset: 0 }), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

describe("useKgMovementOptions", () => {
  it("pide solo los activos (limit 200) y deja los que se miden en kg, en el orden del api", async () => {
    const mock = mockApi({ "GET /movements": movementsHandler });
    const { result } = renderHook(() => useKgMovementOptions(), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(queryOf(mock.calls[0])).toBe("limit=200&offset=0&active=true");
    expect(result.current.data).toEqual([
      { value: movementId(1), label: "Back Squat" },
      { value: movementId(2), label: "Deadlift" },
    ]);
  });

  it("un movimiento inactivo en kg no es una opción aunque el api lo devolviera", async () => {
    mockApi({ "GET /movements": (call) => ({ status: 200, body: { items: [{ ...firstMovement(), is_active: false }], total: 1, limit: Number(new URL(call.url, "http://apex.test").searchParams.get("limit")), offset: 0 } }) });
    const { result } = renderHook(() => useKgMovementOptions(), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toEqual([]);
  });

  it("un error del api queda como error de la consulta", async () => {
    mockApi({ "GET /movements": apiError(500, "internal_error") });
    const { result } = renderHook(() => useKgMovementOptions(), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });

  it("la consulta cuelga de ['movements']: una escritura del catálogo la refresca", async () => {
    mockApi({ "GET /movements": movementsHandler });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => useKgMovementOptions(), { wrapper: wrapper(queryClient) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(queryClient.getQueryCache().findAll({ queryKey: MOVEMENTS_QUERY_KEY }).length).toBeGreaterThanOrEqual(1);
  });
});

describe("useBenchmarkOptions", () => {
  it("pide limit 200 y devuelve cada benchmark con su tipo de marca, en el orden del api", async () => {
    const mock = mockApi({ "GET /benchmarks": benchmarksHandler });
    const { result } = renderHook(() => useBenchmarkOptions(), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(queryOf(mock.calls[0])).toBe("limit=200&offset=0");
    expect(result.current.data).toEqual([
      { value: benchmarkId(1), label: "Fran", scoreType: "time" },
      { value: benchmarkId(2), label: "Cindy", scoreType: "rounds_reps" },
      { value: benchmarkId(3), label: "Helen", scoreType: "time" },
      { value: benchmarkId(4), label: "Max Pull-ups", scoreType: "reps" },
      { value: benchmarkId(5), label: "Max Clean", scoreType: "load" },
    ]);
  });

  it("la consulta cuelga de ['benchmarks']", async () => {
    mockApi({ "GET /benchmarks": benchmarksHandler });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => useBenchmarkOptions(), { wrapper: wrapper(queryClient) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(queryClient.getQueryCache().findAll({ queryKey: BENCHMARKS_QUERY_KEY }).length).toBeGreaterThanOrEqual(1);
  });
});

/** Un movimiento activo en kg del catálogo de prueba (copia, para variarlo). */
function firstMovement() {
  return { id: movementId(1), name: "Back Squat", category: "weightlifting", unit: "kg", is_active: true, wod_count: 3, created_at: "2026-10-01T15:00:00Z", updated_at: "2026-10-01T15:00:00Z" };
}

// Revisión S9-F2 (TS M1): una sola fuente para el contrato del catálogo; features/wods la reexporta.
describe("fuente única del contrato (revisión M1)", () => {
  it("features/wods usa los mismos esquemas y tipos de filtros que shared/data/catalog", async () => {
    const wods = await import("../../features/wods/schemas");
    const catalog = await import("./catalog");
    expect(wods.movementSchema).toBe(catalog.movementSchema);
    expect(wods.benchmarkSchema).toBe(catalog.benchmarkSchema);
    expect(wods.MOVEMENT_CATEGORIES).toBe(catalog.MOVEMENT_CATEGORIES);
    expect(wods.MOVEMENT_UNITS).toBe(catalog.MOVEMENT_UNITS);
  });
});

// Revisión S9-F2 (TS M2): las opciones cubren `total` página a página (de a 200) con un tope de 5 páginas y avisan si faltan.
describe("opciones con más de una página (revisión M2)", () => {
  const manyMovements = (count: number) =>
    Array.from({ length: count }, (_, i) => ({ id: `d1d1d1d1-0000-4000-8000-${String(i).padStart(12, "0")}`, name: `Mov ${String(i)}`, category: "weightlifting", unit: "kg", is_active: true, wod_count: 0, created_at: "2026-10-01T15:00:00Z", updated_at: "2026-10-01T15:00:00Z" }));
  const pagedHandler = (all: readonly unknown[]) => (call: { url: string }) => {
    const params = new URL(call.url, "http://apex.test").searchParams;
    const limit = Number(params.get("limit"));
    const offset = Number(params.get("offset"));
    return { status: 200, body: { items: all.slice(offset, offset + limit), total: all.length, limit, offset } };
  };

  it("con 450 movimientos en kg pide tres páginas (offset 0, 200 y 400) y devuelve las 450 opciones sin aviso", async () => {
    const mock = mockApi({ "GET /movements": pagedHandler(manyMovements(450)) });
    const { result } = renderHook(() => useKgMovementOptions(), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(mock.calls.map((c) => new URL(c.url, "http://apex.test").searchParams.get("offset"))).toEqual(["0", "200", "400"]);
    expect(result.current.data).toHaveLength(450);
    expect(result.current.truncated).toBe(false);
  });

  it("con 1.500 benchmarks para en 5 páginas (1.000 opciones) y lo marca como truncado", async () => {
    const all = Array.from({ length: 1500 }, (_, i) => ({ id: `e1e1e1e1-0000-4000-8000-${String(i).padStart(12, "0")}`, name: `B ${String(i)}`, description: "", score_type: "time", wod_count: 0, created_at: "2026-10-01T15:00:00Z", updated_at: "2026-10-01T15:00:00Z" }));
    const mock = mockApi({ "GET /benchmarks": pagedHandler(all) });
    const { result } = renderHook(() => useBenchmarkOptions(), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(mock.calls).toHaveLength(5);
    expect(result.current.data).toHaveLength(1000);
    expect(result.current.truncated).toBe(true);
  });

  it("con una sola página no hay aviso y `refetch` vuelve a pedir", async () => {
    const mock = mockApi({ "GET /benchmarks": benchmarksHandler });
    const { result } = renderHook(() => useBenchmarkOptions(), { wrapper: wrapper(testQueryClient()) });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.truncated).toBe(false);

    await result.current.refetch();

    expect(mock.calls).toHaveLength(2);
  });
});

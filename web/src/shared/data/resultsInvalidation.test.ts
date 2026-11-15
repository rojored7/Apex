// S8-F6b (M-5): guardar o anular un resultado relee TODO lo que lo muestra: ranking, lista de resultados, WODs, la ficha del socio
// (pestaña Resultados), la tablet de la clase y el WOD de hoy de Inicio.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { useSaveResult } from "../../features/results/api";
import { mockApi, testQueryClient } from "../../test/server";
import { useVoidResult } from "./results";

const EXPECTED = [["wod-leaderboard"], ["wod-results"], ["wods"], ["wod"], ["member-results"], ["session-results"], ["dashboard"]];
const SAVED = {
  id: "r1",
  wod_id: "w1",
  member_id: "m1",
  session_id: "s1",
  level: "rx",
  seconds: 600,
  rounds: null,
  reps: null,
  load_g: null,
  capped: false,
  scaled_movement_ids: [],
  is_current: true,
  status: "validated",
  source: "desk",
  supersedes_id: null,
};

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

const keysOf = (spy: { mock: { calls: readonly (readonly unknown[])[] } }): string[] =>
  spy.mock.calls.map((call) => JSON.stringify((call[0] as { queryKey?: unknown } | undefined)?.queryKey));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("invalidaciones de resultados", () => {
  it("guardar un resultado relee ranking, lista, WODs, ficha del socio, tablet y Inicio", async () => {
    mockApi({ "PUT /results": { status: 201, body: SAVED } });
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useSaveResult(), { wrapper: wrapper(queryClient) });

    await result.current.mutateAsync({
      wodId: "w1",
      memberId: "m1",
      sessionId: "s1",
      score: { level: "rx", capped: false, seconds: 600, rounds: null, reps: null, load_g: null, scaled_movement_ids: [] },
    });

    await waitFor(() => {
      expect(keysOf(invalidate)).toEqual(expect.arrayContaining(EXPECTED.map((key) => JSON.stringify(key))));
    });
  });

  it("anular un resultado relee lo mismo, también la tablet de la clase", async () => {
    mockApi({ "POST /results/r1/void": { status: 200, body: { id: "r1" } } });
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useVoidResult(), { wrapper: wrapper(queryClient) });

    await result.current.mutateAsync({ id: "r1", reason: "Error de captura" });

    await waitFor(() => {
      expect(keysOf(invalidate)).toEqual(expect.arrayContaining(EXPECTED.map((key) => JSON.stringify(key))));
    });
  });
});

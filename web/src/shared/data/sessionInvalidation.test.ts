// S8-V7b (L-1): lo que cambia una clase (quitar una asistencia, cancelar una sesión o la franja entera, cambiar el WOD) relee TODO lo
// que la muestra: la clase, las listas de sesiones, las asistencias, la tablet de resultados, las clases del WOD y Inicio.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { useCancelFutureSessions, useCancelSession, useRemoveAttendance } from "../../features/classes/api";
import { useUpdateWod } from "../../features/wods/wodsApi";
import { mockApi, testQueryClient } from "../../test/server";

const EXPECTED = [["class-session"], ["class-sessions"], ["attendance"], ["session-results"], ["wod-sessions"], ["dashboard"]].map((key) => JSON.stringify(key));

const SESSION = {
  id: "s1",
  slot_id: null,
  session_date: "2026-10-21",
  starts_at: "2026-10-21T15:00:00Z",
  duration_min: 60,
  capacity: 12,
  coach_id: null,
  coach_name: null,
  name: null,
  status: "cancelled",
  attendance_count: 0,
  cancel_reason: "Lluvia",
  cancelled_at: "2026-10-21T14:00:00Z",
};
const WOD = {
  id: "w1",
  date: "2026-10-21",
  title: "Helen",
  description: "",
  score_type: "time",
  time_cap_s: null,
  benchmark_id: null,
  benchmark_name: null,
  is_benchmark: false,
  result_count: 0,
  movements: [],
  created_at: "2026-10-21T10:00:00Z",
  updated_at: "2026-10-21T10:00:00Z",
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

describe("invalidaciones de la clase", () => {
  it("quitar una asistencia relee también los resultados de la tablet, las clases del WOD e Inicio", async () => {
    mockApi({ "DELETE /attendance/a1": { status: 204, body: null } });
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useRemoveAttendance(), { wrapper: wrapper(queryClient) });

    await result.current.mutateAsync({ id: "a1" });

    await waitFor(() => {
      expect(keysOf(invalidate)).toEqual(expect.arrayContaining(EXPECTED));
    });
  });

  it("cancelar una sesión relee la clase, los resultados, las clases del WOD e Inicio", async () => {
    mockApi({ "POST /class-sessions/s1/cancel": { status: 200, body: SESSION } });
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useCancelSession(), { wrapper: wrapper(queryClient) });

    await result.current.mutateAsync({ id: "s1", reason: "Lluvia" });

    await waitFor(() => {
      expect(keysOf(invalidate)).toEqual(expect.arrayContaining(EXPECTED));
    });
  });

  it("cancelar las futuras de una franja relee lo mismo", async () => {
    mockApi({ "POST /class-slots/f1/cancel-future-sessions": { status: 200, body: { cancelled_count: 2 } } });
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useCancelFutureSessions(), { wrapper: wrapper(queryClient) });

    await result.current.mutateAsync({ id: "f1", reason: "Festivo" });

    await waitFor(() => {
      expect(keysOf(invalidate)).toEqual(expect.arrayContaining(EXPECTED));
    });
  });

  it("cambiar un WOD relee las clases que lo heredan, la tablet y Inicio", async () => {
    mockApi({ "PATCH /wods/w1": { status: 200, body: WOD } });
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useUpdateWod("w1"), { wrapper: wrapper(queryClient) });

    await result.current.mutateAsync({ title: "Helen" });

    await waitFor(() => {
      expect(keysOf(invalidate)).toEqual(expect.arrayContaining(EXPECTED));
    });
  });
});

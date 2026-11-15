// S8-F5 (limpieza de F4): la llegada de un socio (POST /attendance) vive una sola vez en shared/data. Las dos features
// (classes: check-in; results: «Alguien que no hizo check-in») usan la misma copia.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { mockApi, testQueryClient } from "../../test/server";
import { checkinSchema, useCheckIn } from "./attendance";

const CREATED = { id: "a1", flags: ["no_membership"], flagged: true, membership_status_at_checkin: "active", attendance_count: 4, capacity: 12 };

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useCheckIn", () => {
  it("manda solo la sesión y el socio y devuelve la llegada validada", async () => {
    const mock = mockApi({ "POST /attendance": { status: 201, body: CREATED } });
    const { result } = renderHook(() => useCheckIn(), { wrapper: wrapper(testQueryClient()) });

    const created = await result.current.mutateAsync({ sessionId: "s1", memberId: "m1" });

    expect(mock.callsTo("POST /attendance")[0]?.body).toEqual({ session_id: "s1", member_id: "m1" });
    expect(created.flags).toEqual(["no_membership"]);
    expect(checkinSchema.safeParse({ id: "x" }).success).toBe(false);
  });

  it("relee la clase, las sesiones, las asistencias y los resultados de la tablet, también si falla", async () => {
    mockApi({ "POST /attendance": { status: 409, body: { error: { code: "attendance_exists", message: "ya", details: {} } } } });
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useCheckIn(), { wrapper: wrapper(queryClient) });

    await expect(result.current.mutateAsync({ sessionId: "s1", memberId: "m1" })).rejects.toBeDefined();

    await waitFor(() => {
      const keys = invalidate.mock.calls.map((call) => JSON.stringify(call[0]?.queryKey));
      expect(keys).toEqual(expect.arrayContaining([JSON.stringify(["class-session"]), JSON.stringify(["class-sessions"]), JSON.stringify(["attendance"]), JSON.stringify(["session-results"])]));
    });
  });
});

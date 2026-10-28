// Fase 4 del Sprint 3 (L3 y L7): hooks de socios.
// - useUpdateMember deja el nombre nuevo en ["member-name", id], la clave que leen la venta y el panel
//   de pagos cuando llegan solo con el id (S3-F7); antes seguían diciendo el nombre viejo 5 minutos.
// - useMembersInfinite no guarda las tarjetas al dejar de usarlas: al volver pide solo la primera página, en vez de releer en
//   serie todas las que se habían cargado (hasta 20).
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { memberNameKey } from "../../shared/data/members";
import { DETAIL_PATH, MEMBER_ID, memberDetailBody } from "../../test/memberDetail";
import { memberRows, pagedMemberPage } from "../../test/members";
import { mockApi, testQueryClient } from "../../test/server";
import { membersInfiniteKey, useMembersInfinite, useUpdateMember, type MembersInfiniteParams } from "./api";

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useUpdateMember", () => {
  it("al guardar pone el nombre nuevo en ['member-name', id]", async () => {
    mockApi({ [`PATCH ${DETAIL_PATH}`]: { status: 200, body: memberDetailBody({ first_name: "Laura Sofía", last_name: "Gómez" }) } });
    const queryClient = testQueryClient();
    queryClient.setQueryData(memberNameKey(MEMBER_ID), "Laura Gómez");
    const { result } = renderHook(() => useUpdateMember(MEMBER_ID), { wrapper: wrapper(queryClient) });

    await act(async () => {
      await result.current.update({ first_name: "Laura Sofía" });
    });

    expect(queryClient.getQueryData(memberNameKey(MEMBER_ID))).toBe("Laura Sofía Gómez");
  });
});

describe("useMembersInfinite", () => {
  const PARAMS: MembersInfiniteParams = { limit: 25 };
  const ROWS = memberRows(60);
  const offsetsOf = (mock: ReturnType<typeof mockApi>): (string | null)[] => mock.callsTo("GET /members").map((call) => new URL(call.url, "http://apex.test").searchParams.get("offset"));

  async function loadTwoPages(queryClient: ReturnType<typeof testQueryClient>, params: MembersInfiniteParams = PARAMS) {
    const hook = renderHook(({ p }) => useMembersInfinite(p), { wrapper: wrapper(queryClient), initialProps: { p: params } });
    // TanStack solo vuelve a pintar por las propiedades leídas: se lee `data` desde el principio.
    await waitFor(() => {
      expect(hook.result.current.data?.pages).toHaveLength(1);
    });
    await act(async () => {
      await hook.result.current.fetchNextPage();
    });
    await waitFor(() => {
      expect(hook.result.current.data?.pages).toHaveLength(2);
    });
    return hook;
  }

  it("al volver a la lista (otro montaje) pide solo la primera página, no relee en serie las cargadas", async () => {
    const mock = mockApi({ "GET /members": (call) => pagedMemberPage(call, ROWS) });
    const queryClient = testQueryClient();
    const first = await loadTwoPages(queryClient);
    first.unmount();
    // gcTime 0: al dejar de usarse, la lista sale de la caché (antes de que se vuelva a la pantalla).
    await waitFor(() => {
      expect(queryClient.getQueryCache().find({ queryKey: membersInfiniteKey(PARAMS) })).toBeUndefined();
    });

    const { result } = renderHook(() => useMembersInfinite(PARAMS), { wrapper: wrapper(queryClient) });

    await waitFor(() => {
      expect(result.current.data?.pages).toHaveLength(1);
    });
    expect(offsetsOf(mock)).toEqual(["0", "25", "0"]);
  });

  it("al cambiar de filtro y volver, una sola petición por cambio (revisión final: sin relectura doble)", async () => {
    const mock = mockApi({ "GET /members": (call) => pagedMemberPage(call, ROWS) });
    const queryClient = testQueryClient();
    const hook = await loadTwoPages(queryClient);

    hook.rerender({ p: { limit: 25, membership_status: "active" } });
    await waitFor(() => {
      expect(hook.result.current.isFetching).toBe(false);
    });
    hook.rerender({ p: PARAMS });
    await waitFor(() => {
      expect(hook.result.current.data?.pages).toHaveLength(1);
    });
    await waitFor(() => {
      expect(hook.result.current.isFetching).toBe(false);
    });

    expect(offsetsOf(mock)).toEqual(["0", "25", "0", "0"]);
  });
});

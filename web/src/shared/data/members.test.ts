// S3-F3 (S3-D65): búsqueda de socios compartida (vender; en S3-F4, registrar un pago).
// createElement en lugar de JSX: el plan fija el nombre members.test.ts (gate de F3, E12).
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { act, render, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { createMemoryRouter, MemoryRouter, Outlet, RouterProvider, useLocation } from "react-router";
import { MEMBERS, memberPage } from "../../test/members";
import { mockApi, testQueryClient } from "../../test/server";
import { MEMBER_SEARCH_DELAY_MS, memberFullName, memberNameKey, membersSearchKey, memberSearchNote, useMemberName, useMemberSearch, useMembersSearch, useMemberTab, type MemberTabContext, type MemberTabMember } from "./members";

function wrapper(queryClient: QueryClient, seen: string[]) {
  function Spy() {
    const location = useLocation();
    seen.push(`${location.pathname}${location.search}`);
    return null;
  }
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(
      QueryClientProvider,
      { client: queryClient },
      createElement(MemoryRouter, { initialEntries: ["/membresias/vender"] }, createElement(Spy), children),
    );
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useMembersSearch", () => {
  it("sin texto (o solo espacios) no pide nada", async () => {
    const mock = mockApi({ "GET /members": (call) => memberPage(call) });
    const { result } = renderHook(() => useMembersSearch("   "), { wrapper: wrapper(testQueryClient(), []) });

    await Promise.resolve();
    expect(result.current.fetchStatus).toBe("idle");
    expect(mock.calls).toHaveLength(0);
  });

  it("pide GET /members con q recortada, limit 10 y offset 0, y valida la página", async () => {
    const mock = mockApi({ "GET /members": (call) => memberPage(call, [MEMBERS.laura]) });
    const { result } = renderHook(() => useMembersSearch(" laura "), { wrapper: wrapper(testQueryClient(), []) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(new URL(mock.calls[0]?.url ?? "", "http://apex.test").searchParams.toString()).toBe("limit=10&offset=0&q=laura");
    expect(result.current.data?.items.map(memberFullName)).toEqual(["Laura Gómez"]);
  });

  it("toma solo lo que el selector usa: un campo nuevo de MemberRowOut no rompe la búsqueda", async () => {
    mockApi({ "GET /members": (call) => memberPage(call, [{ ...MEMBERS.laura, membership_end_date: "2026-11-27" }]) });
    const { result } = renderHook(() => useMembersSearch("laura"), { wrapper: wrapper(testQueryClient(), []) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    // Fase 4 (pendiente 2 de V1): la venta pinta `membership_end_date` (S3-B9b), así que el
    // esquema ya lo toma; la aserción anterior comprobaba que se descartara. Lo que no usa (`sex`)
    // sigue fuera.
    expect(result.current.data?.items[0]).toHaveProperty("membership_end_date", "2026-11-27");
    expect(result.current.data?.items[0]).not.toHaveProperty("sex");
  });

  it("una respuesta con otra forma es invalid_response", async () => {
    mockApi({ "GET /members": { status: 200, body: { items: [{ id: 1 }], total: 1, limit: 10, offset: 0 } } });
    const { result } = renderHook(() => useMembersSearch("laura"), { wrapper: wrapper(testQueryClient(), []) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ code: "invalid_response" });
  });

  it("no guarda q en la URL de la app (S2-D41)", async () => {
    mockApi({ "GET /members": (call) => memberPage(call) });
    const seen: string[] = [];
    const { result } = renderHook(() => useMembersSearch("1020304417"), { wrapper: wrapper(testQueryClient(), seen) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(seen.every((url) => url === "/membresias/vender")).toBe(true);
  });

  it("la búsqueda no se queda en la caché al dejar de usarse (gcTime 0)", async () => {
    mockApi({ "GET /members": (call) => memberPage(call) });
    const queryClient = testQueryClient();
    const { result, unmount } = renderHook(() => useMembersSearch("laura"), { wrapper: wrapper(queryClient, []) });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    unmount();

    await waitFor(() => {
      expect(queryClient.getQueryCache().find({ queryKey: membersSearchKey("laura") })).toBeUndefined();
    });
  });
});

describe("memberFullName", () => {
  it("une nombre y apellido sin espacios de más", () => {
    expect(memberFullName({ first_name: "Laura", last_name: "Gómez" })).toBe("Laura Gómez");
    expect(memberFullName({ first_name: "Laura", last_name: "" })).toBe("Laura");
  });
});

// S3-F7 (pendiente de S3-F1): el nombre de un socio que llega solo con su id, y el socio que la ficha
// pasa a sus pestañas por el contexto del <Outlet />.
describe("useMemberName", () => {
  const ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const detail = { id: ID, first_name: "Laura", last_name: "Gómez", document: "CC •••• 4417", deleted_at: null };

  it("pide GET /members/{id} y devuelve 'Nombre Apellido' con la clave ['members', 'name', id]", async () => {
    const mock = mockApi({ [`GET /members/${ID}`]: { status: 200, body: detail } });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => useMemberName(ID), { wrapper: wrapper(queryClient, []) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toBe("Laura Gómez");
    expect(mock.callsTo(`GET /members/${ID}`)).toHaveLength(1);
    expect(memberNameKey(ID)).toEqual(["member-name", ID]);
    // Solo el nombre queda en la caché: ni el documento enmascarado ni el resto de la ficha.
    expect(queryClient.getQueryData(memberNameKey(ID))).toBe("Laura Gómez");
  });

  it("sin id no pide nada", () => {
    const mock = mockApi({});
    const { result } = renderHook(() => useMemberName(null), { wrapper: wrapper(testQueryClient(), []) });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mock.calls).toHaveLength(0);
  });

  it("una respuesta sin nombre es invalid_response y un 404 llega como error", async () => {
    mockApi({ [`GET /members/${ID}`]: { status: 200, body: { id: ID } } });
    const bad = renderHook(() => useMemberName(ID), { wrapper: wrapper(testQueryClient(), []) });
    await waitFor(() => {
      expect(bad.result.current.isError).toBe(true);
    });
    expect(bad.result.current.error).toMatchObject({ code: "invalid_response" });

    mockApi({ [`GET /members/${ID}`]: { status: 404, body: { error: { code: "member_not_found", message: "No existe." } } } });
    const missing = renderHook(() => useMemberName(ID), { wrapper: wrapper(testQueryClient(), []) });
    await waitFor(() => {
      expect(missing.result.current.isError).toBe(true);
    });
    expect(missing.result.current.error).toMatchObject({ status: 404 });
  });
});

describe("useMemberTab", () => {
  it("lee el socio del contexto del <Outlet /> de la ficha y sin él es null", async () => {
    const member = { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", first_name: "Laura", last_name: "Gómez", deleted_at: null };
    const seen: (MemberTabMember | null)[] = [];
    function Tab() {
      seen.push(useMemberTab());
      return null;
    }
    const router = createMemoryRouter(
      [
        { path: "/socios/:id", element: createElement(Outlet, { context: { member } satisfies MemberTabContext }), children: [{ path: "/socios/:id/pagos", element: createElement(Tab) }] },
        { path: "/sola", element: createElement(Tab) },
      ],
      { initialEntries: [`/socios/${member.id}/pagos`] },
    );
    render(createElement(RouterProvider, { router }));

    await waitFor(() => {
      expect(seen.at(-1)).toEqual(member);
    });
    await act(async () => {
      await router.navigate("/sola");
    });
    expect(seen.at(-1)).toBeNull();
  });
});

// Fase 4 del Sprint 3 (M3): la búsqueda con espera que comparten la venta y el panel de pagos, y la
// nota de cada resultado (con la fecha de fin de S3-B9b: pendiente 2 de V1).
describe("useMemberSearch", () => {
  it("espera 300 ms, no ofrece a los dados de baja y dice el estado", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const mock = mockApi({ "GET /members": (call) => memberPage(call, [MEMBERS.laura, MEMBERS.andres, MEMBERS.elena]) });
      const { result, rerender } = renderHook(({ text }) => useMemberSearch(text), { wrapper: wrapper(testQueryClient(), []), initialProps: { text: "" } });

      expect(result.current).toEqual({ status: "idle", options: [] });
      rerender({ text: "a" });
      expect(MEMBER_SEARCH_DELAY_MS).toBe(300);
      expect(mock.calls).toHaveLength(0);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(MEMBER_SEARCH_DELAY_MS);
      });
      await waitFor(() => {
        expect(result.current.status).toBe("done");
      });
      expect(result.current.options.map(memberFullName)).toEqual(["Laura Gómez", "Andrés Ruiz"]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("un fallo de la búsqueda es status error", async () => {
    mockApi({ "GET /members": { status: 500, body: { error: { code: "internal_error", message: "x" } } } });
    const { result } = renderHook(() => useMemberSearch("laura", 0), { wrapper: wrapper(testQueryClient(), []) });

    await waitFor(() => {
      expect(result.current.status).toBe("error");
    });
  });
});

describe("memberSearchNote", () => {
  const base = { plan_name: null, membership_status: null, membership_end_date: null };

  it.each([
    [base, "Sin membresía"],
    [{ ...base, membership_status: "none" }, "Sin membresía"],
    [{ ...base, plan_name: "Mensual", membership_status: "active" }, "Mensual · Al día"],
    [{ ...base, plan_name: "Mensual", membership_status: "active", membership_end_date: "2026-10-28" }, "Mensual · Al día · hasta el 28 oct 2026"],
    [{ ...base, plan_name: "12 clases", membership_status: "estado_nuevo", membership_end_date: "2026-11-02" }, "12 clases · hasta el 2 nov 2026"],
  ])("%j → %s", (option, text) => {
    expect(memberSearchNote(option)).toBe(text);
  });
});

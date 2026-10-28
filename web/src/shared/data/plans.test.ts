// S3-F3 (S3-D65): usePlans y planRowSchema se mueven de features/plans a shared/data sin cambiar
// su comportamiento; features/plans los reexporta (PlansPage sigue igual).
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import * as plansApi from "../../features/plans/api";
import * as plansSchemas from "../../features/plans/schemas";
import { PLANS, planPage } from "../../test/plans";
import { mockApi, testQueryClient } from "../../test/server";
import { PLAN_KINDS, planRowSchema, plansPageSchema, plansQueryKey, PLANS_QUERY_KEY, plansShownNote, usePlans } from "./plans";

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("usePlans (shared/data)", () => {
  it("con { active: true } pide solo los planes activos y valida la página", async () => {
    const mock = mockApi({ "GET /plans": (call) => planPage(call, [PLANS.mensual]) });
    const { result } = renderHook(() => usePlans({ limit: 100, offset: 0, active: true }), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(new URL(mock.calls[0]?.url ?? "", "http://apex.test").searchParams.toString()).toBe("limit=100&offset=0&active=true");
    expect(result.current.data?.items.map((p) => p.name)).toEqual(["Mensual"]);
  });

  it("un precio con decimales es invalid_response", async () => {
    mockApi({ "GET /plans": (call) => planPage(call, [{ ...PLANS.mensual, price_cop: 1.5 }]) });
    const { result } = renderHook(() => usePlans({ limit: 25, offset: 0 }), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ code: "invalid_response" });
  });

  it("la clave es ['plans', params], bajo ['plans']", () => {
    expect(plansQueryKey({ limit: 25, offset: 0 })).toEqual(["plans", { limit: 25, offset: 0 }]);
    expect(PLANS_QUERY_KEY).toEqual(["plans"]);
  });
});

describe("reexportación desde features/plans", () => {
  it("features/plans/api.ts y schemas.ts entregan los mismos objetos que shared/data/plans.ts", () => {
    expect(plansApi.usePlans).toBe(usePlans);
    expect(plansApi.plansQueryKey).toBe(plansQueryKey);
    expect(plansApi.PLANS_QUERY_KEY).toBe(PLANS_QUERY_KEY);
    expect(plansSchemas.planRowSchema).toBe(planRowSchema);
    expect(plansSchemas.plansPageSchema).toBe(plansPageSchema);
    expect(plansSchemas.PLAN_KINDS).toBe(PLAN_KINDS);
  });
});

// Fase 4 del Sprint 3 (L8): una lista de planes cortada por `limit` lo dice (la venta pide 100 y los
// filtros de Membresías y Socios 200); antes los demás desaparecían en silencio.
describe("plansShownNote", () => {
  it("null mientras no hay página o cuando trae todos", () => {
    expect(plansShownNote(undefined)).toBeNull();
    expect(plansShownNote({ items: [PLANS.mensual], total: 1, limit: 100, offset: 0 })).toBeNull();
  });

  it("dice cuántos se muestran de cuántos y qué hacer", () => {
    expect(plansShownNote({ items: [PLANS.mensual, PLANS.clases], total: 230, limit: 2, offset: 0 })).toBe("Se muestran 2 de 230 planes. Si falta el que buscas, avísale a un administrador.");
  });
});

// S3-F4 (E10, S3-D65, S3-D66): datos de membresías compartidos. useMembershipSummary (GET
// /memberships/summary, cinco enteros), useMemberOpenMemberships (las no anuladas ni vencidas de un
// socio, con `paid_cop`) y useMembershipOption (una membresía por su id, para el panel de pagos).
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import * as membershipSchemas from "../../features/memberships/schemas";
import type { components } from "../../core/api/types";
import { MEMBERS } from "../../test/members";
import { MEMBERSHIP_ID, membershipOut, membershipRow, membershipRowsPage, membershipSummary } from "../../test/memberships";
import { mockApi, testQueryClient } from "../../test/server";
import {
  FREEZABLE_MEMBERSHIP_STATUSES,
  isFreezableMembershipStatus,
  isOpenMembershipStatus,
  MEMBERSHIP_STATUSES,
  memberMembershipsKey,
  MEMBERSHIPS_SUMMARY_QUERY_KEY,
  membershipOutSchema,
  OPEN_MEMBERSHIP_STATUSES,
  useMemberMemberships,
  useMemberOpenMemberships,
  useMembershipOption,
  useMembershipSummary,
} from "./memberships";

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useMembershipSummary", () => {
  it("lee los cinco enteros de GET /memberships/summary con la clave ['memberships-summary']", async () => {
    const mock = mockApi({ "GET /memberships/summary": { status: 200, body: membershipSummary() } });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => useMembershipSummary(), { wrapper: wrapper(queryClient) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toEqual({ active: 210, expiring: 18, expired: 12, frozen: 3, pending_payment: 5 });
    expect(mock.callsTo("GET /memberships/summary")).toHaveLength(1);
    expect(queryClient.getQueryData(MEMBERSHIPS_SUMMARY_QUERY_KEY)).toEqual(result.current.data);
  });

  it.each([
    ["un decimal", { ...membershipSummary(), active: 1.5 }],
    ["un negativo", { ...membershipSummary(), expired: -1 }],
    ["una clave de más", { ...membershipSummary(), cancelled: 2 }],
    ["una clave de menos", { active: 1, expiring: 1, expired: 1, frozen: 1 }],
  ])("%s es invalid_response", async (_case, body) => {
    mockApi({ "GET /memberships/summary": { status: 200, body } });
    const { result } = renderHook(() => useMembershipSummary(), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ code: "invalid_response" });
  });
});

describe("useMemberOpenMemberships", () => {
  it("pide las membresías abiertas del socio: member_id y los cuatro estados separados por comas", async () => {
    const mock = mockApi({ "GET /memberships": membershipRowsPage([membershipRow()]) });
    const { result } = renderHook(() => useMemberOpenMemberships(MEMBERS.laura.id), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const url = new URL(mock.callsTo("GET /memberships")[0]?.url ?? "", "http://apex.test");
    expect(url.searchParams.get("member_id")).toBe(MEMBERS.laura.id);
    expect(url.searchParams.get("status")).toBe("active,expiring,frozen,pending_payment");
    expect(url.searchParams.get("limit")).toBe("20");
    expect(url.searchParams.get("offset")).toBe("0");
    expect(result.current.data).toEqual([membershipRow()]);
    expect(OPEN_MEMBERSHIP_STATUSES).toEqual(["active", "expiring", "frozen", "pending_payment"]);
  });

  it("sin socio no pide nada", () => {
    const mock = mockApi({});
    const { result } = renderHook(() => useMemberOpenMemberships(null), { wrapper: wrapper(testQueryClient()) });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mock.calls).toHaveLength(0);
  });

  it("una fila con un estado desconocido o un monto decimal es invalid_response", async () => {
    mockApi({ "GET /memberships": membershipRowsPage([membershipRow({ status: "paused" as never })]) });
    const bad = renderHook(() => useMemberOpenMemberships(MEMBERS.laura.id), { wrapper: wrapper(testQueryClient()) });
    await waitFor(() => {
      expect(bad.result.current.isError).toBe(true);
    });

    mockApi({ "GET /memberships": membershipRowsPage([membershipRow({ paid_cop: 10.5 })]) });
    const decimal = renderHook(() => useMemberOpenMemberships(MEMBERS.laura.id), { wrapper: wrapper(testQueryClient()) });
    await waitFor(() => {
      expect(decimal.result.current.isError).toBe(true);
    });
  });
});

describe("useMembershipOption", () => {
  it("lee GET /memberships/{id} y se queda con los campos de la fila (sin congelaciones ni motivo)", async () => {
    const mock = mockApi({ [`GET /memberships/${MEMBERSHIP_ID}`]: { status: 200, body: membershipOut({ status: "pending_payment", paid_cop: 60_000 }) } });
    const { result } = renderHook(() => useMembershipOption(MEMBERSHIP_ID), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(mock.callsTo(`GET /memberships/${MEMBERSHIP_ID}`)).toHaveLength(1);
    expect(result.current.data).toMatchObject({ id: MEMBERSHIP_ID, member_name: "Laura Gómez", plan_name: "Mensual", agreed_price_cop: 120_000, paid_cop: 60_000, status: "pending_payment" });
    expect(result.current.data).not.toHaveProperty("freezes");
  });

  it("sin id no pide nada", () => {
    const mock = mockApi({});
    renderHook(() => useMembershipOption(null), { wrapper: wrapper(testQueryClient()) });

    expect(mock.calls).toHaveLength(0);
  });
});

it("features/memberships reexporta los estados de shared/data (una sola lista)", () => {
  expect(membershipSchemas.MEMBERSHIP_STATUSES).toBe(MEMBERSHIP_STATUSES);
});

// S3-F7 · US-093 (front): las membresías de un socio para la pestaña de la ficha (B11).
describe("useMemberMemberships", () => {
  const ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const PATH = `GET /members/${ID}/memberships`;
  const page = (items: unknown[], total = items.length) => ({ status: 200, body: { items, total, limit: 25, offset: 0 } });

  it("pide GET /members/{id}/memberships con limit y offset, sin q, y valida MembershipOut con sus congelaciones", async () => {
    const freeze = { id: "f0000000-0000-4000-8000-000000000001", frozen_from: "2026-10-01", frozen_to: "2026-10-05", days: 5, created_at: "2026-10-01T15:00:00Z" };
    const mock = mockApi({ [PATH]: page([membershipOut({ member_id: ID, freezes: [freeze] })], 3) });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => useMemberMemberships(ID, { limit: 25, offset: 0 }), { wrapper: wrapper(queryClient) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const url = new URL(mock.callsTo(PATH)[0]?.url ?? "", "http://apex.test");
    expect(url.searchParams.get("limit")).toBe("25");
    expect(url.searchParams.get("offset")).toBe("0");
    expect(url.searchParams.has("q")).toBe(false);
    expect(result.current.data?.total).toBe(3);
    expect(result.current.data?.items[0]?.freezes).toEqual([freeze]);
    expect(queryClient.getQueryData(memberMembershipsKey(ID, { limit: 25, offset: 0 }))).toEqual(result.current.data);
  });

  it("con q la envía (nombre del plan) y la clave la lleva; otra página es otra clave", async () => {
    const mock = mockApi({ [PATH]: page([]) });
    const { result } = renderHook(() => useMemberMemberships(ID, { limit: 50, offset: 50 }, "mensual"), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const url = new URL(mock.callsTo(PATH)[0]?.url ?? "", "http://apex.test");
    expect(url.searchParams.get("q")).toBe("mensual");
    expect(url.searchParams.get("limit")).toBe("50");
    expect(url.searchParams.get("offset")).toBe("50");
    expect(memberMembershipsKey(ID, { limit: 50, offset: 50 }, "mensual")).toEqual(["memberships", "member", ID, { limit: 50, offset: 50, q: "mensual" }]);
    expect(memberMembershipsKey(ID, { limit: 25, offset: 0 })).toEqual(["memberships", "member", ID, { limit: 25, offset: 0 }]);
  });

  it("sin socio no pide nada", () => {
    const mock = mockApi({});
    const { result } = renderHook(() => useMemberMemberships(null, { limit: 25, offset: 0 }), { wrapper: wrapper(testQueryClient()) });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mock.calls).toHaveLength(0);
  });

  it.each([
    ["un campo de más", { ...membershipOut(), extra: true }],
    ["un estado desconocido", membershipOut({ status: "paused" as never })],
    ["un monto decimal", membershipOut({ paid_cop: 1.5 })],
    ["una congelación con días decimales", membershipOut({ freezes: [{ id: "f1", frozen_from: "2026-10-01", frozen_to: "2026-10-05", days: 2.5, created_at: "2026-10-01T15:00:00Z" }] })],
  ])("%s es invalid_response", async (_case, row) => {
    mockApi({ [PATH]: page([row]) });
    const { result } = renderHook(() => useMemberMemberships(ID, { limit: 25, offset: 0 }), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ code: "invalid_response" });
  });

  it("un 404 del socio llega como error del api", async () => {
    mockApi({ [PATH]: { status: 404, body: { error: { code: "member_not_found", message: "No existe." } } } });
    const { result } = renderHook(() => useMemberMemberships(ID, { limit: 25, offset: 0 }), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ status: 404, code: "member_not_found" });
  });
});

it("S3-F7: features/memberships reexporta MembershipOut de shared/data (un solo esquema)", () => {
  expect(membershipSchemas.membershipOutSchema).toBe(membershipOutSchema);
});

describe("revisión S3-F7 (M1): la página anterior se conserva solo para el mismo socio", () => {
  const A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

  it("otra página del mismo socio muestra la anterior mientras llega; otro socio no hereda nada", async () => {
    mockApi({
      [`GET /members/${A}/memberships`]: (call) => {
        const offset = new URL(call.url, "http://apex.test").searchParams.get("offset");
        return offset === "0" ? { status: 200, body: { items: [membershipOut({ member_id: A })], total: 30, limit: 25, offset: 0 } } : new Promise(() => undefined);
      },
      [`GET /members/${B}/memberships`]: () => new Promise(() => undefined),
    });
    const { result, rerender } = renderHook(({ id, offset }: { id: string; offset: number }) => useMemberMemberships(id, { limit: 25, offset }), {
      wrapper: wrapper(testQueryClient()),
      initialProps: { id: A, offset: 0 },
    });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    rerender({ id: A, offset: 25 });
    expect(result.current.isPlaceholderData).toBe(true);
    expect(result.current.data?.items[0]?.member_id).toBe(A);

    rerender({ id: B, offset: 0 });
    expect(result.current.data).toBeUndefined();
  });
});

// Fase 4 del Sprint 3 (L1 y M4): los estados salen del contrato y las reglas que los agrupan viven aquí.
describe("estados de membresía del contrato", () => {
  it("MEMBERSHIP_STATUSES cubre exactamente el enum MembershipStatus del contrato", () => {
    expectTypeOf<(typeof MEMBERSHIP_STATUSES)[number]>().toEqualTypeOf<components["schemas"]["MembershipStatus"]>();
    expect(new Set(MEMBERSHIP_STATUSES).size).toBe(6);
  });

  it.each(MEMBERSHIP_STATUSES)("isOpenMembershipStatus(%s) sigue a OPEN_MEMBERSHIP_STATUSES", (status) => {
    expect(isOpenMembershipStatus(status)).toBe((OPEN_MEMBERSHIP_STATUSES as readonly string[]).includes(status));
  });

  it("solo se congelan las al día o por vencer", () => {
    expect(FREEZABLE_MEMBERSHIP_STATUSES).toEqual(["active", "expiring"]);
    expect(MEMBERSHIP_STATUSES.filter(isFreezableMembershipStatus)).toEqual(["active", "expiring"]);
  });
});

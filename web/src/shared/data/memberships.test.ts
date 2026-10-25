// S3-F4 (E10, S3-D65, S3-D66): datos de membresías compartidos. useMembershipSummary (GET
// /memberships/summary, cinco enteros), useMemberOpenMemberships (las no anuladas ni vencidas de un
// socio, con `paid_cop`) y useMembershipOption (una membresía por su id, para el panel de pagos).
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import * as membershipSchemas from "../../features/memberships/schemas";
import { MEMBERS } from "../../test/members";
import { MEMBERSHIP_ID, membershipOut, membershipRow, membershipRowsPage, membershipSummary } from "../../test/memberships";
import { mockApi, testQueryClient } from "../../test/server";
import { MEMBERSHIP_STATUSES, MEMBERSHIPS_SUMMARY_QUERY_KEY, OPEN_MEMBERSHIP_STATUSES, useMemberOpenMemberships, useMembershipOption, useMembershipSummary } from "./memberships";

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
    mockApi({ "GET /memberships": membershipRowsPage([membershipRow({ status: "paused" })]) });
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

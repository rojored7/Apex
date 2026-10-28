// S3-F5 · US-089 a US-092 (front): hooks de la lista de membresías y de sus escrituras.
// - useMemberships(params): GET /memberships con la clave ["memberships", "list", params] (los
//   filtros forman parte de la clave), filas estrictas (MembershipRow, D35), la página anterior
//   mientras llega la nueva (keepPreviousData) y, con `q`, sin caché al dejar de usarse (S2-D41).
// - useMembership(id): GET /memberships/{id} (MembershipOut con el estado efectivo, B7).
// - useFreezeMembership y useCancelMembership: POST de congelar y anular; `gcTime: 0` y `reset()`
//   al terminar (S3-D52). Al salir bien invalidan ["memberships"], ["memberships-summary"] y
//   ["members"]; un 409 o un 404 también releen la lista (lo que se ve quedó viejo).
import { focusManager, QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { MEMBERS } from "../../test/members";
import { INVALIDATE_AFTER_PAYMENT } from "../../shared/data/payments";
import { apiError, cancelKey, ELENA_MEMBERSHIP_ID, freezeKey, MEMBERSHIP_ID, MEMBERSHIP_ROWS, membershipOut, membershipRow, membershipsPage, previewKey, renewalPreview, sellKey, sellMembershipOut } from "../../test/memberships";
import { mockApi, testQueryClient } from "../../test/server";
import { MEMBERSHIP_WRITE_INVALIDATES, membershipQueryKey, membershipsQueryKey, renewalPreviewKey, SELL_INVALIDATES, useCancelMembership, useFreezeMembership, useMembership, useMemberships, useRenewalPreview, useSellMembership, type MembershipsParams } from "./api";

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

const PARAMS: MembershipsParams = { limit: 25, offset: 50, status: "active,expiring", plan_id: "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa", ends_from: "2026-10-01", ends_to: "2026-10-31" };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useMemberships", () => {
  it("pide GET /memberships con los filtros (status separado por comas) y guarda la página bajo una clave con ellos", async () => {
    const mock = mockApi({ "GET /memberships": (call) => membershipsPage(call) });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => useMemberships(PARAMS), { wrapper: wrapper(queryClient) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const query = new URL(mock.callsTo("GET /memberships")[0]?.url ?? "", "http://apex.test").searchParams;
    expect(Object.fromEntries(query)).toEqual({
      limit: "25",
      offset: "50",
      status: "active,expiring",
      plan_id: "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      ends_from: "2026-10-01",
      ends_to: "2026-10-31",
    });
    expect(membershipsQueryKey(PARAMS)).toEqual(["memberships", "list", PARAMS]);
    expect(queryClient.getQueryData(membershipsQueryKey(PARAMS))).toEqual({ items: MEMBERSHIP_ROWS, total: 3, limit: 25, offset: 50 });
  });

  it("dos filtros distintos son dos claves distintas", () => {
    expect(membershipsQueryKey({ limit: 25, offset: 0, status: "active" })).not.toEqual(membershipsQueryKey({ limit: 25, offset: 0, status: "frozen" }));
  });

  it("una fila con un campo de más es invalid_response (D35)", async () => {
    mockApi({ "GET /memberships": { status: 200, body: { items: [{ ...membershipRow(), document: "123" }], total: 1, limit: 25, offset: 0 } } });
    const { result } = renderHook(() => useMemberships({ limit: 25, offset: 0 }), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ code: "invalid_response" });
  });

  it("mientras llega la página nueva conserva la anterior (keepPreviousData)", async () => {
    let release: () => void = () => undefined;
    mockApi({
      "GET /memberships": (call) =>
        new URL(call.url, "http://apex.test").searchParams.get("offset") === "0"
          ? membershipsPage(call)
          : new Promise((resolve) => {
              release = () => {
                resolve(membershipsPage(call, []));
              };
            }),
    });
    const { result, rerender } = renderHook((params: MembershipsParams) => useMemberships(params), {
      wrapper: wrapper(testQueryClient()),
      initialProps: { limit: 25, offset: 0 },
    });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    rerender({ limit: 25, offset: 25 });

    expect(result.current.isPlaceholderData).toBe(true);
    expect(result.current.data?.items).toHaveLength(3);
    release();
  });

  it("con búsqueda no deja la página en la caché al dejar de usarse (S2-D41)", async () => {
    mockApi({ "GET /memberships": (call) => membershipsPage(call) });
    const queryClient = testQueryClient();
    const params = { limit: 25, offset: 0, q: "gómez" };
    const { result, unmount } = renderHook(() => useMemberships(params), { wrapper: wrapper(queryClient) });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    unmount();

    await waitFor(() => {
      expect(queryClient.getQueryData(membershipsQueryKey(params))).toBeUndefined();
    });
  });
});

describe("useMembership", () => {
  it("lee GET /memberships/{id} con la clave ['memberships', 'detail', id]", async () => {
    const body = membershipOut();
    mockApi({ [`GET /memberships/${MEMBERSHIP_ID}`]: { status: 200, body } });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => useMembership(MEMBERSHIP_ID), { wrapper: wrapper(queryClient) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toEqual(body);
    expect(queryClient.getQueryData(membershipQueryKey(MEMBERSHIP_ID))).toEqual(body);
  });

  it("sin id no pide nada", () => {
    const mock = mockApi({});
    renderHook(() => useMembership(null), { wrapper: wrapper(testQueryClient()) });

    expect(mock.calls).toHaveLength(0);
  });
});

describe("useFreezeMembership", () => {
  it("POST /memberships/{id}/freeze con las dos fechas; al salir bien invalida membresías, su resumen y socios", async () => {
    const frozen = membershipOut({ id: ELENA_MEMBERSHIP_ID, member_id: MEMBERS.elena.id, status: "frozen", end_date: "2026-11-10" });
    const mock = mockApi({ [freezeKey()]: { status: 200, body: frozen } });
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useFreezeMembership(), { wrapper: wrapper(queryClient) });

    let out: unknown;
    await act(async () => {
      out = await result.current.freeze({ id: ELENA_MEMBERSHIP_ID, frozen_from: "2026-10-28", frozen_to: "2026-11-06" });
    });

    expect(out).toEqual(frozen);
    expect(mock.callsTo(freezeKey()).map((c) => c.body)).toEqual([{ frozen_from: "2026-10-28", frozen_to: "2026-11-06" }]);
    expect(MEMBERSHIP_WRITE_INVALIDATES).toEqual([["memberships"], ["memberships-summary"], ["members"]]);
    expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([["memberships"], ["memberships-summary"], ["members"]]);
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
  });

  it.each([
    [409, "membership_not_freezable"],
    [404, "membership_not_found"],
  ])("un %i relee la lista y el resumen (lo que se ve quedó viejo)", async (status, code) => {
    mockApi({ [freezeKey()]: apiError(status, code) });
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useFreezeMembership(), { wrapper: wrapper(queryClient) });

    await act(async () => {
      await expect(result.current.freeze({ id: ELENA_MEMBERSHIP_ID, frozen_from: "2026-10-28", frozen_to: "2026-11-06" })).rejects.toMatchObject({ status, code });
    });

    expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([["memberships"], ["memberships-summary"]]);
  });

  it("un 422 no relee nada y la caché de mutaciones queda vacía", async () => {
    mockApi({ [freezeKey()]: apiError(422, "freeze_too_retroactive", { field: "frozen_from" }) });
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useFreezeMembership(), { wrapper: wrapper(queryClient) });

    await act(async () => {
      await expect(result.current.freeze({ id: ELENA_MEMBERSHIP_ID, frozen_from: "2026-01-01", frozen_to: "2026-01-02" })).rejects.toMatchObject({ status: 422 });
    });

    expect(invalidate).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
  });
});

describe("useCancelMembership", () => {
  it("POST /memberships/{id}/cancel con el motivo; al salir bien invalida membresías, su resumen y socios", async () => {
    const cancelled = membershipOut({ id: ELENA_MEMBERSHIP_ID, status: "cancelled" });
    const mock = mockApi({ [cancelKey()]: { status: 200, body: cancelled } });
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useCancelMembership(), { wrapper: wrapper(queryClient) });

    await act(async () => {
      await result.current.cancel({ id: ELENA_MEMBERSHIP_ID, reason: "Vendida por error" });
    });

    expect(mock.callsTo(cancelKey()).map((c) => c.body)).toEqual([{ reason: "Vendida por error" }]);
    expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([["memberships"], ["memberships-summary"], ["members"]]);
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
  });

  it("un 409 membership_already_cancelled relee la lista y el resumen", async () => {
    mockApi({ [cancelKey()]: apiError(409, "membership_already_cancelled") });
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useCancelMembership(), { wrapper: wrapper(queryClient) });

    await act(async () => {
      await expect(result.current.cancel({ id: ELENA_MEMBERSHIP_ID, reason: "Vendida por error" })).rejects.toMatchObject({ code: "membership_already_cancelled" });
    });

    expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([["memberships"], ["memberships-summary"]]);
  });

  it("una respuesta que no es MembershipOut es invalid_response", async () => {
    mockApi({ [cancelKey()]: { status: 200, body: { ok: true } } });
    const { result } = renderHook(() => useCancelMembership(), { wrapper: wrapper(testQueryClient()) });

    await act(async () => {
      await expect(result.current.cancel({ id: ELENA_MEMBERSHIP_ID, reason: "Vendida por error" })).rejects.toMatchObject({ code: "invalid_response" });
    });
  });
});

// Fase 4 del Sprint 3 (M1): vender con primer pago deja viejo el total del mes de /pagos; la venta
// y el registro de pagos invalidan la misma lista (shared/data/payments.ts).
describe("useSellMembership", () => {
  it("al salir bien invalida todo lo que deja viejo un pago, también ['payments-summary']", async () => {
    mockApi({ [sellKey()]: { status: 201, body: sellMembershipOut({ first_payment_id: "12121212-1212-4121-8121-121212121212", paid_cop: 120_000 }) } });
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useSellMembership(MEMBERS.laura.id), { wrapper: wrapper(queryClient) });

    await act(async () => {
      await result.current.sell({ plan_id: "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa", renew: false, start_date: "2026-10-28" });
    });

    expect(SELL_INVALIDATES).toBe(INVALIDATE_AFTER_PAYMENT);
    expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([["payments"], ["payments-summary"], ["memberships"], ["memberships-summary"], ["members"]]);
  });
});

// Fase 4 del Sprint 3 (L5): la vista previa de la renovación tiene su propia clave; invalidar
// ["memberships"] (vender, pagar, congelar) no la pide de nuevo.
describe("useRenewalPreview", () => {
  it("usa la clave ['renewal-preview', socio, plan] y no se relee al invalidar ['memberships']", async () => {
    const mock = mockApi({ [previewKey()]: { status: 200, body: renewalPreview() } });
    const queryClient = testQueryClient();
    const planId = "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    const { result } = renderHook(() => useRenewalPreview(MEMBERS.laura.id, planId), { wrapper: wrapper(queryClient) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(renewalPreviewKey(MEMBERS.laura.id, planId)).toEqual(["renewal-preview", MEMBERS.laura.id, planId]);
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: ["memberships"] });
    });
    expect(mock.callsTo(previewKey())).toHaveLength(1);
  });
});

// Revisión final de la Fase 4 (LOW 3): tras vender, la vista previa sigue montada bajo "Venta
// registrada"; volver a la ventana no la pide de nuevo (podría responder 409 y bloquear la venta).
describe("useRenewalPreview · foco de la ventana", () => {
  it("no se relee al volver a la ventana", async () => {
    const mock = mockApi({ [previewKey()]: { status: 200, body: renewalPreview() } });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => useRenewalPreview(MEMBERS.laura.id, "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa"), { wrapper: wrapper(queryClient) });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    await act(async () => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
      await new Promise((resolve) => setTimeout(resolve, 20));
    });

    expect(mock.callsTo(previewKey())).toHaveLength(1);
    focusManager.setFocused(undefined);
  });
});

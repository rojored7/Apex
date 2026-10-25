// S3-F4 · US-095 y US-097 (front): hooks de pagos que no cubren los componentes. usePayment (GET
// /payments/{id}, B8) valida el detalle; useVoidPayment relee los pagos tras un 409 o un 404; los
// medios se reexportan en el orden del api.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { apiError } from "../../test/memberships";
import { PAYMENT_ID, PAYMENT_METHODS, paymentDetail, paymentMethods } from "../../test/payments";
import { mockApi, testQueryClient } from "../../test/server";
import { paymentQueryKey, usePayment, usePaymentMethods, useRegisterPayment, useVoidPayment } from "./api";

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("usePayment", () => {
  it("lee GET /payments/{id} con la clave ['payments', 'detail', id]", async () => {
    mockApi({ [`GET /payments/${PAYMENT_ID}`]: { status: 200, body: paymentDetail({ backdated: true }) } });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => usePayment(PAYMENT_ID), { wrapper: wrapper(queryClient) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data).toMatchObject({ id: PAYMENT_ID, backdated: true, registered_by_name: "c•••@apex.test" });
    expect(queryClient.getQueryData(paymentQueryKey(PAYMENT_ID))).toEqual(result.current.data);
  });

  it("sin id no pide nada; un detalle con un monto decimal es invalid_response", async () => {
    const empty = mockApi({});
    renderHook(() => usePayment(null), { wrapper: wrapper(testQueryClient()) });
    expect(empty.calls).toHaveLength(0);

    mockApi({ [`GET /payments/${PAYMENT_ID}`]: { status: 200, body: paymentDetail({ amount_cop: 1.5 }) } });
    const { result } = renderHook(() => usePayment(PAYMENT_ID), { wrapper: wrapper(testQueryClient()) });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ code: "invalid_response" });
  });
});

describe("useVoidPayment", () => {
  it.each([
    ["409", apiError(409, "payment_already_voided")],
    ["404", apiError(404, "payment_not_found")],
  ])("un %s relee ['payments'] (el pago que se ve quedó viejo)", async (_status, reply) => {
    mockApi({ [`POST /payments/${PAYMENT_ID}/void`]: reply });
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useVoidPayment(), { wrapper: wrapper(queryClient) });

    await act(async () => {
      await expect(result.current.voidPayment({ id: PAYMENT_ID, reason: "Duplicado" })).rejects.toMatchObject({ status: reply.status });
    });

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["payments"] });
  });

  it("un 500 no relee nada", async () => {
    mockApi({ [`POST /payments/${PAYMENT_ID}/void`]: apiError(500, "internal_error") });
    const queryClient = testQueryClient();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useVoidPayment(), { wrapper: wrapper(queryClient) });

    await act(async () => {
      await expect(result.current.voidPayment({ id: PAYMENT_ID, reason: "Duplicado" })).rejects.toMatchObject({ status: 500 });
    });

    expect(invalidate).not.toHaveBeenCalled();
  });
});

describe("useRegisterPayment", () => {
  it("sin membresía no envía nada", async () => {
    const mock = mockApi({});
    const { result } = renderHook(() => useRegisterPayment(null), { wrapper: wrapper(testQueryClient()) });

    await act(async () => {
      await expect(result.current.register({ amount_cop: 1000, method: "cash", confirm_overpayment: false, confirm_duplicate: false })).rejects.toThrow(/membresía/);
    });
    expect(mock.calls).toHaveLength(0);
  });
});

it("los medios de pago se reexportan y llegan en el orden del api", async () => {
  mockApi({ "GET /payments/methods": paymentMethods() });
  const { result } = renderHook(() => usePaymentMethods(), { wrapper: wrapper(testQueryClient()) });

  await waitFor(() => {
    expect(result.current.isSuccess).toBe(true);
  });
  expect(result.current.data?.map((m) => m.code)).toEqual(PAYMENT_METHODS.map((m) => m.code));
});

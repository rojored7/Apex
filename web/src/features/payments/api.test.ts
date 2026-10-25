// S3-F4 · US-095 y US-097 (front): hooks de pagos que no cubren los componentes. usePayment (GET
// /payments/{id}, B8) valida el detalle; useVoidPayment relee los pagos tras un 409 o un 404; los
// medios se reexportan en el orden del api.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { apiError } from "../../test/memberships";
import { PAYMENT_ID, PAYMENT_METHODS, paymentDetail, paymentMethods, paymentOut, paymentRow, paymentsSummary } from "../../test/payments";
import { mockApi, testQueryClient } from "../../test/server";
import {
  paymentQueryKey,
  paymentsQueryKey,
  paymentsSummaryKey,
  usePayment,
  usePaymentMethods,
  usePayments,
  usePaymentsSummary,
  useRegisterPayment,
  useVoidPayment,
  type PaymentsParams,
} from "./api";

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

describe("S3-F6 · usePayments", () => {
  const PARAMS: PaymentsParams = { limit: 25, offset: 0, method: "nequi", voided: false, from: "2026-10-01T05:00:00.000Z", to: "2026-10-21T05:00:00.000Z" };
  const page = (items: unknown[]) => ({ status: 200, body: { items, total: items.length, limit: 25, offset: 0 } });

  it("lee GET /payments con los filtros y guarda la página bajo ['payments', 'list', params]", async () => {
    const mock = mockApi({ "GET /payments": page([paymentRow()]) });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => usePayments(PARAMS), { wrapper: wrapper(queryClient) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const url = new URL(mock.calls[0]?.url ?? "", "http://apex.test");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      limit: "25",
      offset: "0",
      method: "nequi",
      voided: "false",
      from: "2026-10-01T05:00:00.000Z",
      to: "2026-10-21T05:00:00.000Z",
    });
    expect(paymentsQueryKey(PARAMS)).toEqual(["payments", "list", PARAMS]);
    expect(queryClient.getQueryData(paymentsQueryKey(PARAMS))).toEqual(result.current.data);
  });

  it("una fila con un campo de más es invalid_response", async () => {
    mockApi({ "GET /payments": page([{ ...paymentRow(), extra: 1 }]) });
    const { result } = renderHook(() => usePayments({ limit: 25, offset: 0 }), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ code: "invalid_response" });
  });

  it("mientras llega la página nueva conserva la anterior", () => {
    mockApi({ "GET /payments": () => new Promise<never>(() => undefined) });
    const queryClient = testQueryClient();
    queryClient.setQueryData(paymentsQueryKey({ limit: 25, offset: 0 }), { items: [paymentRow()], total: 30, limit: 25, offset: 0 });
    const { result, rerender } = renderHook(({ params }: { params: PaymentsParams }) => usePayments(params), {
      wrapper: wrapper(queryClient),
      initialProps: { params: { limit: 25, offset: 0 } },
    });
    expect(result.current.data?.items).toHaveLength(1);

    rerender({ params: { limit: 25, offset: 25 } });

    expect(result.current.isPlaceholderData).toBe(true);
    expect(result.current.data?.items).toHaveLength(1);
  });

  it("con q no deja la búsqueda en la caché al dejar de usarla (S2-D41)", async () => {
    mockApi({ "GET /payments": page([]) });
    const queryClient = testQueryClient();
    const params: PaymentsParams = { limit: 25, offset: 0, q: "M12345678" };
    const { result, unmount } = renderHook(() => usePayments(params), { wrapper: wrapper(queryClient) });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    unmount();

    await waitFor(() => {
      expect(queryClient.getQueryData(paymentsQueryKey(params))).toBeUndefined();
    });
  });
});

describe("S3-F6 · usePaymentsSummary", () => {
  it("lee GET /payments/summary?month= con la clave ['payments-summary', month]", async () => {
    const mock = mockApi({ "GET /payments/summary": { status: 200, body: paymentsSummary() } });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => usePaymentsSummary("2026-10"), { wrapper: wrapper(queryClient) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(new URL(mock.calls[0]?.url ?? "", "http://apex.test").searchParams.get("month")).toBe("2026-10");
    expect(paymentsSummaryKey("2026-10")).toEqual(["payments-summary", "2026-10"]);
    expect(queryClient.getQueryData(paymentsSummaryKey("2026-10"))).toEqual(paymentsSummary());
  });

  it("un resumen con un medio de más es invalid_response", async () => {
    mockApi({ "GET /payments/summary": { status: 200, body: { ...paymentsSummary(), by_method: { cash: 0, nequi: 0, breb: 0, card: 0 } } } });
    const { result } = renderHook(() => usePaymentsSummary("2026-10"), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ code: "invalid_response" });
  });

  it("anular un pago relee el resumen del mes (la clave empieza por 'payments-summary')", async () => {
    let summaries = 0;
    mockApi({
      "GET /payments/summary": () => {
        summaries += 1;
        return { status: 200, body: paymentsSummary() };
      },
      [`POST /payments/${PAYMENT_ID}/void`]: { status: 200, body: paymentOut({ id: PAYMENT_ID, voided: true, void_reason: "Duplicado" }) },
    });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => ({ summary: usePaymentsSummary("2026-10"), write: useVoidPayment() }), { wrapper: wrapper(queryClient) });
    await waitFor(() => {
      expect(result.current.summary.isSuccess).toBe(true);
    });

    await act(async () => {
      await result.current.write.voidPayment({ id: PAYMENT_ID, reason: "Duplicado" });
    });

    await waitFor(() => {
      expect(summaries).toBe(2);
    });
  });
});

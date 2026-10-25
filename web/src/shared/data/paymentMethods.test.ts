// S3-F3 (S3-D65): medios de pago con su etiqueta (US-056, D24, D25).
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import * as paymentsApi from "../../features/payments/api";
import { PAYMENT_METHODS, paymentMethods } from "../../test/payments";
import { mockApi, testQueryClient } from "../../test/server";
import { PAYMENT_METHODS_STALE_MS, usePaymentMethods } from "./paymentMethods";

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("usePaymentMethods", () => {
  it("lee `items` de GET /payments/methods en el orden del api", async () => {
    const reordered = [PAYMENT_METHODS[2], PAYMENT_METHODS[0], PAYMENT_METHODS[1]].filter((m) => m !== undefined);
    mockApi({ "GET /payments/methods": paymentMethods(reordered) });
    const { result } = renderHook(() => usePaymentMethods(), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    expect(result.current.data?.map((m) => m.code)).toEqual(["breb", "cash", "nequi"]);
    expect(result.current.data?.[0]).toEqual({ code: "breb", label: "Bre-B", hint: "Referencia de la transferencia" });
  });

  it("dura 5 minutos fresca: un segundo uso no vuelve a pedir", async () => {
    const mock = mockApi({ "GET /payments/methods": paymentMethods() });
    const queryClient = testQueryClient();
    const first = renderHook(() => usePaymentMethods(), { wrapper: wrapper(queryClient) });
    await waitFor(() => {
      expect(first.result.current.isSuccess).toBe(true);
    });

    const second = renderHook(() => usePaymentMethods(), { wrapper: wrapper(queryClient) });

    expect(second.result.current.data).toHaveLength(3);
    expect(mock.callsTo("GET /payments/methods")).toHaveLength(1);
    expect(PAYMENT_METHODS_STALE_MS).toBe(300_000);
  });

  it("un medio fuera de los tres fijos o un arreglo suelto es invalid_response", async () => {
    mockApi({ "GET /payments/methods": { status: 200, body: { items: [{ code: "card", label: "Tarjeta", hint: "" }] } } });
    const bad = renderHook(() => usePaymentMethods(), { wrapper: wrapper(testQueryClient()) });
    await waitFor(() => {
      expect(bad.result.current.isError).toBe(true);
    });
    expect(bad.result.current.error).toMatchObject({ code: "invalid_response" });

    mockApi({ "GET /payments/methods": { status: 200, body: PAYMENT_METHODS } });
    const bare = renderHook(() => usePaymentMethods(), { wrapper: wrapper(testQueryClient()) });
    await waitFor(() => {
      expect(bare.result.current.isError).toBe(true);
    });
  });

  it("features/payments/api.ts reexporta el mismo hook", () => {
    expect(paymentsApi.usePaymentMethods).toBe(usePaymentMethods);
  });
});

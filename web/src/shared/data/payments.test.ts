// S3-F7 · US-101 (front): los pagos de un socio para la pestaña Pagos de la ficha (B11) y la fila de
// pagos compartida (S3-D65: features/payments la reexporta).
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import * as paymentSchemas from "../../features/payments/schemas";
import { paymentRow } from "../../test/payments";
import { mockApi, testQueryClient } from "../../test/server";
import { memberPaymentsKey, paymentRowSchema, paymentsPageSchema, useMemberPayments } from "./payments";

const ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const PATH = `GET /members/${ID}/payments`;

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

const page = (items: unknown[], total = items.length) => ({ status: 200, body: { items, total, limit: 25, offset: 0 } });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useMemberPayments", () => {
  it("pide GET /members/{id}/payments con limit y offset y sin `voided` cuando trae todos", async () => {
    const mock = mockApi({ [PATH]: page([paymentRow({ member_id: ID })], 7) });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => useMemberPayments(ID, { limit: 25, offset: 0 }), { wrapper: wrapper(queryClient) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const url = new URL(mock.callsTo(PATH)[0]?.url ?? "", "http://apex.test");
    expect(url.searchParams.get("limit")).toBe("25");
    expect(url.searchParams.get("offset")).toBe("0");
    expect(url.searchParams.has("voided")).toBe(false);
    expect(url.searchParams.has("q")).toBe(false);
    expect(result.current.data?.total).toBe(7);
    expect(result.current.data?.items[0]).toMatchObject({ member_id: ID, backdated: false, voided: false });
    expect(queryClient.getQueryData(memberPaymentsKey(ID, { limit: 25, offset: 0 }))).toEqual(result.current.data);
  });

  it("'Ocultar anulados' envía voided=false; la clave lleva los parámetros y vive bajo ['payments']", async () => {
    const mock = mockApi({ [PATH]: page([]) });
    const { result } = renderHook(() => useMemberPayments(ID, { voided: false, limit: 50, offset: 50 }), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const url = new URL(mock.callsTo(PATH)[0]?.url ?? "", "http://apex.test");
    expect(url.searchParams.get("voided")).toBe("false");
    expect(url.searchParams.get("limit")).toBe("50");
    expect(url.searchParams.get("offset")).toBe("50");
    expect(memberPaymentsKey(ID, { voided: false, limit: 50, offset: 50 })).toEqual(["payments", "member", ID, { voided: false, limit: 50, offset: 50 }]);
  });

  it("sin socio no pide nada", () => {
    const mock = mockApi({});
    const { result } = renderHook(() => useMemberPayments(null, { limit: 25, offset: 0 }), { wrapper: wrapper(testQueryClient()) });

    expect(result.current.fetchStatus).toBe("idle");
    expect(mock.calls).toHaveLength(0);
  });

  it.each([
    ["un campo de más", { ...paymentRow(), extra: 1 }],
    ["un medio desconocido", { ...paymentRow(), method: "card" }],
    ["un monto decimal", paymentRow({ amount_cop: 10.5 })],
    ["sin `backdated`", Object.fromEntries(Object.entries(paymentRow()).filter(([key]) => key !== "backdated"))],
  ])("%s es invalid_response", async (_case, row) => {
    mockApi({ [PATH]: page([row]) });
    const { result } = renderHook(() => useMemberPayments(ID, { limit: 25, offset: 0 }), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ code: "invalid_response" });
  });
});

describe("paymentRowSchema (compartido)", () => {
  it("features/payments reexporta la fila y la página de shared/data (un solo esquema)", () => {
    expect(paymentSchemas.paymentRowSchema).toBe(paymentRowSchema);
    expect(paymentSchemas.paymentsPageSchema).toBe(paymentsPageSchema);
  });

  it("acepta `registered_by_name` y `void_reason` en null y exige un monto de al menos $ 1", () => {
    expect(paymentRowSchema.safeParse(paymentRow({ registered_by_name: null, void_reason: null })).success).toBe(true);
    expect(paymentRowSchema.safeParse(paymentRow({ amount_cop: 0 })).success).toBe(false);
  });
});

it("revisión S3-F7 (M1): al cambiar de socio no se muestran los pagos del anterior", async () => {
  const B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  mockApi({ [PATH]: page([paymentRow({ member_id: ID })]), [`GET /members/${B}/payments`]: () => new Promise(() => undefined) });
  const { result, rerender } = renderHook(({ id }: { id: string }) => useMemberPayments(id, { limit: 25, offset: 0 }), { wrapper: wrapper(testQueryClient()), initialProps: { id: ID } });
  await waitFor(() => {
    expect(result.current.isSuccess).toBe(true);
  });

  rerender({ id: B });
  expect(result.current.data).toBeUndefined();
});

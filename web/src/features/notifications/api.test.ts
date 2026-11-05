// S5-F1 · US-127 y US-128 (front): hooks de "Por avisar hoy".
// - useToday(params): GET /notifications/today con la clave ["notifications", "today", params]; la
//   página se valida con Zod (forma inesperada = invalid_response).
// - useWaLink(): POST /notifications/{id}/wa-link por useMutation con gcTime 0 (S5-D59, M-9): la URL
//   (lleva el teléfono) no queda en la caché de mutaciones ni en la de consultas, y solo se acepta
//   un enlace https://wa.me/. Al terminar relee ["notifications"], también con un 409.
// - useSkip(): POST /notifications/{id}/skip con {reason} recortado; relee ["notifications"].
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { ApiError } from "../../core/api/errors";
import { apiError, NOTIFICATIONS, todayPage, TODAY_ROWS, WA_URL } from "../../test/notifications";
import { mockApi, testQueryClient } from "../../test/server";
import { NOTIFICATIONS_QUERY_KEY, todayQueryKey, useSkip, useToday, useWaLink } from "./api";

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

const JUAN = NOTIFICATIONS.juan;
const WA_KEY = `POST /notifications/${JUAN.id}/wa-link`;
const SKIP_KEY = `POST /notifications/${JUAN.id}/skip`;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useToday", () => {
  it("pide GET /notifications/today con limit y offset y guarda la página bajo su clave", async () => {
    const mock = mockApi({ "GET /notifications/today": (call) => todayPage(call) });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => useToday({ limit: 25, offset: 50 }), { wrapper: wrapper(queryClient) });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
    const query = new URL(mock.callsTo("GET /notifications/today")[0]?.url ?? "", "http://apex.test").searchParams;
    expect(Object.fromEntries(query)).toEqual({ limit: "25", offset: "50" });
    expect(todayQueryKey({ limit: 25, offset: 50 })).toEqual(["notifications", "today", { limit: 25, offset: 50 }]);
    expect(queryClient.getQueryData(todayQueryKey({ limit: 25, offset: 50 }))).toEqual({ items: TODAY_ROWS, total: 4, limit: 25, offset: 50 });
  });

  it("una forma inesperada es una respuesta inválida", async () => {
    mockApi({ "GET /notifications/today": { status: 200, body: { items: [{ id: "x" }], total: 1, limit: 25, offset: 0 } } });
    const { result } = renderHook(() => useToday({ limit: 25, offset: 0 }), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect((result.current.error as ApiError).code).toBe("invalid_response");
  });

  it("un campo que el contrato no declara tampoco pasa (filas estrictas)", async () => {
    mockApi({ "GET /notifications/today": { status: 200, body: { items: [{ ...JUAN, phone: "3201234567" }], total: 1, limit: 25, offset: 0 } } });
    const { result } = renderHook(() => useToday({ limit: 25, offset: 0 }), { wrapper: wrapper(testQueryClient()) });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

describe("useWaLink", () => {
  it("hace POST sin cuerpo y entrega la URL a quien llama; la mutación no se queda en la caché (gcTime 0)", async () => {
    const mock = mockApi({ [WA_KEY]: { status: 200, body: { url: WA_URL } } });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => useWaLink(), { wrapper: wrapper(queryClient) });

    let url: string | undefined;
    await act(async () => {
      url = (await result.current.mutateAsync(JUAN.id)).url;
    });

    expect(url).toBe(WA_URL);
    expect(mock.callsTo(WA_KEY)).toHaveLength(1);
    expect(mock.callsTo(WA_KEY)[0]?.body).toBeUndefined();
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
  });

  it("la URL no queda en el estado de la mutación ni en la caché de consultas (M-9)", async () => {
    mockApi({ [WA_KEY]: { status: 200, body: { url: WA_URL } } });
    const queryClient = testQueryClient();
    const { result } = renderHook(() => useWaLink(), { wrapper: wrapper(queryClient) });

    await act(async () => {
      await result.current.mutateAsync(JUAN.id);
    });

    await waitFor(() => {
      expect(result.current.data).toBeUndefined();
    });
    expect(JSON.stringify(queryClient.getQueryCache().getAll().map((q) => q.state.data))).not.toContain("wa.me");
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
  });

  it("al salir bien invalida ['notifications']", async () => {
    mockApi({ [WA_KEY]: { status: 200, body: { url: WA_URL } } });
    const queryClient = testQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useWaLink(), { wrapper: wrapper(queryClient) });

    await act(async () => {
      await result.current.mutateAsync(JUAN.id);
    });

    expect(spy).toHaveBeenCalledWith({ queryKey: NOTIFICATIONS_QUERY_KEY });
  });

  it.each(["https://evil.example/573201234567", "http://wa.me/573201234567", "https://wa.me.evil.example/57", "javascript:alert(1)"])(
    "rechaza una URL que no es https://wa.me/: %s",
    async (bad) => {
      mockApi({ [WA_KEY]: { status: 200, body: { url: bad } } });
      const { result } = renderHook(() => useWaLink(), { wrapper: wrapper(testQueryClient()) });

      let caught: unknown;
      await act(async () => {
        caught = await result.current.mutateAsync(JUAN.id).catch((e: unknown) => e);
      });

      expect(caught).toBeInstanceOf(ApiError);
      expect((caught as ApiError).code).toBe("invalid_response");
    },
  );

  it("un 422 invalid_phone rechaza con el ApiError del api", async () => {
    mockApi({ [WA_KEY]: apiError(422, "invalid_phone", {}, undefined, "El teléfono del socio no es un celular válido.") });
    const { result } = renderHook(() => useWaLink(), { wrapper: wrapper(testQueryClient()) });

    let caught: unknown;
    await act(async () => {
      caught = await result.current.mutateAsync(JUAN.id).catch((e: unknown) => e);
    });

    expect((caught as ApiError).status).toBe(422);
    expect((caught as ApiError).code).toBe("invalid_phone");
  });

  it("un 409 también relee la lista (el aviso cambió)", async () => {
    mockApi({ [WA_KEY]: apiError(409, "notification_closed") });
    const queryClient = testQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useWaLink(), { wrapper: wrapper(queryClient) });

    await act(async () => {
      await result.current.mutateAsync(JUAN.id).catch(() => undefined);
    });

    expect(spy).toHaveBeenCalledWith({ queryKey: NOTIFICATIONS_QUERY_KEY });
  });

  it.each([401, 403, 429, 500])("un %i no relee la lista (no quiere decir que el estado cambió)", async (status) => {
    mockApi({ [WA_KEY]: apiError(status, "x") });
    const queryClient = testQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useWaLink(), { wrapper: wrapper(queryClient) });

    await act(async () => {
      await result.current.mutateAsync(JUAN.id).catch(() => undefined);
    });

    expect(spy).not.toHaveBeenCalled();
  });

  it("un 404 sí relee la lista", async () => {
    mockApi({ [WA_KEY]: apiError(404, "notification_not_found") });
    const queryClient = testQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useWaLink(), { wrapper: wrapper(queryClient) });

    await act(async () => {
      await result.current.mutateAsync(JUAN.id).catch(() => undefined);
    });

    expect(spy).toHaveBeenCalledWith({ queryKey: NOTIFICATIONS_QUERY_KEY });
  });

  it("codifica el id en la ruta", async () => {
    const mock = mockApi({});
    const { result } = renderHook(() => useWaLink(), { wrapper: wrapper(testQueryClient()) });

    await act(async () => {
      await result.current.mutateAsync("a/b").catch(() => undefined);
    });

    expect(mock.calls[0]?.path).toBe("/notifications/a%2Fb/wa-link");
  });
});

describe("useSkip", () => {
  it("hace POST con el motivo recortado, entrega el aviso omitido e invalida ['notifications']", async () => {
    const skipped = { ...JUAN, status: "skipped", skip_reason: "Ya pagó en el box" };
    const mock = mockApi({ [SKIP_KEY]: { status: 200, body: skipped } });
    const queryClient = testQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useSkip(), { wrapper: wrapper(queryClient) });

    let out: unknown;
    await act(async () => {
      out = await result.current.mutateAsync({ id: JUAN.id, reason: "  Ya pagó en el box  " });
    });

    expect(mock.callsTo(SKIP_KEY)[0]?.body).toEqual({ reason: "Ya pagó en el box" });
    expect(out).toMatchObject({ id: JUAN.id, status: "skipped", skip_reason: "Ya pagó en el box" });
    expect(spy).toHaveBeenCalledWith({ queryKey: NOTIFICATIONS_QUERY_KEY });
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
  });

  it("no envía un motivo de menos de 3 ni de más de 500 caracteres", async () => {
    const mock = mockApi({ [SKIP_KEY]: { status: 200, body: JUAN } });
    const { result } = renderHook(() => useSkip(), { wrapper: wrapper(testQueryClient()) });

    await act(async () => {
      await result.current.mutateAsync({ id: JUAN.id, reason: "ab" }).catch(() => undefined);
      await result.current.mutateAsync({ id: JUAN.id, reason: "x".repeat(501) }).catch(() => undefined);
    });

    expect(mock.callsTo(SKIP_KEY)).toHaveLength(0);
  });

  it("un 429 al omitir no relee la lista", async () => {
    mockApi({ [SKIP_KEY]: apiError(429, "rate_limited") });
    const queryClient = testQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useSkip(), { wrapper: wrapper(queryClient) });

    await act(async () => {
      await result.current.mutateAsync({ id: JUAN.id, reason: "Ya pagó" }).catch(() => undefined);
    });

    expect(spy).not.toHaveBeenCalled();
  });

  it("un 409 rechaza con el ApiError y relee la lista", async () => {
    mockApi({ [SKIP_KEY]: apiError(409, "notification_closed") });
    const queryClient = testQueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const { result } = renderHook(() => useSkip(), { wrapper: wrapper(queryClient) });

    let caught: unknown;
    await act(async () => {
      caught = await result.current.mutateAsync({ id: JUAN.id, reason: "Ya pagó" }).catch((e: unknown) => e);
    });

    expect((caught as ApiError).status).toBe(409);
    expect(spy).toHaveBeenCalledWith({ queryKey: NOTIFICATIONS_QUERY_KEY });
  });
});

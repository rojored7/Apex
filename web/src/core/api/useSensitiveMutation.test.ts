// Fase 4 del Sprint 3 (M6): la garantía de S3-D52 (M-9) en un solo hook. Una mutación cuyo cuerpo o
// respuesta lleva un valor sensible (un monto, un motivo, una referencia, una contraseña, un dato
// cifrado en claro) no deja `variables` ni `data` en la caché de mutaciones después de responder:
// `gcTime: 0` y `reset()` al terminar, salga bien o mal. Quien llama recibe igual el resultado de
// `mutateAsync` (o su rechazo).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { useSensitiveMutation } from "./useSensitiveMutation";

const SECRET = { amount_cop: 120_000, reason: "Pago en efectivo de Laura" };

function setup<T>(mutationFn: (variables: typeof SECRET) => Promise<T>, onSuccess?: (data: T) => void) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client: queryClient }, children);
  const hook = renderHook(() => useSensitiveMutation<T, Error, typeof SECRET>({ mutationFn, ...(onSuccess ? { onSuccess } : {}) }), { wrapper });
  return { queryClient, ...hook };
}

describe("useSensitiveMutation (S3-D52)", () => {
  it("devuelve el resultado y no deja las variables ni la respuesta en la caché de mutaciones", async () => {
    const onSuccess = vi.fn();
    const { queryClient, result } = setup(() => Promise.resolve({ id: "p1", reference: "NQ-123" }), onSuccess);

    let out: unknown;
    await act(async () => {
      out = await result.current.mutateAsync(SECRET);
    });

    expect(out).toEqual({ id: "p1", reference: "NQ-123" });
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(onSuccess.mock.calls[0]?.slice(0, 2)).toEqual([{ id: "p1", reference: "NQ-123" }, SECRET]);
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
    expect(result.current.variables).toBeUndefined();
    expect(result.current.data).toBeUndefined();
    expect(result.current.isIdle).toBe(true);
  });

  it("también se olvida cuando falla, y quien llama recibe el rechazo", async () => {
    const failure = new Error("409");
    const { queryClient, result } = setup(() => Promise.reject(failure));

    let caught: unknown;
    await act(async () => {
      caught = await result.current.mutateAsync(SECRET).catch((error: unknown) => error);
    });

    expect(caught).toBe(failure);
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
    expect(result.current.variables).toBeUndefined();
    expect(result.current.error).toBeNull();
  });

  it("isPending es verdadero mientras responde", async () => {
    let finish: (value: string) => void = () => undefined;
    const { result } = setup(
      () =>
        new Promise<string>((resolve) => {
          finish = resolve;
        }),
    );

    let pending: Promise<string> = Promise.resolve("");
    act(() => {
      pending = result.current.mutateAsync(SECRET);
    });
    await waitFor(() => {
      expect(result.current.isPending).toBe(true);
    });
    await act(async () => {
      finish("listo");
      await pending;
    });
    await waitFor(() => {
      expect(result.current.isPending).toBe(false);
    });
  });
});

// Blueprint F2/F3, "Estructura común": QueryClient sin reintentos para 4xx (no son
// transitorios) y con staleTime de 30 s.
import { ApiError } from "./errors";
import { QUERY_STALE_TIME_MS, createQueryClient, shouldRetry } from "./queryClient";

const apiError = (status: number) => new ApiError({ status, code: "x", message: "x" });

describe("queryClient", () => {
  it("no reintenta un 4xx", () => {
    for (const status of [400, 401, 403, 404, 409, 422, 429]) expect(shouldRetry(0, apiError(status))).toBe(false);
  });

  it("reintenta hasta dos veces un 5xx, un fallo de red o un error ajeno", () => {
    expect(shouldRetry(0, apiError(503))).toBe(true);
    expect(shouldRetry(1, apiError(0))).toBe(true);
    expect(shouldRetry(1, new Error("x"))).toBe(true);
    expect(shouldRetry(2, apiError(500))).toBe(false);
  });

  it("usa staleTime de 30 s y la regla de reintento", () => {
    const client = createQueryClient();
    const defaults = client.getDefaultOptions();

    expect(QUERY_STALE_TIME_MS).toBe(30_000);
    expect(defaults.queries?.staleTime).toBe(30_000);
    expect(defaults.queries?.retry).toBe(shouldRetry);
    expect(defaults.mutations?.retry).toBe(false);
  });
});

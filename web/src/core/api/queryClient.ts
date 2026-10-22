// Blueprint del Sprint 2, "Estructura común": el QueryClient de la app.
// - Un 4xx no se reintenta (no es transitorio: credenciales, permiso, validación, 429).
// - Un 5xx, un fallo de red o un error ajeno se reintentan hasta dos veces.
// - Las mutaciones nunca se reintentan solas (podrían duplicar una escritura).
// - staleTime de 30 s. S2-F3 vacía este cliente al cerrar la sesión.
import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "./errors";
import { isClientErrorStatus } from "./status";

export const QUERY_STALE_TIME_MS = 30_000;
const MAX_RETRIES = 2;

export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && isClientErrorStatus(error.status)) return false;
  return failureCount < MAX_RETRIES;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: QUERY_STALE_TIME_MS, retry: shouldRetry },
      mutations: { retry: false },
    },
  });
}

export const queryClient = createQueryClient();

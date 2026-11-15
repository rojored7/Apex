// S8-F6 · US-177 (S8-D19, S8-D32, M-3): la única petición sin usuario del front, la de la pantalla de TV.
// - Va por `fetch` propio (y no por api.get) porque no debe llevar ni cookies ni Authorization ni el refresh de sesión: el token del
//   dispositivo viaja SOLO en la cabecera X-Device-Token (`credentials: "omit"`), nunca en la URL (la URL llega a los logs).
// - Un 401 es «token inválido» (ausente, inventado, rotado o revocado: el api no distingue). Cualquier otra falla (red caída, 429,
//   5xx, tiempo agotado o una respuesta que no es JSON) es «no disponible»: la pantalla conserva lo último que mostró.
// - Nunca escribe en console ni registra el token.
import { API_BASE } from "./client";
import { HTTP_UNAUTHORIZED } from "./status";

export const TV_REQUEST_TIMEOUT_MS = 15_000;
const DEVICE_TOKEN_HEADER = "X-Device-Token";

export type TvFailure = "invalid_token" | "unavailable";

export class TvRequestError extends Error {
  override readonly name = "TvRequestError";
  readonly failure: TvFailure;

  constructor(failure: TvFailure) {
    super(failure === "invalid_token" ? "Token inválido" : "Sin conexión");
    this.failure = failure;
  }
}

/** GET /tv/today con el token del dispositivo; devuelve el JSON sin validar (lo valida quien lo usa). */
export async function fetchTvToday(token: string, signal?: AbortSignal): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => {
    controller.abort();
  }, TV_REQUEST_TIMEOUT_MS);
  const onAbort = (): void => {
    controller.abort();
  };
  signal?.addEventListener("abort", onAbort);
  try {
    const response = await fetch(`${API_BASE}/tv/today`, {
      method: "GET",
      headers: { Accept: "application/json", [DEVICE_TOKEN_HEADER]: token },
      credentials: "omit",
      cache: "no-store",
      referrerPolicy: "no-referrer",
      signal: controller.signal,
    });
    if (response.status === HTTP_UNAUTHORIZED) throw new TvRequestError("invalid_token");
    if (!response.ok) throw new TvRequestError("unavailable");
    return (await response.json()) as unknown;
  } catch (error) {
    if (error instanceof TvRequestError) throw error;
    throw new TvRequestError("unavailable");
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  }
}

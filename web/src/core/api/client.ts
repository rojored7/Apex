// US-059 T6: la única puerta del front hacia el api.
// - Base /api/v1; ninguna feature escribe el prefijo.
// - El access token vive solo en memoria (N-13) y llega por setAccessTokenGetter; el
//   refresh viaja en una cookie HttpOnly del mismo origen, por eso credentials es
//   "same-origin" (nunca "include": no hay orígenes cruzados en v0.1, P7).
// - Ante un 401 invoca el gancho registrado (US-043 hace ahí el refresh compartido) como
//   máximo una vez por petición; si responde "retry" se repite la petición una sola vez.
// - S2-F3: un 429 lleva en el ApiError los segundos de `Retry-After` (retryAfterS).
// - S3-F3 (S3-D67): un 503 `busy` de una lectura (GET) se reintenta una sola vez tras los segundos
//   de `Retry-After` (1 s si no viene, 5 s como máximo); una escritura nunca se reintenta: podría
//   registrar dos veces una venta o un pago. Si el que llama cancela durante la espera, no hay
//   segundo intento.
// - Nunca escribe en console ni registra cuerpos o tokens.
import { API_ERROR_CODES } from "./errorCodes";
import { ApiError, GENERIC_MESSAGES, parseApiError } from "./errors";
import { toQueryString, type QueryParams } from "./query";
import { HTTP_SERVICE_UNAVAILABLE, HTTP_UNAUTHORIZED } from "./status";

export const API_BASE = "/api/v1";
export const REQUEST_TIMEOUT_MS = 15_000;

export interface RequestOptions {
  query?: QueryParams;
  body?: unknown;
  /** Señal del que llama (por ejemplo la de TanStack Query) para cancelar la petición. */
  signal?: AbortSignal;
  /**
   * No invoca el gancho del 401 (login, refresh y logout): evita que el refresh se llame a
   * sí mismo o que un 401 de credenciales malas dispare un refresh inútil.
   */
  skipAuthRetry?: boolean;
}

export type UnauthorizedResult = "retry" | "fail";
/** S2-F3: el access token con el que salió la petición que recibió el 401 (o null). */
export interface UnauthorizedContext {
  accessToken: string | null;
}
export type UnauthorizedHandler = (error: ApiError, context: UnauthorizedContext) => Promise<UnauthorizedResult>;

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

let accessTokenGetter: (() => string | null) | null = null;
let unauthorizedHandler: UnauthorizedHandler | null = null;

/** La sesión en memoria (US-042, US-043) entrega aquí el access token vigente. */
export function setAccessTokenGetter(getter: (() => string | null) | null): void {
  accessTokenGetter = getter;
}

/** Gancho para el 401; `null` lo quita. */
export function registerOnUnauthorized(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

function buildUrl(path: string, query: QueryParams | undefined): string {
  const qs = query ? toQueryString(query) : "";
  return `${API_BASE}${path}${qs ? `?${qs}` : ""}`;
}

function buildHeaders(hasBody: boolean, token: string | null): Headers {
  const headers = new Headers({ Accept: "application/json" });
  if (hasBody) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

interface RawResponse {
  status: number;
  ok: boolean;
  text: string;
  /** Cabecera `Retry-After` (429); `null` si no viene. */
  retryAfter: string | null;
}

/**
 * fetch más la lectura del cuerpo bajo el mismo timeout y la misma cancelación: un cuerpo
 * que se queda colgado también vence, y un fallo al leerlo es network_error.
 */
async function fetchWithTimeout(url: string, init: RequestInit, external: AbortSignal | undefined): Promise<RawResponse> {
  const controller = new AbortController();
  // Objeto mutable: el temporizador lo marca fuera del flujo que TypeScript sigue.
  const state = { timedOut: false };
  const timer = setTimeout(() => {
    state.timedOut = true;
    controller.abort();
  }, REQUEST_TIMEOUT_MS);
  const forwardAbort = (): void => {
    controller.abort(external?.reason);
  };
  if (external?.aborted) forwardAbort();
  else external?.addEventListener("abort", forwardAbort, { once: true });

  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    const text = response.status === 204 ? "" : await response.text();
    return { status: response.status, ok: response.ok, text, retryAfter: response.headers.get("Retry-After") };
  } catch (error) {
    if (state.timedOut) throw new ApiError({ status: 0, code: "timeout", message: GENERIC_MESSAGES.timeout });
    if (external?.aborted) throw error;
    throw new ApiError({ status: 0, code: "network_error", message: GENERIC_MESSAGES.network_error });
  } finally {
    clearTimeout(timer);
    external?.removeEventListener("abort", forwardAbort);
  }
}

function readSuccess({ status, text }: RawResponse): unknown {
  if (text === "") return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new ApiError({ status, code: "network_error", message: GENERIC_MESSAGES.network_error });
  }
}

/** S3-F3: reintentos ya gastados en esta petición (uno por motivo, nunca más). */
interface Retries {
  /** Tras un 401, el gancho pidió repetir (US-043). */
  auth: boolean;
  /** Tras un 503 `busy` en una lectura (S3-D67). */
  busy: boolean;
}

const FRESH: Retries = Object.freeze({ auth: false, busy: false });

/** S3-F3: espera de un 503 `busy` sin `Retry-After` útil, y tope de la espera. */
export const BUSY_RETRY_DEFAULT_S = 1;
export const BUSY_RETRY_MAX_S = 5;
const MS_PER_S = 1_000;

/** Un 503 `busy` de una lectura se reintenta una vez; una escritura nunca (podría duplicarse). */
function shouldRetryBusy(method: Method, error: ApiError, retries: Retries): boolean {
  return method === "GET" && !retries.busy && error.status === HTTP_SERVICE_UNAVAILABLE && error.code === API_ERROR_CODES.busy;
}

/** Espera `seconds`; si el que llama cancela, rechaza con el motivo de su señal (AbortError). */
function waitFor(seconds: number, signal: AbortSignal | undefined): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(signal.reason as Error);
      return;
    }
    const onAbort = (): void => {
      clearTimeout(timer);
      reject(signal?.reason as Error);
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, seconds * MS_PER_S);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

async function request<T>(method: Method, path: string, options: RequestOptions, retries: Retries = FRESH): Promise<T> {
  const hasBody = options.body !== undefined;
  const token = accessTokenGetter?.() ?? null;
  const init: RequestInit = {
    method,
    credentials: "same-origin",
    headers: buildHeaders(hasBody, token),
    ...(hasBody ? { body: JSON.stringify(options.body) } : {}),
  };
  const response = await fetchWithTimeout(buildUrl(path, options.query), init, options.signal);
  if (response.ok) return readSuccess(response) as T;

  const error = parseApiError(response.status, response.text, response.retryAfter);
  if (response.status === HTTP_UNAUTHORIZED && !retries.auth && !options.skipAuthRetry && unauthorizedHandler) {
    const outcome = await unauthorizedHandler(error, { accessToken: token });
    if (outcome === "retry") return request<T>(method, path, options, { ...retries, auth: true });
  }
  if (shouldRetryBusy(method, error, retries)) {
    // Revisión S3-F3 (LOW 11): entre 1 y 5 s; un Retry-After de 0 no reintenta al instante.
    await waitFor(Math.min(Math.max(error.retryAfterS ?? BUSY_RETRY_DEFAULT_S, BUSY_RETRY_DEFAULT_S), BUSY_RETRY_MAX_S), options.signal);
    return request<T>(method, path, options, { ...retries, busy: true });
  }
  throw error;
}

export const api = {
  get: <T>(path: string, options: RequestOptions = {}): Promise<T> => request<T>("GET", path, options),
  post: <T>(path: string, options: RequestOptions = {}): Promise<T> => request<T>("POST", path, options),
  put: <T>(path: string, options: RequestOptions = {}): Promise<T> => request<T>("PUT", path, options),
  patch: <T>(path: string, options: RequestOptions = {}): Promise<T> => request<T>("PATCH", path, options),
  delete: <T>(path: string, options: RequestOptions = {}): Promise<T> => request<T>("DELETE", path, options),
};

// US-059 T6: la única puerta del front hacia el api.
// - Base /api/v1; ninguna feature escribe el prefijo.
// - El access token vive solo en memoria (N-13) y llega por setAccessTokenGetter; el
//   refresh viaja en una cookie HttpOnly del mismo origen, por eso credentials es
//   "same-origin" (nunca "include": no hay orígenes cruzados en v0.1, P7).
// - Ante un 401 invoca el gancho registrado (US-043 hace ahí el refresh compartido) como
//   máximo una vez por petición; si responde "retry" se repite la petición una sola vez.
// - Nunca escribe en console ni registra cuerpos o tokens.
import { ApiError, GENERIC_MESSAGES, parseApiError } from "./errors";
import { toQueryString, type QueryParams } from "./query";

export const API_BASE = "/api/v1";
export const REQUEST_TIMEOUT_MS = 15_000;

export interface RequestOptions {
  query?: QueryParams;
  body?: unknown;
  /** Señal del que llama (por ejemplo la de TanStack Query) para cancelar la petición. */
  signal?: AbortSignal;
}

export type UnauthorizedResult = "retry" | "fail";
export type UnauthorizedHandler = (error: ApiError) => Promise<UnauthorizedResult>;

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

function buildHeaders(hasBody: boolean): Headers {
  const headers = new Headers({ Accept: "application/json" });
  if (hasBody) headers.set("Content-Type", "application/json");
  const token = accessTokenGetter?.();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

async function fetchWithTimeout(url: string, init: RequestInit, external: AbortSignal | undefined): Promise<Response> {
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
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (state.timedOut) throw new ApiError({ status: 0, code: "timeout", message: GENERIC_MESSAGES.timeout });
    if (external?.aborted) throw error;
    throw new ApiError({ status: 0, code: "network_error", message: GENERIC_MESSAGES.network_error });
  } finally {
    clearTimeout(timer);
    external?.removeEventListener("abort", forwardAbort);
  }
}

async function readSuccess<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  if (text === "") return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError({ status: response.status, code: "network_error", message: GENERIC_MESSAGES.network_error });
  }
}

async function request<T>(method: Method, path: string, options: RequestOptions, retried: boolean): Promise<T> {
  const hasBody = options.body !== undefined;
  const init: RequestInit = {
    method,
    credentials: "same-origin",
    headers: buildHeaders(hasBody),
    ...(hasBody ? { body: JSON.stringify(options.body) } : {}),
  };
  const response = await fetchWithTimeout(buildUrl(path, options.query), init, options.signal);
  if (response.ok) return readSuccess<T>(response);

  const error = parseApiError(response.status, await response.text());
  if (response.status === 401 && !retried && unauthorizedHandler) {
    const outcome = await unauthorizedHandler(error);
    if (outcome === "retry") return request<T>(method, path, options, true);
  }
  throw error;
}

export const api = {
  get: <T>(path: string, options: RequestOptions = {}): Promise<T> => request<T>("GET", path, options, false),
  post: <T>(path: string, options: RequestOptions = {}): Promise<T> => request<T>("POST", path, options, false),
  put: <T>(path: string, options: RequestOptions = {}): Promise<T> => request<T>("PUT", path, options, false),
  patch: <T>(path: string, options: RequestOptions = {}): Promise<T> => request<T>("PATCH", path, options, false),
  delete: <T>(path: string, options: RequestOptions = {}): Promise<T> => request<T>("DELETE", path, options, false),
};

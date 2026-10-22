// Utilidades de prueba compartidas del front (plan del Sprint 2, sección 2, "W0-1 y front").
// - mockApi: `fetch` simulado por "MÉTODO /ruta" (sin el prefijo /api/v1) que registra cada
//   llamada. Se instala con vi.stubGlobal y se quita con vi.unstubAllGlobals().
// - renderWithProviders: QueryClient nuevo por prueba, rol por contexto y un MemoryRouter.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions, type RenderResult } from "@testing-library/react";
import { createElement, type ReactElement, type ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { RoleProvider, type Role } from "../core/auth";

export interface MockReply {
  status: number;
  body?: unknown;
  /** Cabeceras extra de la respuesta (por ejemplo `Retry-After` de un 429, S2-F3). */
  headers?: Record<string, string>;
}

export type MockHandler = MockReply | ((call: RecordedCall) => MockReply | Promise<MockReply>);

export interface RecordedCall {
  method: string;
  path: string;
  url: string;
  headers: Headers;
  body: unknown;
  /** `credentials` del `RequestInit` (S2-D44: siempre "same-origin"). */
  credentials: RequestCredentials | undefined;
  /** S2-F6: la señal con la que salió la petición (cancelación de TanStack Query). */
  signal: AbortSignal | null;
}

export interface ApiMock {
  calls: RecordedCall[];
  /** Llamadas a una ruta ("POST /auth/refresh"). */
  callsTo: (key: string) => RecordedCall[];
}

const API_PREFIX = "/api/v1";

function parseBody(init: RequestInit | undefined): unknown {
  if (typeof init?.body !== "string") return undefined;
  try {
    return JSON.parse(init.body) as unknown;
  } catch {
    return init.body;
  }
}

/** Instala un `fetch` simulado. Una ruta sin manejador responde 404 con el envelope. */
export function mockApi(handlers: Record<string, MockHandler>): ApiMock {
  const calls: RecordedCall[] = [];
  const fake = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const pathname = new URL(url, "http://apex.test").pathname;
    const path = pathname.startsWith(API_PREFIX) ? pathname.slice(API_PREFIX.length) : pathname;
    const method = (init?.method ?? "GET").toUpperCase();
    const call: RecordedCall = {
      method,
      path,
      url,
      headers: new Headers(init?.headers),
      body: parseBody(init),
      credentials: init?.credentials,
      signal: init?.signal ?? null,
    };
    calls.push(call);
    const handler = handlers[`${method} ${path}`];
    const reply: MockReply =
      handler === undefined
        ? { status: 404, body: { error: { code: "not_found", message: "No encontrado." } } }
        : typeof handler === "function"
          ? await handler(call)
          : handler;
    const text = reply.body === undefined ? null : JSON.stringify(reply.body);
    return new Response(reply.status === 204 ? null : text, {
      status: reply.status,
      headers: { "Content-Type": "application/json", ...reply.headers },
    });
  };
  vi.stubGlobal("fetch", vi.fn(fake));
  return { calls, callsTo: (key) => calls.filter((c) => `${c.method} ${c.path}` === key) };
}

export interface ProviderOptions extends Omit<RenderOptions, "wrapper"> {
  role?: Role | null;
  route?: string;
  queryClient?: QueryClient;
}

export function testQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

export function renderWithProviders(ui: ReactElement, options: ProviderOptions = {}): RenderResult & { queryClient: QueryClient } {
  const { role = null, route = "/", queryClient = testQueryClient(), ...rest } = options;
  // createElement en lugar de JSX: el plan fija el nombre server.ts.
  function Wrapper({ children }: { children: ReactNode }) {
    return createElement(
      QueryClientProvider,
      { client: queryClient },
      createElement(RoleProvider, { value: role }, createElement(MemoryRouter, { initialEntries: [route] }, children)),
    );
  }
  return { ...render(ui, { wrapper: Wrapper, ...rest }), queryClient };
}

/** `matchMedia` simulado para un ancho de ventana; entiende `(width < Npx)` y `(min-width: Npx)`. */
export function setViewportWidth(width: number): void {
  const matches = (query: string): boolean => {
    const lt = /width\s*<\s*(\d+)px/.exec(query);
    if (lt) return width < Number(lt[1]);
    const ge = /width\s*>=\s*(\d+)px|min-width:\s*(\d+)px/.exec(query);
    if (ge) return width >= Number(ge[1] ?? ge[2]);
    return false;
  };
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: matches(query),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(() => false),
    })),
  );
}

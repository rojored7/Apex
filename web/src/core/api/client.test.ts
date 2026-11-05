// @vitest-environment node
// US-059 T9: cliente HTTP único. fetch se simula con vi.stubGlobal (sin MSW: no hace
// falta otra dependencia para responder 200, 204, 401, 409, 422 y 502).
import {
  API_BASE,
  BLOB_TIMEOUT_MS,
  UNEXPECTED_CONTENT_MESSAGE,
  REQUEST_TIMEOUT_MS,
  api,
  registerOnUnauthorized,
  setAccessTokenGetter,
  type UnauthorizedHandler,
} from "./client";
import { clearCustodyNotice, getCustodyNotice } from "../custody/custodyNotice";
import { ApiError } from "./errors";
import type { Page } from "./page";

type FetchMock = ReturnType<typeof vi.fn<typeof fetch>>;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function envelope(status: number, code: string, message: string, extra: Record<string, unknown> = {}): Response {
  return json(status, { error: { code, message, ...extra } });
}

let fetchMock: FetchMock;

function lastCall(): { url: string; init: RequestInit } {
  const call = fetchMock.mock.calls.at(-1);
  if (!call) throw new Error("fetch no fue llamado");
  const [input, init] = call;
  return { url: typeof input === "string" ? input : input instanceof URL ? input.href : input.url, init: init ?? {} };
}

function headersOf(init: RequestInit): Headers {
  return new Headers(init.headers);
}

beforeEach(() => {
  fetchMock = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  setAccessTokenGetter(null);
  registerOnUnauthorized(null);
  vi.unstubAllGlobals();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("cliente HTTP", () => {
  it("usa la base /api/v1 y un timeout de 15 s", () => {
    expect(API_BASE).toBe("/api/v1");
    expect(REQUEST_TIMEOUT_MS).toBe(15_000);
  });

  it("GET tipado con query string, credenciales de mismo origen y Accept JSON", async () => {
    interface Row {
      id: string;
      first_name: string;
    }
    const page: Page<Row> = { items: [{ id: "1", first_name: "Ana" }], total: 1, limit: 25, offset: 0 };
    fetchMock.mockResolvedValue(json(200, page));

    const result = await api.get<Page<Row>>("/members", { query: { limit: 25, offset: 0, q: undefined } });

    expect(result).toEqual(page);
    const { url, init } = lastCall();
    expect(url).toBe("/api/v1/members?limit=25&offset=0");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
    expect(headersOf(init).get("Accept")).toBe("application/json");
    expect(headersOf(init).has("Authorization")).toBe(false);
    expect(init.body).toBeUndefined();
  });

  it("POST envía el cuerpo como JSON y la cabecera Authorization si hay token en memoria", async () => {
    setAccessTokenGetter(() => "token-de-prueba");
    fetchMock.mockResolvedValue(json(201, { id: "x" }));

    await api.post<{ id: string }>("/members", { body: { first_name: "Ana" } });

    const { url, init } = lastCall();
    expect(url).toBe("/api/v1/members");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ first_name: "Ana" }));
    expect(headersOf(init).get("Content-Type")).toBe("application/json");
    expect(headersOf(init).get("Authorization")).toBe("Bearer token-de-prueba");
  });

  it("PATCH, PUT y DELETE usan su método; 204 devuelve undefined", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response(null, { status: 204 })));

    await expect(api.patch("/members/1", { body: { phone: "300" } })).resolves.toBeUndefined();
    expect(lastCall().init.method).toBe("PATCH");
    await expect(api.put("/settings", { body: {} })).resolves.toBeUndefined();
    expect(lastCall().init.method).toBe("PUT");
    await expect(api.delete("/members/1")).resolves.toBeUndefined();
    expect(lastCall().init.method).toBe("DELETE");
  });

  it("una respuesta 200 sin cuerpo devuelve undefined", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 200 }));

    await expect(api.get("/x")).resolves.toBeUndefined();
  });

  it("un token vacío no agrega Authorization", async () => {
    setAccessTokenGetter(() => null);
    fetchMock.mockResolvedValue(json(200, {}));

    await api.get("/x");

    expect(headersOf(lastCall().init).has("Authorization")).toBe(false);
  });

  it("409 con existing_id lanza ApiError con field y existingId", async () => {
    fetchMock.mockResolvedValue(
      envelope(409, "member_document_duplicated", "Ya existe un socio con este documento", {
        field: "document",
        existing_id: "abc",
      }),
    );

    const error = await api.post("/members", { body: {} }).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, code: "member_document_duplicated", field: "document", existingId: "abc" });
  });

  it("422 con field lanza ApiError con el campo", async () => {
    fetchMock.mockResolvedValue(envelope(422, "validation_error", "El motivo es obligatorio", { field: "reason" }));

    await expect(api.post("/payments/1/void", { body: {} })).rejects.toMatchObject({ status: 422, field: "reason" });
  });

  it("502 sin envelope lanza network_error", async () => {
    fetchMock.mockResolvedValue(new Response("<html>Bad Gateway</html>", { status: 502 }));

    await expect(api.get("/members")).rejects.toMatchObject({ status: 502, code: "network_error" });
  });

  it("un fallo de red lanza network_error con status 0", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(api.get("/members")).rejects.toMatchObject({ status: 0, code: "network_error" });
  });

  it("200 con cuerpo que no es JSON lanza network_error", async () => {
    fetchMock.mockResolvedValue(new Response("no json", { status: 200 }));

    await expect(api.get("/members")).rejects.toMatchObject({ status: 200, code: "network_error" });
  });

  it("pasado el timeout lanza ApiError timeout", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("aborted", "AbortError"));
          });
        }),
    );

    const pending = api.get("/lento").catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS);

    expect(await pending).toMatchObject({ status: 0, code: "timeout" });
  });

  it("un cuerpo que se queda colgado también vence con timeout", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation((_input, init) => {
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          init?.signal?.addEventListener("abort", () => {
            controller.error(new DOMException("aborted", "AbortError"));
          });
        },
      });
      return Promise.resolve(new Response(body, { status: 200 }));
    });

    const pending = api.get("/lento").catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS);

    expect(await pending).toMatchObject({ status: 0, code: "timeout" });
  });

  it("un fallo al leer el cuerpo es network_error", async () => {
    fetchMock.mockResolvedValue({
      status: 200,
      ok: true,
      text: () => Promise.reject(new TypeError("conexión cortada")),
    } as unknown as Response);

    await expect(api.get("/x")).rejects.toMatchObject({ status: 0, code: "network_error" });
  });

  it("una cancelación del que llama se propaga como AbortError, no como ApiError", async () => {
    const controller = new AbortController();
    fetchMock.mockImplementation(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("aborted", "AbortError"));
          });
        }),
    );

    const pending = api.get("/x", { signal: controller.signal }).catch((e: unknown) => e);
    controller.abort();
    const error = await pending;

    expect(error).not.toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ name: "AbortError" });
  });

  it("una señal ya cancelada no llega a esperar al servidor", async () => {
    const controller = new AbortController();
    controller.abort();
    fetchMock.mockImplementation((_input, init) =>
      init?.signal?.aborted ? Promise.reject(new DOMException("aborted", "AbortError")) : Promise.resolve(json(200, {})),
    );

    await expect(api.get("/x", { signal: controller.signal })).rejects.toMatchObject({ name: "AbortError" });
  });

  it("nunca escribe en console", async () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((method) =>
      vi.spyOn(console, method).mockImplementation(() => undefined),
    );
    setAccessTokenGetter(() => "secreto");
    fetchMock.mockResolvedValueOnce(json(200, { ok: true }));
    fetchMock.mockResolvedValueOnce(envelope(500, "internal_error", "Error interno"));

    await api.get("/x");
    await api.get("/x").catch(() => undefined);

    for (const spy of spies) expect(spy).not.toHaveBeenCalled();
  });
});

describe("401 y el gancho onUnauthorized", () => {
  it("sin gancho registrado propaga el ApiError", async () => {
    fetchMock.mockResolvedValue(envelope(401, "token_expired", "Sesión vencida"));

    await expect(api.get("/members")).rejects.toMatchObject({ status: 401, code: "token_expired" });
  });

  it("invoca el gancho una vez y, si pide reintentar, repite la petición una sola vez", async () => {
    const handler = vi.fn<UnauthorizedHandler>(() => Promise.resolve("retry"));
    registerOnUnauthorized(handler);
    fetchMock.mockResolvedValueOnce(envelope(401, "token_expired", "Sesión vencida"));
    fetchMock.mockResolvedValueOnce(json(200, { id: "1" }));

    await expect(api.get<{ id: string }>("/members/1")).resolves.toEqual({ id: "1" });
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler.mock.calls[0]?.[0]).toMatchObject({ code: "token_expired" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("si el reintento vuelve a dar 401, no invoca el gancho otra vez", async () => {
    const handler = vi.fn(() => Promise.resolve("retry" as const));
    registerOnUnauthorized(handler);
    fetchMock.mockImplementation(() => Promise.resolve(envelope(401, "token_expired", "Sesión vencida")));

    await expect(api.get("/members")).rejects.toMatchObject({ status: 401 });
    expect(handler).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("si el gancho no pide reintentar, propaga el 401", async () => {
    const handler = vi.fn(() => Promise.resolve("fail" as const));
    registerOnUnauthorized(handler);
    fetchMock.mockResolvedValue(envelope(401, "unauthorized", "No autorizado"));

    await expect(api.get("/members")).rejects.toMatchObject({ status: 401, code: "unauthorized" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("tres peticiones concurrentes con 401 llaman al mismo gancho una vez cada una", async () => {
    const handler = vi.fn(() => Promise.resolve("retry" as const));
    registerOnUnauthorized(handler);
    let calls = 0;
    fetchMock.mockImplementation(() => {
      calls += 1;
      return Promise.resolve(calls <= 3 ? envelope(401, "token_expired", "Sesión vencida") : json(200, { ok: calls }));
    });

    const results = await Promise.all([api.get("/a"), api.get("/b"), api.get("/c")]);

    expect(results).toHaveLength(3);
    expect(handler).toHaveBeenCalledTimes(3);
    expect(fetchMock).toHaveBeenCalledTimes(6);
  });

  it("con skipAuthRetry (login, refresh) un 401 no invoca el gancho", async () => {
    const handler = vi.fn<UnauthorizedHandler>(() => Promise.resolve("retry"));
    registerOnUnauthorized(handler);
    fetchMock.mockResolvedValue(envelope(401, "unauthorized", "Credenciales inválidas"));

    await expect(api.post("/auth/login", { body: {}, skipAuthRetry: true })).rejects.toMatchObject({ status: 401 });
    expect(handler).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("un 401 no invoca el gancho para otros códigos de estado", async () => {
    const handler = vi.fn(() => Promise.resolve("retry" as const));
    registerOnUnauthorized(handler);
    fetchMock.mockResolvedValue(envelope(403, "forbidden", "Sin permiso"));

    await expect(api.get("/x")).rejects.toMatchObject({ status: 403 });
    expect(handler).not.toHaveBeenCalled();
  });
});

describe("429 y Retry-After (S2-F3)", () => {
  it("un 429 lleva los segundos de Retry-After en el ApiError y no invoca el gancho", async () => {
    const handler = vi.fn(() => Promise.resolve("retry" as const));
    registerOnUnauthorized(handler);
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "rate_limited", message: "Demasiadas solicitudes" } }), {
        status: 429,
        headers: { "Content-Type": "application/json", "Retry-After": "42" },
      }),
    );

    await expect(api.post("/auth/login", { body: {}, skipAuthRetry: true })).rejects.toMatchObject({
      status: 429,
      code: "rate_limited",
      retryAfterS: 42,
    });
    expect(handler).not.toHaveBeenCalled();
  });

  it("sin Retry-After el ApiError no trae espera", async () => {
    fetchMock.mockResolvedValue(envelope(429, "rate_limited", "Demasiadas solicitudes"));

    await expect(api.get("/x")).rejects.toMatchObject({ status: 429, retryAfterS: undefined });
  });
});

describe("contexto del gancho del 401 (S2-F3)", () => {
  it("el gancho recibe el access token con el que salió la petición", async () => {
    const handler = vi.fn<UnauthorizedHandler>(() => Promise.resolve("fail"));
    registerOnUnauthorized(handler);
    setAccessTokenGetter(() => "usado");
    fetchMock.mockResolvedValue(envelope(401, "token_expired", "Token vencido"));

    await expect(api.get("/x")).rejects.toMatchObject({ code: "token_expired" });

    expect(handler).toHaveBeenCalledWith(expect.objectContaining({ code: "token_expired" }), { accessToken: "usado" });
  });

  it("sin token el contexto lleva null", async () => {
    const handler = vi.fn<UnauthorizedHandler>(() => Promise.resolve("fail"));
    registerOnUnauthorized(handler);
    fetchMock.mockResolvedValue(envelope(401, "unauthorized", "No autorizado"));

    await expect(api.get("/x")).rejects.toMatchObject({ status: 401 });

    expect(handler.mock.calls[0]?.[1]).toEqual({ accessToken: null });
  });
});

describe("503 busy (S3-F3, S3-D67)", () => {
  function busy(retryAfter: string | null = "1"): Response {
    return new Response(JSON.stringify({ error: { code: "busy", message: "Base de datos ocupada" } }), {
      status: 503,
      headers: { "Content-Type": "application/json", ...(retryAfter === null ? {} : { "Retry-After": retryAfter }) },
    });
  }

  it("un GET con 503 busy se reintenta una vez tras los segundos de Retry-After", async () => {
    vi.useFakeTimers();
    fetchMock.mockResolvedValueOnce(busy("2")).mockResolvedValueOnce(json(200, { ok: true }));

    const pending = api.get<{ ok: boolean }>("/members");
    await vi.advanceTimersByTimeAsync(1_999);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);

    expect(await pending).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("si el reintento vuelve a dar busy, lanza el ApiError sin un tercer intento", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(() => Promise.resolve(busy()));

    const pending = api.get("/members").catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(1_000);

    expect(await pending).toMatchObject({ status: 503, code: "busy" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it.each(["POST", "PATCH", "PUT", "DELETE"] as const)("un %s con 503 busy nunca se reintenta (escritura)", async (method) => {
    fetchMock.mockResolvedValue(busy());
    const call = { POST: api.post, PATCH: api.patch, PUT: api.put, DELETE: api.delete }[method];

    await expect(call("/members/1/memberships", { body: {} })).rejects.toMatchObject({ status: 503, code: "busy", retryAfterS: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("sin Retry-After espera 1 s; un Retry-After mayor que 5 s espera 5 s", async () => {
    vi.useFakeTimers();
    fetchMock.mockResolvedValueOnce(busy(null)).mockResolvedValueOnce(json(200, {})).mockResolvedValueOnce(busy("120")).mockResolvedValueOnce(json(200, {}));

    const first = api.get("/a");
    await vi.advanceTimersByTimeAsync(999);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    await first;
    expect(fetchMock).toHaveBeenCalledTimes(2);

    const second = api.get("/b");
    await vi.advanceTimersByTimeAsync(4_999);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(1);
    await second;
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("otro 503 (sin el código busy) no se reintenta", async () => {
    fetchMock.mockResolvedValue(new Response("<html>503</html>", { status: 503 }));

    await expect(api.get("/x")).rejects.toMatchObject({ status: 503, code: "network_error" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("si el que llama cancela durante la espera, no hay segundo intento y se propaga el AbortError", async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    fetchMock.mockResolvedValue(busy("3"));

    const pending = api.get("/x", { signal: controller.signal }).catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(500);
    controller.abort();
    await vi.advanceTimersByTimeAsync(5_000);

    expect(await pending).toMatchObject({ name: "AbortError" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("revisión S3-F3 (LOW 11): Retry-After 0 en un busy", () => {
  it("espera al menos 1 s antes del reintento", async () => {
    vi.useFakeTimers();
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: { code: "busy", message: "x" } }), { status: 503, headers: { "Retry-After": "0" } }))
      .mockResolvedValueOnce(json(200, {}));

    const pending = api.get("/x");
    await vi.advanceTimersByTimeAsync(999);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    await pending;
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("503 crypto_unavailable (S5-F5, S5-D14, US-136)", () => {
  function sealed(retryAfter: string | null = "30"): Response {
    return new Response(JSON.stringify({ error: { code: "crypto_unavailable", message: "El servicio de llaves no está disponible" } }), {
      status: 503,
      headers: { "Content-Type": "application/json", ...(retryAfter === null ? {} : { "Retry-After": retryAfter }) },
    });
  }

  afterEach(() => {
    clearCustodyNotice();
  });

  it("avisa de forma global con los segundos de Retry-After y propaga el error", async () => {
    fetchMock.mockResolvedValueOnce(sealed("45"));

    await expect(api.get("/members/1")).rejects.toMatchObject({ status: 503, code: "crypto_unavailable", retryAfterS: 45 });

    expect(getCustodyNotice()).toMatchObject({ retryAfterS: 45 });
  });

  it("sin Retry-After usa 30 segundos", async () => {
    fetchMock.mockResolvedValueOnce(sealed(null));

    await expect(api.get("/members/1")).rejects.toMatchObject({ code: "crypto_unavailable" });

    expect(getCustodyNotice()).toMatchObject({ retryAfterS: 30 });
  });

  it.each(["GET", "POST", "PATCH", "PUT", "DELETE"] as const)("un %s no se reintenta: una sola petición", async (method) => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(() => Promise.resolve(sealed("1")));
    const call = { GET: api.get, POST: api.post, PATCH: api.patch, PUT: api.put, DELETE: api.delete }[method];

    const pending = call("/members/1").catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(60_000);

    expect(await pending).toMatchObject({ code: "crypto_unavailable" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("otro 503 (busy u otro código) no dispara el aviso de custodio", async () => {
    fetchMock.mockResolvedValueOnce(envelope(503, "internal_error", "x"));

    await expect(api.post("/x")).rejects.toMatchObject({ status: 503 });

    expect(getCustodyNotice()).toBeNull();
  });

  it("un 200 no avisa", async () => {
    fetchMock.mockResolvedValueOnce(json(200, {}));

    await api.get("/x");

    expect(getCustodyNotice()).toBeNull();
  });
});

describe("api.blob: descargas de archivos (S5-F4, L-8)", () => {
  const PDF = "%PDF-1.4 recibo";

  function file(headers: Record<string, string> = {}, body: string = PDF, status = 200): Response {
    return new Response(body, { status, headers: { "Content-Type": "application/pdf", ...headers } });
  }

  function hang(): void {
    fetchMock.mockImplementation(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("aborted", "AbortError"));
          });
        }),
    );
  }

  it("devuelve el Blob, el nombre del Content-Disposition y el tipo; pide solo GET con credenciales de mismo origen", async () => {
    fetchMock.mockResolvedValueOnce(file({ "Content-Disposition": "attachment; filename=recibo-9a8b7c6d.pdf" }));

    const result = await api.blob("/payments/9a8b7c6d/receipt.pdf");

    expect(await result.blob.text()).toBe(PDF);
    expect(result.filename).toBe("recibo-9a8b7c6d.pdf");
    expect(result.contentType).toBe("application/pdf");
    const { url, init } = lastCall();
    expect(url).toBe("/api/v1/payments/9a8b7c6d/receipt.pdf");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
    expect(headersOf(init).get("Accept")).toContain("application/pdf");
  });

  it("sin Content-Disposition el nombre es null; con query string y el access token en memoria", async () => {
    setAccessTokenGetter(() => "tok");
    fetchMock.mockResolvedValueOnce(file());

    const result = await api.blob("/members/export", { query: { q: "ana", status: "active" } });

    expect(result.filename).toBeNull();
    expect(lastCall().url).toBe("/api/v1/members/export?q=ana&status=active");
    expect(headersOf(lastCall().init).get("Authorization")).toBe("Bearer tok");
  });

  it("tiene un tiempo propio, mayor que el del JSON, y lo vence con timeout", async () => {
    expect(BLOB_TIMEOUT_MS).toBeGreaterThan(REQUEST_TIMEOUT_MS);
    vi.useFakeTimers();
    hang();

    const pending = api.blob("/lento").catch((e: unknown) => e);
    let settled = false;
    void pending.then(() => {
      settled = true;
    });
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS + 1);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(BLOB_TIMEOUT_MS);

    expect(await pending).toMatchObject({ status: 0, code: "timeout" });
  });

  it("acepta un timeoutMs propio por llamada", async () => {
    vi.useFakeTimers();
    hang();

    const pending = api.blob("/lento", { timeoutMs: 500 }).catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(500);

    expect(await pending).toMatchObject({ code: "timeout" });
  });

  it("no guarda nada: ni caché de HTTP ni almacenamiento del navegador", async () => {
    const setItem = vi.fn();
    vi.stubGlobal("localStorage", { setItem, getItem: vi.fn(), removeItem: vi.fn() });
    vi.stubGlobal("sessionStorage", { setItem, getItem: vi.fn(), removeItem: vi.fn() });
    fetchMock.mockResolvedValueOnce(file());

    await api.blob("/payments/1/receipt.pdf");

    expect(setItem).not.toHaveBeenCalled();
    expect(lastCall().init.cache).toBeUndefined();
  });

  it.each([
    [401, "unauthorized", "Inicia sesión"],
    [403, "forbidden", "Sin permiso"],
    [404, "not_found", "No existe"],
    [409, "export_in_progress", "Ya tienes una exportación en curso. Espera a que termine."],
    [422, "export_too_large", "La exportación supera el máximo de filas. Acota los filtros."],
    [503, "crypto_unavailable", "El custodio de llaves no está disponible. Avise al administrador para desellarlo."],
  ])("propaga el %i %s con el code y el message del api", async (status, code, message) => {
    fetchMock.mockResolvedValueOnce(envelope(status, code, message));

    await expect(api.blob("/members/export")).rejects.toMatchObject({ status, code, message });
  });

  it("un 422 conserva el field del api", async () => {
    fetchMock.mockResolvedValueOnce(envelope(422, "invalid_date_range", "El rango de fechas no es válido.", { field: "to" }));

    await expect(api.blob("/payments/export")).rejects.toMatchObject({ status: 422, field: "to" });
  });

  it("un 503 respeta Retry-After y no se reintenta (aunque sea busy)", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "busy", message: "ocupado" } }), { status: 503, headers: { "Content-Type": "application/json", "Retry-After": "7" } }),
    );

    await expect(api.blob("/members/export")).rejects.toMatchObject({ status: 503, code: "busy", retryAfterS: 7 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("un 503 crypto_unavailable activa el aviso global con los segundos de Retry-After", async () => {
    clearCustodyNotice();
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: { code: "crypto_unavailable", message: "x" } }), { status: 503, headers: { "Content-Type": "application/json", "Retry-After": "45" } }),
    );

    await expect(api.blob("/members/export")).rejects.toMatchObject({ retryAfterS: 45 });

    expect(getCustodyNotice()).not.toBeNull();
    clearCustodyNotice();
  });

  it("un 401 invoca el gancho y, si pide reintentar, repite la descarga una sola vez", async () => {
    const handler = vi.fn<UnauthorizedHandler>(() => Promise.resolve("retry"));
    registerOnUnauthorized(handler);
    fetchMock.mockResolvedValueOnce(envelope(401, "token_expired", "Sesión vencida"));
    fetchMock.mockResolvedValueOnce(file());

    const result = await api.blob("/payments/1/receipt.pdf");

    expect(await result.blob.text()).toBe(PDF);
    expect(handler).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("respeta la cancelación del que llama", async () => {
    const controller = new AbortController();
    hang();

    const pending = api.blob("/lento", { signal: controller.signal }).catch((e: unknown) => e);
    controller.abort();

    expect(await pending).toBeInstanceOf(DOMException);
  });

  it("un fallo de red es network_error", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await expect(api.blob("/x")).rejects.toMatchObject({ status: 0, code: "network_error" });
  });
});

describe("api.blob: tipo de contenido (revisión F4, LOW 3)", () => {
  it.each(["application/pdf", "text/csv", "text/csv; charset=utf-8", "Application/PDF"])("acepta %s", async (type) => {
    fetchMock.mockResolvedValueOnce(new Response("x", { status: 200, headers: { "Content-Type": type } }));

    await expect(api.blob("/x")).resolves.toMatchObject({ contentType: type });
  });

  it.each(["text/html", "application/json", "application/octet-stream", ""])("rechaza un 200 de tipo '%s' con unexpected_content_type", async (type) => {
    fetchMock.mockResolvedValueOnce(new Response("<html></html>", { status: 200, headers: type ? { "Content-Type": type } : {} }));

    await expect(api.blob("/x")).rejects.toMatchObject({ code: "unexpected_content_type", message: UNEXPECTED_CONTENT_MESSAGE });
  });
});

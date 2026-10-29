// S4A-F1 · US-104 (front; S4A-D31, S4A-D35, S4A-D58): "Verificar ahora". 200 con el resultado,
// 202 con sondeo de GET /audit/verify/last hasta que cambie `finished_at` (tope de 900 s), 409, 429,
// cadena rota con enlace a `?seq=X`, la última verificación en hora de Bogotá, y la mutación por
// useSensitiveMutation: nada queda en la caché de mutaciones al terminar.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { verifyResult, verifyStarted } from "../../../test/audit";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { VERIFY_MAX_MS, VERIFY_MAX_POLLS, VERIFY_POLL_MS, lastVerificationPollLimit, useLastVerification } from "../api";
import { VERIFY_POLL_FAILED_MESSAGE, VerifyChainButton } from "./VerifyChainButton";

const OLD = verifyResult();
const NEW = verifyResult({ rows_checked: 5000, started_at: "2026-10-21T16:00:00Z", finished_at: "2026-10-21T16:04:00Z" });

function renderButton(handlers: Record<string, MockHandler>, { user = userEvent.setup(), queryClient = testQueryClient() }: { user?: ReturnType<typeof userEvent.setup>; queryClient?: QueryClient } = {}) {
  const mock = mockApi({ "GET /audit/verify/last": { status: 200, body: OLD }, ...handlers });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/sistema/auditoria?action=update"]}>
        <VerifyChainButton />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { mock, user, queryClient, ...view };
}

const verifyButton = (): HTMLElement => screen.getByRole("button", { name: "Verificar ahora" });

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("VerifyChainButton · resultado inmediato (200)", () => {
  it("muestra la última verificación en hora de Bogotá y el botón Verificar ahora", async () => {
    renderButton({});

    expect(await screen.findByText("Última verificación: 21 oct 2026, 10:00 a. m. · íntegra, 3.418 filas")).toBeInTheDocument();
    expect(verifyButton()).toBeEnabled();
  });

  it("sin verificaciones anteriores lo dice", async () => {
    renderButton({ "GET /audit/verify/last": { status: 200, body: null } });

    expect(await screen.findByText("Todavía no se ha verificado la cadena.")).toBeInTheDocument();
  });

  it("200 íntegra: Cadena íntegra con N filas y la fecha en Bogotá", async () => {
    const { mock, user } = renderButton({ "POST /audit/verify": { status: 200, body: NEW } });
    await screen.findByText(/Última verificación/);

    await user.click(verifyButton());

    expect(await screen.findByText("Cadena íntegra: 5.000 filas verificadas (21 oct 2026, 11:04 a. m.)")).toBeInTheDocument();
    expect(mock.callsTo("POST /audit/verify")).toHaveLength(1);
    expect(mock.callsTo("POST /audit/verify")[0]?.body).toBeUndefined();
  });

  it("la primera verificación dice que no hay una anterior que comparar", async () => {
    const { user } = renderButton({ "GET /audit/verify/last": { status: 200, body: null }, "POST /audit/verify": { status: 200, body: NEW } });
    await screen.findByText("Todavía no se ha verificado la cadena.");

    await user.click(verifyButton());

    expect(await screen.findByText(/Cadena íntegra: 5\.000 filas verificadas/)).toBeInTheDocument();
    expect(screen.getByText("Sin verificación anterior que comparar.")).toBeInTheDocument();
  });

  it("cadena rota: dice el registro y enlaza a ?seq=X conservando los filtros", async () => {
    const { user } = renderButton({ "POST /audit/verify": { status: 200, body: verifyResult({ ok: false, broken_at_seq: 120, rows_checked: 119 }) } });
    await screen.findByText(/Última verificación/);

    await user.click(verifyButton());

    expect(await screen.findByText(/Cadena rota en el registro seq 120/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Ver el registro 120" });
    const href = new URL(link.getAttribute("href") ?? "", "http://apex.test");
    expect(href.searchParams.get("seq")).toBe("120");
    expect(href.searchParams.get("action")).toBe("update");
  });

  it("mientras verifica el botón se deshabilita y dice Verificando…", async () => {
    const { user } = renderButton({ "POST /audit/verify": () => new Promise(() => undefined) });
    await screen.findByText(/Última verificación/);

    await user.click(verifyButton());

    expect(await screen.findByRole("button", { name: "Verificando…" })).toBeDisabled();
  });

  it("la mutación usa useSensitiveMutation: tras terminar no queda data en el MutationCache", async () => {
    const { queryClient, user } = renderButton({ "POST /audit/verify": { status: 200, body: NEW } });
    await screen.findByText(/Última verificación/);

    await user.click(verifyButton());
    await screen.findByText(/Cadena íntegra/);

    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll().filter((m) => m.state.data !== undefined)).toEqual([]);
    });
  });
});

describe("VerifyChainButton · errores", () => {
  it("409: ya hay una verificación en curso", async () => {
    const { user } = renderButton({ "POST /audit/verify": { status: 409, body: { error: { code: "verification_running", message: "x" } } } });
    await screen.findByText(/Última verificación/);

    await user.click(verifyButton());

    expect(await screen.findByText("Ya hay una verificación en curso. Espera a que termine; el resultado aparece aquí.")).toBeInTheDocument();
  });

  it("429: demasiadas verificaciones, con la espera", async () => {
    const { user } = renderButton({ "POST /audit/verify": { status: 429, body: { error: { code: "rate_limited", message: "x" } } } });
    await screen.findByText(/Última verificación/);

    await user.click(verifyButton());

    expect(await screen.findByText("Demasiadas verificaciones; espera un momento y vuelve a intentarlo.")).toBeInTheDocument();
  });

  it("500: no se pudo verificar", async () => {
    const { user } = renderButton({ "POST /audit/verify": { status: 500, body: { error: { code: "internal_error", message: "x" } } } });
    await screen.findByText(/Última verificación/);

    await user.click(verifyButton());

    expect(await screen.findByText("No pudimos verificar la cadena. Intenta de nuevo en un momento.")).toBeInTheDocument();
    expect(verifyButton()).toBeEnabled();
  });
});

describe("VerifyChainButton · segundo plano (202) con sondeo", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    vi.stubGlobal("jest", {
      advanceTimersByTime: (ms: number) => {
        vi.advanceTimersByTime(ms);
      },
    });
  });

  const fakeUser = () =>
    userEvent.setup({
      advanceTimers: (ms) => {
        vi.advanceTimersByTime(ms);
      },
    });

  it("202: sondea GET /audit/verify/last hasta que cambia finished_at y muestra el resultado", async () => {
    let current = OLD;
    const { mock, user } = renderButton({ "GET /audit/verify/last": () => ({ status: 200, body: current }), "POST /audit/verify": { status: 202, body: verifyStarted(OLD) } }, { user: fakeUser() });
    await screen.findByText(/Última verificación/);
    const before = mock.callsTo("GET /audit/verify/last").length;

    await user.click(verifyButton());
    expect(await screen.findByText("Verificando la cadena en segundo plano…")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(VERIFY_POLL_MS);
    });
    expect(mock.callsTo("GET /audit/verify/last").length).toBeGreaterThan(before);
    expect(screen.queryByText(/Cadena íntegra/)).not.toBeInTheDocument();

    current = NEW;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VERIFY_POLL_MS);
    });

    expect(await screen.findByText(/Cadena íntegra: 5\.000 filas verificadas/)).toBeInTheDocument();
    const settled = mock.callsTo("GET /audit/verify/last").length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VERIFY_POLL_MS * 5);
    });
    expect(mock.callsTo("GET /audit/verify/last")).toHaveLength(settled);
  });

  it("202 sin verificación anterior: el primer resultado que llega cuenta", async () => {
    let current: unknown = null;
    const { user } = renderButton({ "GET /audit/verify/last": () => ({ status: 200, body: current }), "POST /audit/verify": { status: 202, body: verifyStarted(null) } }, { user: fakeUser() });
    await screen.findByText("Todavía no se ha verificado la cadena.");

    await user.click(verifyButton());
    current = NEW;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VERIFY_POLL_MS);
    });

    expect(await screen.findByText(/Cadena íntegra: 5\.000 filas verificadas/)).toBeInTheDocument();
  });

  it("tope de 900 s: deja de sondear y dice que la verificación no terminó", async () => {
    const { mock, user } = renderButton({ "POST /audit/verify": { status: 202, body: verifyStarted(OLD) } }, { user: fakeUser() });
    await screen.findByText(/Última verificación/);

    await user.click(verifyButton());
    await screen.findByText("Verificando la cadena en segundo plano…");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VERIFY_MAX_MS);
    });

    expect(await screen.findByText("La verificación no terminó; vuelve a intentarlo.")).toBeInTheDocument();
    const polls = mock.callsTo("GET /audit/verify/last").length;
    expect(polls).toBeLessThanOrEqual(VERIFY_MAX_MS / VERIFY_POLL_MS + 2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VERIFY_POLL_MS * 10);
    });
    expect(mock.callsTo("GET /audit/verify/last")).toHaveLength(polls);
    expect(verifyButton()).toBeEnabled();
  });
});

describe("VerifyChainButton · sondeo acotado (revisión de seguridad de F1, MEDIUM 1)", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    vi.stubGlobal("jest", {
      advanceTimersByTime: (ms: number) => {
        vi.advanceTimersByTime(ms);
      },
    });
  });

  it("un 429 en el sondeo lo frena: no hay más peticiones y la pantalla lo dice", async () => {
    let limited = false;
    const user = userEvent.setup({
      advanceTimers: (ms) => {
        vi.advanceTimersByTime(ms);
      },
    });
    const { mock } = renderButton(
      {
        "GET /audit/verify/last": () => (limited ? { status: 429, body: { error: { code: "rate_limited", message: "x" } } } : { status: 200, body: OLD }),
        "POST /audit/verify": { status: 202, body: verifyStarted(OLD) },
      },
      { user },
    );
    await screen.findByText(/Última verificación/);

    await user.click(verifyButton());
    await screen.findByText("Verificando la cadena en segundo plano…");
    limited = true;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VERIFY_POLL_MS);
    });

    expect(await screen.findByText(VERIFY_POLL_FAILED_MESSAGE)).toBeInTheDocument();
    const polls = mock.callsTo("GET /audit/verify/last").length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VERIFY_POLL_MS * 10);
    });
    expect(mock.callsTo("GET /audit/verify/last")).toHaveLength(polls);
    expect(verifyButton()).toBeEnabled();
  });

  it("useLastVerification se detiene tras maxUpdates lecturas aunque finished_at no cambie", async () => {
    const mock = mockApi({ "GET /audit/verify/last": { status: 200, body: OLD } });
    const queryClient = testQueryClient();
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useLastVerification({ polling: true, baseline: OLD.finished_at, maxUpdates: 4 }), { wrapper });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.data).toEqual(OLD);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(VERIFY_POLL_MS * 20);
    });

    expect(mock.callsTo("GET /audit/verify/last")).toHaveLength(4);
    expect(lastVerificationPollLimit(queryClient)).toBe(4 + VERIFY_MAX_POLLS);
  });
});

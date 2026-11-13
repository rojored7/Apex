// S6-F2 · US-145 (S6-D16, S6-B2): trabajos de rotación y recifrado. Barra de progreso con el porcentaje
// también en texto; la tabla se relee cada 5 s solo mientras haya un trabajo pendiente o en curso (con
// temporizadores falsos) y se detiene al terminar o al fallar una lectura. Sin el texto `error` del api.
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { JOBS_POLL_MS } from "../api";
import { apiError, cryptoJob, jobsReply, lastGet, renderKeys } from "../../../test/keys";
import { CryptoJobs } from "./CryptoJobs";

const BASE = "/sistema/llaves?tab=trabajos";
async function loadedTable(): Promise<HTMLElement> {
  const table = await screen.findByRole("table", { name: "Trabajos de rotación y recifrado" });
  await waitFor(() => {
    expect(screen.queryByText("Cargando…")).not.toBeInTheDocument();
  });
  return table;
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function useFakeTimers(): ReturnType<typeof userEvent.setup> {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
  vi.stubGlobal("jest", {
    advanceTimersByTime: (ms: number) => {
      vi.advanceTimersByTime(ms);
    },
  });
  return userEvent.setup({
    advanceTimers: (ms) => {
      vi.advanceTimersByTime(ms);
    },
  });
}

describe("CryptoJobs · tabla", () => {
  it("pide limit 25 y offset 0 y pinta tipo, clase, estado, avance y fechas de Bogotá", async () => {
    const { mock, container } = renderKeys(<CryptoJobs />, BASE);

    const table = await loadedTable();
    expect(Object.fromEntries(lastGet(mock.calls, "/crypto/jobs"))).toEqual({ limit: "25", offset: "0" });
    const row = within(table).getByRole("row", { name: /member\.phone/ });
    for (const text of ["Rotación", "En curso", "212 de 342", "20 oct 2026, 9:00 a. m."]) {
      expect(within(row).getByText(text)).toBeInTheDocument();
    }
    expect(await axe(container)).toHaveNoViolations();
  });

  it("la barra de progreso trae el porcentaje en texto y como valor accesible", async () => {
    renderKeys(<CryptoJobs />, BASE);
    const table = await loadedTable();

    const bar = within(table).getByRole("progressbar", { name: /Avance.*rotación de member\.phone/ });
    expect(bar).toHaveAttribute("value", "61");
    expect(bar).toHaveAttribute("max", "100");
    expect(within(table).getByText("61 %")).toBeInTheDocument();
  });

  it.each([
    ["pending", "Pendiente"],
    ["done", "Terminado"],
    ["failed", "Falló"],
  ] as const)("el estado %s se lee «%s»", async (status, label) => {
    renderKeys(<CryptoJobs />, BASE, { handlers: { "GET /crypto/jobs": (call) => jobsReply(call, [cryptoJob({ status, percent: status === "done" ? 100 : 0, done: status === "done" ? 342 : 0 })]) } });
    const table = await loadedTable();

    expect(within(table).getByText(label)).toBeInTheDocument();
  });

  it.each([
    ["reencrypt", "Recifrado"],
    ["migrate_provider", "Cambio de proveedor"],
    ["rewrap", "Re-envoltura"],
  ] as const)("el tipo %s se lee «%s»", async (kind, label) => {
    renderKeys(<CryptoJobs />, BASE, { handlers: { "GET /crypto/jobs": (call) => jobsReply(call, [cryptoJob({ kind, status: "done", percent: 100 })]) } });
    const table = await loadedTable();

    expect(within(table).getByText(label)).toBeInTheDocument();
  });

  it("un trabajo sin clase de dato (migración de proveedor) no inventa una", async () => {
    renderKeys(<CryptoJobs />, BASE, { handlers: { "GET /crypto/jobs": (call) => jobsReply(call, [cryptoJob({ kind: "migrate_provider", data_class: null, status: "done", percent: 100 })]) } });
    const table = await loadedTable();

    expect(within(table).getAllByText("—").length).toBeGreaterThanOrEqual(1);
  });

  it("Siguiente pide offset 25", async () => {
    const { mock, user } = renderKeys(<CryptoJobs />, BASE, { handlers: { "GET /crypto/jobs": (call) => jobsReply(call, [cryptoJob()], 60) } });
    await loadedTable();

    await user.click(screen.getByRole("button", { name: /Siguiente/ }));

    await vi.waitFor(() => {
      expect(lastGet(mock.calls, "/crypto/jobs").get("offset")).toBe("25");
    });
  });
});

describe("CryptoJobs · refresco cada 5 s", () => {
  it("mientras hay un trabajo en curso vuelve a pedir cada 5 s y se detiene al terminar", async () => {
    useFakeTimers();
    let current = [cryptoJob()];
    const { mock } = renderKeys(<CryptoJobs />, BASE, { handlers: { "GET /crypto/jobs": (call) => jobsReply(call, current) } });
    await loadedTable();
    const first = mock.callsTo("GET /crypto/jobs").length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(JOBS_POLL_MS);
    });
    const second = mock.callsTo("GET /crypto/jobs").length;
    expect(second).toBeGreaterThan(first);

    current = [cryptoJob({ status: "done", percent: 100, done: 342, finished_at: "2026-10-20T14:05:00Z" })];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(JOBS_POLL_MS);
    });
    expect(await screen.findByText("Terminado")).toBeInTheDocument();
    const settled = mock.callsTo("GET /crypto/jobs").length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(JOBS_POLL_MS * 6);
    });
    expect(mock.callsTo("GET /crypto/jobs")).toHaveLength(settled);
  });

  it("un trabajo pendiente también se sigue (el worker aún no lo toma)", async () => {
    useFakeTimers();
    const { mock } = renderKeys(<CryptoJobs />, BASE, { handlers: { "GET /crypto/jobs": (call) => jobsReply(call, [cryptoJob({ status: "pending", percent: 0, done: 0, started_at: null })]) } });
    await loadedTable();
    const first = mock.callsTo("GET /crypto/jobs").length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(JOBS_POLL_MS);
    });

    expect(mock.callsTo("GET /crypto/jobs").length).toBeGreaterThan(first);
  });

  it("sin trabajos en curso no vuelve a pedir", async () => {
    useFakeTimers();
    const { mock } = renderKeys(<CryptoJobs />, BASE, { handlers: { "GET /crypto/jobs": (call) => jobsReply(call, [cryptoJob({ status: "done", percent: 100 }), cryptoJob({ id: "77777777-7777-4777-8777-777777777778", status: "failed" })]) } });
    await loadedTable();
    const first = mock.callsTo("GET /crypto/jobs").length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(JOBS_POLL_MS * 6);
    });

    expect(mock.callsTo("GET /crypto/jobs")).toHaveLength(first);
  });

  it("un error de lectura frena el refresco", async () => {
    useFakeTimers();
    let fail = false;
    const { mock } = renderKeys(<CryptoJobs />, BASE, {
      handlers: { "GET /crypto/jobs": (call) => (fail ? apiError(500, "internal_error", "x") : jobsReply(call, [cryptoJob()])) },
    });
    await loadedTable();
    fail = true;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(JOBS_POLL_MS);
    });
    const afterError = mock.callsTo("GET /crypto/jobs").length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(JOBS_POLL_MS * 6);
    });

    expect(mock.callsTo("GET /crypto/jobs")).toHaveLength(afterError);
  });

  it("al terminar un trabajo invalida las llaves y el resumen (cambian de estado)", async () => {
    useFakeTimers();
    let current = [cryptoJob()];
    const { queryClient } = renderKeys(<CryptoJobs />, BASE, { handlers: { "GET /crypto/jobs": (call) => jobsReply(call, current) } });
    await loadedTable();
    const spy = vi.spyOn(queryClient, "invalidateQueries");

    current = [cryptoJob({ status: "done", percent: 100, done: 342 })];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(JOBS_POLL_MS);
    });
    await screen.findByText("Terminado");

    expect(spy).toHaveBeenCalledWith({ queryKey: ["crypto", "keys"] });
  });
});

describe("CryptoJobs · estados", () => {
  it("carga", () => {
    renderKeys(<CryptoJobs />, BASE);

    expect(screen.getByText("Cargando…")).toBeInTheDocument();
  });

  it("vacío: explica de dónde salen los trabajos y guía a la pestaña Inventario", async () => {
    renderKeys(<CryptoJobs />, BASE, { handlers: { "GET /crypto/jobs": (call) => jobsReply(call, [], 0) } });

    expect(await screen.findByText("Todavía no hay trabajos de rotación ni de recifrado")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ir al inventario" })).toBeInTheDocument();
  });

  it("error 500 con Reintentar", async () => {
    renderKeys(<CryptoJobs />, BASE, { handlers: { "GET /crypto/jobs": apiError(500, "internal_error", "x") } });

    expect(await screen.findByText("No pudimos cargar los trabajos. Intenta de nuevo en un momento.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });

  it("403 sin permiso", async () => {
    renderKeys(<CryptoJobs />, BASE, { handlers: { "GET /crypto/jobs": apiError(403, "forbidden", "x") } });

    expect(await screen.findByText("No tienes permiso para ver los trabajos. Solo un administrador puede consultarlos.")).toBeInTheDocument();
  });

  it("nunca pinta un texto de error del api", async () => {
    const leaking = { ...cryptoJob({ status: "failed" }), error: "vault: permission denied" };
    renderKeys(<CryptoJobs />, BASE, { handlers: { "GET /crypto/jobs": (call) => jobsReply(call, [leaking]) } });

    expect(await screen.findByText(/La respuesta del servidor no es válida/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("vault");
  });
});

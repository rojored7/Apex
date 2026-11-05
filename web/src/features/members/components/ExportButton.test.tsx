// S5-F4 · US-138 (front): "Exportar" de /socios. Solo admin (`members.export`); confirmación con el
// texto fijo de datos personales y auditoría; envía los filtros vigentes a GET /members/export; los
// errores 403, 409, 422, 429 y 503 se quedan dentro del modal con el mensaje del api; el CSV nunca se
// guarda (ni en la caché de mutaciones ni en el almacenamiento del navegador).
import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { api } from "../../../core/api/client";
import { RoleProvider, type Role } from "../../../core/auth";
import { mockApi, testQueryClient, type MockHandler, type MockReply } from "../../../test/server";
import { EXPORT_CONFIRM_LABEL, EXPORT_TITLE, ExportButton, type MembersExportFilters } from "./ExportButton";

const saved = vi.hoisted(() => ({ calls: [] as { filename: string | null; text: string; fallback: string }[] }));

vi.mock("../../../shared/lib/download", () => ({
  saveDownload: vi.fn(async (result: { blob: Blob; filename: string | null }, fallback: string) => {
    saved.calls.push({ filename: result.filename, text: await result.blob.text(), fallback });
  }),
}));

const EXPORT_KEY = "GET /members/export";
const FIXED_TEXT = "La descarga contiene datos personales y queda registrada en la auditoría";
const CSV: MockReply = { status: 200, file: { content: "nombre;documento\r\n", contentType: "text/csv; charset=utf-8", filename: "socios-20261105.csv" } };

const failure = (status: number, code: string, message: string, headers?: Record<string, string>): MockReply => ({
  status,
  body: { error: { code, message } },
  ...(headers ? { headers } : {}),
});

function renderButton(role: Role, filters: MembersExportFilters = {}, handlers: Record<string, MockHandler> = {}) {
  const mock = mockApi({ [EXPORT_KEY]: CSV, ...handlers });
  const queryClient = testQueryClient();
  const view = render(
    <QueryClientProvider client={queryClient}>
      <RoleProvider value={role}>
        <main>
          <h1>Socios</h1>
          <ExportButton filters={filters} />
        </main>
      </RoleProvider>
    </QueryClientProvider>,
  );
  return { mock, queryClient, user: userEvent.setup(), ...view };
}

const dialog = () => screen.getByRole("dialog", { name: EXPORT_TITLE });
const confirmButton = () => within(dialog()).getByRole("button", { name: EXPORT_CONFIRM_LABEL });

beforeEach(() => {
  saved.calls.length = 0;
});

afterEach(() => {
  vi.useRealTimers();
  cleanup();
  vi.unstubAllGlobals();
});

describe("ExportButton de socios", () => {
  it("solo el admin lo ve: el coach y el socio no", () => {
    renderButton("coach");
    expect(screen.queryByRole("button", { name: "Exportar" })).not.toBeInTheDocument();
    cleanup();

    renderButton("member");
    expect(screen.queryByRole("button", { name: "Exportar" })).not.toBeInTheDocument();
    cleanup();

    renderButton("admin");
    expect(screen.getByRole("button", { name: "Exportar" })).toBeInTheDocument();
  });

  it("pide confirmar con el texto fijo y no llama al api hasta confirmar", async () => {
    const { mock, user } = renderButton("admin");

    await user.click(screen.getByRole("button", { name: "Exportar" }));

    expect(dialog()).toHaveTextContent(FIXED_TEXT);
    expect(mock.callsTo(EXPORT_KEY)).toHaveLength(0);
    await user.click(within(dialog()).getByRole("button", { name: "Volver" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.callsTo(EXPORT_KEY)).toHaveLength(0);
  });

  it("confirma, descarga el CSV con el nombre del api y cierra el modal", async () => {
    const { mock, user } = renderButton("admin");

    await user.click(screen.getByRole("button", { name: "Exportar" }));
    await user.click(confirmButton());

    await waitFor(() => {
      expect(saved.calls).toHaveLength(1);
    });
    expect(saved.calls[0]).toMatchObject({ filename: "socios-20261105.csv", text: "nombre;documento\r\n" });
    expect(saved.calls[0]?.fallback).toMatch(/^socios-\d{8}\.csv$/);
    expect(mock.callsTo(EXPORT_KEY)).toHaveLength(1);
    expect(mock.callsTo(EXPORT_KEY)[0]?.method).toBe("GET");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("sin filtros pide la ruta sin query string", async () => {
    const { mock, user } = renderButton("admin");

    await user.click(screen.getByRole("button", { name: "Exportar" }));
    await user.click(confirmButton());

    await waitFor(() => {
      expect(mock.callsTo(EXPORT_KEY)).toHaveLength(1);
    });
    expect(new URL(mock.callsTo(EXPORT_KEY)[0]?.url ?? "", "http://apex.test").search).toBe("");
  });

  it("envía los filtros vigentes de la URL: búsqueda, estado, estado de la membresía y plan", async () => {
    const planId = "11111111-1111-4111-8111-111111111111";
    const { mock, user } = renderButton("admin", { q: "ana", status: "deleted", membership_status: "active", plan_id: planId });

    await user.click(screen.getByRole("button", { name: "Exportar" }));
    await user.click(confirmButton());

    await waitFor(() => {
      expect(mock.callsTo(EXPORT_KEY)).toHaveLength(1);
    });
    const params = new URL(mock.callsTo(EXPORT_KEY)[0]?.url ?? "", "http://apex.test").searchParams;
    expect(Object.fromEntries(params)).toEqual({ q: "ana", status: "deleted", membership_status: "active", plan_id: planId });
  });

  it("mientras descarga muestra el botón ocupado y no permite cancelar ni repetir", async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const { mock, user } = renderButton("admin", {}, {
      [EXPORT_KEY]: async () => {
        await gate;
        return CSV;
      },
    });

    await user.click(screen.getByRole("button", { name: "Exportar" }));
    await user.click(confirmButton());

    await waitFor(() => {
      expect(confirmButton()).toHaveAttribute("aria-busy", "true");
    });
    expect(confirmButton()).toBeDisabled();
    expect(within(dialog()).getByRole("button", { name: "Volver" })).toBeDisabled();
    expect(mock.callsTo(EXPORT_KEY)).toHaveLength(1);

    release?.();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it.each([
    [403, "forbidden", "Forbidden", "No tienes permiso para descargar esta información."],
    [409, "export_in_progress", "Ya tienes una exportación en curso. Espera a que termine.", "Ya tienes una exportación en curso. Espera a que termine."],
    [422, "export_too_large", "La exportación supera el máximo de filas. Acota los filtros.", "La exportación supera el máximo de filas. Acota los filtros."],
    [503, "crypto_unavailable", "El custodio de llaves no está disponible. Avise al administrador para desellarlo.", "El custodio de llaves no está disponible. Avise al administrador para desellarlo."],
    [429, "rate_limited", "x", "Hiciste muchas descargas seguidas."],
    [500, "internal_error", "boom", "No pudimos preparar la descarga. Intenta de nuevo en un momento."],
  ])("%i %s: el error queda dentro del modal, que sigue abierto", async (status, code, message, shown) => {
    const { user } = renderButton("admin", {}, { [EXPORT_KEY]: failure(status, code, message, status === 429 ? { "Retry-After": "30" } : undefined) });

    await user.click(screen.getByRole("button", { name: "Exportar" }));
    await user.click(confirmButton());

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(shown);
    expect(saved.calls).toHaveLength(0);
    expect(confirmButton()).toBeEnabled();
  });

  it("tras un error se puede reintentar y la descarga que sale bien cierra el modal", async () => {
    let attempt = 0;
    const { user } = renderButton("admin", {}, {
      [EXPORT_KEY]: () => {
        attempt += 1;
        return attempt === 1 ? failure(409, "export_in_progress", "Ya tienes una exportación en curso. Espera a que termine.") : CSV;
      },
    });

    await user.click(screen.getByRole("button", { name: "Exportar" }));
    await user.click(confirmButton());
    await within(dialog()).findByRole("alert");
    await user.click(confirmButton());

    await waitFor(() => {
      expect(saved.calls).toHaveLength(1);
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("nunca almacena el CSV: ni en la caché de mutaciones ni en el almacenamiento del navegador", async () => {
    const setItem = vi.fn();
    vi.stubGlobal("localStorage", { setItem, getItem: vi.fn(), removeItem: vi.fn() });
    vi.stubGlobal("sessionStorage", { setItem, getItem: vi.fn(), removeItem: vi.fn() });
    const { queryClient, user } = renderButton("admin", { q: "ana" });

    await user.click(screen.getByRole("button", { name: "Exportar" }));
    await user.click(confirmButton());
    await waitFor(() => {
      expect(saved.calls).toHaveLength(1);
    });

    expect(setItem).not.toHaveBeenCalled();
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
  });

  it("el modal abierto no tiene violaciones de accesibilidad", async () => {
    const { user } = renderButton("admin");

    await user.click(screen.getByRole("button", { name: "Exportar" }));

    expect(await axe(dialog())).toHaveNoViolations();
  });
});

describe("ExportButton de socios · revisión de seguridad de F4", () => {
  it("LOW 2: un 503 busy muestra la espera y deshabilita Descargar ese tiempo, sin reintento automático", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const { mock } = renderButton("admin", {}, { [EXPORT_KEY]: failure(503, "busy", "x", { "Retry-After": "1" }) });

    fireEvent.click(screen.getByRole("button", { name: "Exportar" }));
    fireEvent.click(confirmButton());

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(within(dialog()).getByRole("alert")).toHaveTextContent("Espera 1 segundo");
    expect(confirmButton()).toBeDisabled();
    expect(mock.callsTo(EXPORT_KEY)).toHaveLength(1);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(confirmButton()).toBeEnabled();
    expect(mock.callsTo(EXPORT_KEY)).toHaveLength(1);
    vi.useRealTimers();
  });

  it("LOW 1: al desmontar durante la descarga no se entrega nada", async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const blob = vi.spyOn(api, "blob");
    const { mock, user, unmount } = renderButton("admin", {}, {
      [EXPORT_KEY]: async () => {
        await gate;
        return CSV;
      },
    });

    await user.click(screen.getByRole("button", { name: "Exportar" }));
    await user.click(confirmButton());
    await waitFor(() => {
      expect(mock.callsTo(EXPORT_KEY)).toHaveLength(1);
    });
    unmount();
    release?.();
    await expect(blob.mock.results[0]?.value).resolves.toBeDefined();
    await Promise.resolve();

    expect(saved.calls).toHaveLength(0);
  });
});

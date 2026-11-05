// S5-F4 · US-139 (front): "Exportar" de /pagos. Solo admin (`payments.export`); confirmación con el
// texto fijo de datos personales y auditoría; el rango de "Fecha del pago" es obligatorio y de 12
// meses como máximo, validado con Zod ANTES de llamar a GET /payments/export; envía los filtros
// vigentes con el rango en UTC; 403, 409, 422 y 503 con el mensaje del api; el CSV nunca se guarda.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { RoleProvider, type Role } from "../../../core/auth";
import { mockApi, testQueryClient, type MockHandler, type MockReply } from "../../../test/server";
import { EXPORT_RANGE_MESSAGES, type PaymentsExportFilters } from "../exportSchema";
import { EXPORT_BLOCKED_NOTE, EXPORT_CONFIRM_LABEL, EXPORT_TITLE, ExportButton } from "./ExportButton";

const saved = vi.hoisted(() => ({ calls: [] as { filename: string | null; text: string; fallback: string }[] }));

vi.mock("../../../shared/lib/download", () => ({
  saveDownload: vi.fn(async (result: { blob: Blob; filename: string | null }, fallback: string) => {
    saved.calls.push({ filename: result.filename, text: await result.blob.text(), fallback });
  }),
}));

const EXPORT_KEY = "GET /payments/export";
const FIXED_TEXT = "La descarga contiene datos personales y queda registrada en la auditoría";
const OCTOBER = { from: "2026-10-01", to: "2026-10-31" };
const CSV: MockReply = { status: 200, file: { content: "fecha;socio\r\n", contentType: "text/csv; charset=utf-8", filename: "pagos-20261105.csv" } };

const failure = (status: number, code: string, message: string, extra: Record<string, unknown> = {}, headers?: Record<string, string>): MockReply => ({
  status,
  body: { error: { code, message, ...extra } },
  ...(headers ? { headers } : {}),
});

interface Setup {
  range?: { from: string; to: string };
  filters?: PaymentsExportFilters;
  blocked?: boolean;
  handlers?: Record<string, MockHandler>;
}

function renderButton(role: Role, { range = OCTOBER, filters = {}, blocked = false, handlers = {} }: Setup = {}) {
  const mock = mockApi({ [EXPORT_KEY]: CSV, ...handlers });
  const queryClient = testQueryClient();
  const view = render(
    <QueryClientProvider client={queryClient}>
      <RoleProvider value={role}>
        <main>
          <h1>Pagos</h1>
          <ExportButton range={range} filters={filters} blocked={blocked} />
        </main>
      </RoleProvider>
    </QueryClientProvider>,
  );
  return { mock, queryClient, user: userEvent.setup(), ...view };
}

const dialog = () => screen.getByRole("dialog", { name: EXPORT_TITLE });
const confirmButton = () => within(dialog()).getByRole("button", { name: EXPORT_CONFIRM_LABEL });
const paramsOf = (call: { url: string } | undefined) => Object.fromEntries(new URL(call?.url ?? "", "http://apex.test").searchParams);

async function openAndConfirm(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.click(screen.getByRole("button", { name: "Exportar" }));
  await user.click(confirmButton());
}

beforeEach(() => {
  saved.calls.length = 0;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ExportButton de pagos", () => {
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
    await user.click(within(dialog()).getByRole("button", { name: "Volver" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.callsTo(EXPORT_KEY)).toHaveLength(0);
  });

  it("envía el rango en UTC de Bogotá ([from, to) con el día siguiente) y los filtros vigentes", async () => {
    const registeredBy = "22222222-2222-4222-8222-222222222222";
    const { mock, user } = renderButton("admin", { filters: { q: "ana", method: "nequi", registered_by: registeredBy, voided: false } });

    await openAndConfirm(user);

    await waitFor(() => {
      expect(saved.calls).toHaveLength(1);
    });
    expect(paramsOf(mock.callsTo(EXPORT_KEY)[0])).toEqual({
      from: "2026-10-01T05:00:00.000Z",
      to: "2026-11-01T05:00:00.000Z",
      q: "ana",
      method: "nequi",
      registered_by: registeredBy,
      voided: "false",
    });
    expect(saved.calls[0]).toMatchObject({ filename: "pagos-20261105.csv", text: "fecha;socio\r\n" });
    expect(saved.calls[0]?.fallback).toMatch(/^pagos-\d{8}\.csv$/);
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it.each([
    ["sin 'Desde'", { from: "", to: "2026-10-31" }, EXPORT_RANGE_MESSAGES.fromRequired],
    ["sin 'Hasta'", { from: "2026-10-01", to: "" }, EXPORT_RANGE_MESSAGES.toRequired],
    ["sin rango", { from: "", to: "" }, EXPORT_RANGE_MESSAGES.fromRequired],
    ["invertido", { from: "2026-10-31", to: "2026-10-01" }, EXPORT_RANGE_MESSAGES.inverted],
    ["de más de 12 meses", { from: "2025-10-01", to: "2026-10-31" }, EXPORT_RANGE_MESSAGES.tooLong],
  ])("rango %s: lo explica dentro del modal y no llama al api", async (_name, range, message) => {
    const { mock, user } = renderButton("admin", { range });

    await openAndConfirm(user);

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(message);
    expect(mock.callsTo(EXPORT_KEY)).toHaveLength(0);
    expect(saved.calls).toHaveLength(0);
  });

  it("un rango de exactamente 12 meses sí se exporta", async () => {
    const { mock, user } = renderButton("admin", { range: { from: "2025-11-01", to: "2026-10-31" } });

    await openAndConfirm(user);

    await waitFor(() => {
      expect(saved.calls).toHaveLength(1);
    });
    expect(paramsOf(mock.callsTo(EXPORT_KEY)[0])).toMatchObject({ from: "2025-11-01T05:00:00.000Z", to: "2026-11-01T05:00:00.000Z" });
  });

  it.each([
    [403, "forbidden", "Forbidden", {}, "No tienes permiso para descargar esta información."],
    [409, "export_in_progress", "Ya tienes una exportación en curso. Espera a que termine.", {}, "Ya tienes una exportación en curso. Espera a que termine."],
    [422, "export_too_large", "La exportación supera el máximo de filas. Acota los filtros.", {}, "La exportación supera el máximo de filas. Acota los filtros."],
    [422, "invalid_date_range", "El rango de fechas no es válido.", { field: "to" }, "El rango de fechas no es válido."],
    [503, "crypto_unavailable", "El custodio de llaves no está disponible. Avise al administrador para desellarlo.", {}, "El custodio de llaves no está disponible. Avise al administrador para desellarlo."],
    [429, "rate_limited", "x", {}, "Hiciste muchas descargas seguidas."],
  ])("%i %s: el error queda dentro del modal, que sigue abierto", async (status, code, message, extra, shown) => {
    const { user } = renderButton("admin", { handlers: { [EXPORT_KEY]: failure(status, code, message, extra, status === 429 ? { "Retry-After": "30" } : undefined) } });

    await openAndConfirm(user);

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent(shown);
    expect(saved.calls).toHaveLength(0);
    expect(confirmButton()).toBeEnabled();
  });

  it("mientras descarga muestra el botón ocupado y no repite la petición", async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const { mock, user } = renderButton("admin", {
      handlers: {
        [EXPORT_KEY]: async () => {
          await gate;
          return CSV;
        },
      },
    });

    await openAndConfirm(user);

    await waitFor(() => {
      expect(confirmButton()).toHaveAttribute("aria-busy", "true");
    });
    expect(confirmButton()).toBeDisabled();
    expect(mock.callsTo(EXPORT_KEY)).toHaveLength(1);
    release?.();
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("con un filtro que la exportación no admite queda deshabilitado y lo explica", async () => {
    const { mock, user } = renderButton("admin", { blocked: true });

    const button = screen.getByRole("button", { name: "Exportar" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(EXPORT_BLOCKED_NOTE);
    await user.click(button);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.callsTo(EXPORT_KEY)).toHaveLength(0);
  });

  it("nunca almacena el CSV: ni en la caché de mutaciones ni en el almacenamiento del navegador", async () => {
    const setItem = vi.fn();
    vi.stubGlobal("localStorage", { setItem, getItem: vi.fn(), removeItem: vi.fn() });
    vi.stubGlobal("sessionStorage", { setItem, getItem: vi.fn(), removeItem: vi.fn() });
    const { queryClient, user } = renderButton("admin");

    await openAndConfirm(user);
    await waitFor(() => {
      expect(saved.calls).toHaveLength(1);
    });

    expect(setItem).not.toHaveBeenCalled();
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
  });

  it("el modal abierto y con un error no tiene violaciones de accesibilidad", async () => {
    const { user } = renderButton("admin", { range: { from: "", to: "" } });

    await openAndConfirm(user);
    await within(dialog()).findByRole("alert");

    expect(await axe(dialog())).toHaveNoViolations();
  });
});

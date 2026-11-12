// S6-F2 · US-143 a US-146 (Llaves.html, solo admin): /sistema/llaves. PageHeader «Llaves de cifrado» con
// «Exportar CBOM», tarjetas de resumen desde `summary` (llaves activas, recifrados en curso, operaciones
// hoy, proveedor activo y el DESIGN-GAP «Rotación vencida (30 días)» con `age_days`) y tres pestañas en la
// URL: Inventario, Bitácora y Trabajos. Claro y oscuro con axe; solo tokens.
import { readFileSync } from "node:fs";
import { screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { KEY_PHONE, KEYS, apiError, keysReply, keysSummary, lastGet, renderKeys, rotationStarted } from "../../../test/keys";
import KeysPage from "./KeysPage";

const SOURCES = [
  readFileSync("src/features/system/pages/KeysPage.tsx", "utf8"),
  readFileSync("src/features/system/pages/KeysPage.module.css", "utf8"),
  readFileSync("src/features/system/components/KeysSummaryCards.tsx", "utf8"),
];

afterEach(() => {
  delete document.documentElement.dataset.theme;
  vi.unstubAllGlobals();
});

const card = (name: string): HTMLElement => screen.getByRole("group", { name });
const renderPage = (entry = "/sistema/llaves", handlers: Parameters<typeof renderKeys>[2] = {}) => renderKeys(<KeysPage />, entry, handlers);

describe("KeysPage · encabezado y pestañas", () => {
  it("h1 «Llaves de cifrado», «Exportar CBOM» y tres pestañas con Inventario activa", async () => {
    renderPage();

    expect(screen.getByRole("heading", { level: 1, name: "Llaves de cifrado" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Exportar CBOM" })).toBeInTheDocument();
    const tabs = within(screen.getByRole("tablist", { name: "Secciones de llaves" })).getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Inventario", "Bitácora", "Trabajos"]);
    expect(screen.getByRole("tab", { name: "Inventario" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByRole("table", { name: "Inventario de llaves" })).toBeInTheDocument();
  });

  it("?tab=bitacora muestra la bitácora y ?tab=trabajos los trabajos", async () => {
    const first = renderPage("/sistema/llaves?tab=bitacora");
    expect(await screen.findByRole("table", { name: "Bitácora de operaciones" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Bitácora" })).toHaveAttribute("aria-selected", "true");
    first.unmount();

    renderPage("/sistema/llaves?tab=trabajos");
    expect(await screen.findByRole("table", { name: "Trabajos de rotación y recifrado" })).toBeInTheDocument();
  });

  it("una pestaña desconocida cae en Inventario", async () => {
    renderPage("/sistema/llaves?tab=secretos");

    expect(await screen.findByRole("table", { name: "Inventario de llaves" })).toBeInTheDocument();
  });

  it("cambiar de pestaña deja la elegida en la URL", async () => {
    const { user, router } = renderPage();

    await user.click(screen.getByRole("tab", { name: "Trabajos" }));

    expect(new URLSearchParams(router.state.location.search).get("tab")).toBe("trabajos");
    expect(await screen.findByRole("table", { name: "Trabajos de rotación y recifrado" })).toBeInTheDocument();
  });
});

describe("KeysPage · tarjetas de resumen", () => {
  it("muestra llaves activas, recifrados en curso y operaciones de hoy desde summary", async () => {
    renderPage();

    await waitFor(() => {
      expect(within(card("Llaves activas")).getByText("5")).toBeInTheDocument();
    });
    expect(within(card("Recifrados en curso")).getByText("1")).toBeInTheDocument();
    expect(within(card("Operaciones hoy")).getByText("1.204")).toBeInTheDocument();
  });

  it("«Rotación vencida (30 días)» es un DESIGN-GAP: muestra el age_days de la llave activa más antigua", async () => {
    renderPage();

    await waitFor(() => {
      expect(within(card("Rotación vencida (30 días)")).getByText("255")).toBeInTheDocument();
    });
    expect(within(card("Rotación vencida (30 días)")).getByText(/días la llave activa más antigua/)).toBeInTheDocument();
    expect(SOURCES[0]).toContain("DESIGN-GAP:");
  });

  it("las tarjetas leen todas las llaves de una vez (limit 200) aparte de la página del inventario", async () => {
    const { mock } = renderPage();
    await screen.findByRole("table", { name: "Inventario de llaves" });

    const limits = mock.callsTo("GET /crypto/keys").map((c) => new URL(c.url, "http://apex.test").searchParams.get("limit"));
    expect(limits).toContain("200");
    expect(limits).toContain("25");
  });

  it.each([
    [{ names: ["openbao"], state: "ok" }, "Proveedor activo: OpenBao · conectado"],
    [{ names: ["openbao"], state: "sealed" }, "Proveedor activo: OpenBao · sellado"],
    [{ names: ["local"], state: "unreachable" }, "Proveedor activo: Local · inalcanzable"],
    [{ names: ["local", "openbao"], state: "ok" }, "Proveedor activo: Local y OpenBao · conectado"],
    [{ names: ["openbao"], state: "unknown" }, "Proveedor activo: OpenBao · sin verificar"],
    [{ names: [], state: "unknown" }, "Proveedor activo: ninguno · sin verificar"],
  ])("el proveedor %j se lee «%s»", async (provider, text) => {
    renderPage("/sistema/llaves", { handlers: { "GET /crypto/keys": (call) => keysReply(call, KEYS, keysSummary({ provider })) } });

    expect(await screen.findByText(text)).toBeInTheDocument();
  });

  it("un proveedor sellado se muestra como alerta de texto, no solo con color", async () => {
    renderPage("/sistema/llaves", { handlers: { "GET /crypto/keys": (call) => keysReply(call, KEYS, keysSummary({ provider: { names: ["openbao"], state: "sealed" } })) } });

    expect(await screen.findByText(/El custodio de llaves está sellado/)).toBeInTheDocument();
  });

  it("mientras cargan, las tarjetas anuncian la carga", () => {
    renderPage();

    expect(within(card("Llaves activas")).getByText("Cargando")).toBeInTheDocument();
  });

  it("si el resumen falla, las tarjetas dicen «No se pudo cargar» y Reintentar vuelve a pedir", async () => {
    const { mock, user } = renderPage("/sistema/llaves", { handlers: { "GET /crypto/keys": apiError(500, "internal_error", "x") } });

    await waitFor(() => {
      expect(within(card("Llaves activas")).getByText("No se pudo cargar")).toBeInTheDocument();
    });
    const before = mock.callsTo("GET /crypto/keys").length;
    await user.click(within(card("Llaves activas")).getByRole("button", { name: "Reintentar" }));

    await waitFor(() => {
      expect(mock.callsTo("GET /crypto/keys").length).toBeGreaterThan(before);
    });
  });

  it("un campo extra en summary.provider (un token) invalida la respuesta: tarjetas en error y el texto no llega al DOM", async () => {
    const leaking = keysSummary({ provider: { names: ["openbao"], state: "ok", token: "vault:s.SECRETO" } });
    renderPage("/sistema/llaves", { handlers: { "GET /crypto/keys": (call) => keysReply(call, KEYS, leaking) } });

    await waitFor(() => {
      expect(within(card("Llaves activas")).getByText("No se pudo cargar")).toBeInTheDocument();
    });
    expect(document.body.textContent).not.toContain("SECRETO");
    expect(screen.queryByText(/Proveedor activo/)).not.toBeInTheDocument();
  });

  it("403: dice que solo un administrador ve las llaves", async () => {
    renderPage("/sistema/llaves", { handlers: { "GET /crypto/keys": apiError(403, "forbidden", "x") } });

    expect(await screen.findAllByText(/Solo un administrador puede consultarlas/)).not.toHaveLength(0);
  });
});

describe("KeysPage · rotar desde el inventario", () => {
  it("Rotar, motivo y ROTAR → 202 → salta a la pestaña Trabajos con la tabla", async () => {
    const { user, mock, router } = renderPage("/sistema/llaves", { handlers: { [`POST /crypto/keys/${KEY_PHONE}/rotate`]: rotationStarted() } });
    await user.click(await screen.findByRole("button", { name: "Rotar member.phone" }));
    const dialog = screen.getByRole("dialog", { name: "¿Rotar la llave de member.phone?" });
    await user.type(within(dialog).getByLabelText(/^Motivo/), "Rotación programada");
    await user.type(within(dialog).getByRole("textbox", { name: "Escribe ROTAR para confirmar" }), "ROTAR");
    await user.click(within(dialog).getByRole("button", { name: "Rotar llave" }));

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Trabajos" })).toHaveAttribute("aria-selected", "true");
    });
    expect(mock.callsTo(`POST /crypto/keys/${KEY_PHONE}/rotate`)).toHaveLength(1);
    expect(new URLSearchParams(router.state.location.search).get("tab")).toBe("trabajos");
    expect(await screen.findByRole("table", { name: "Trabajos de rotación y recifrado" })).toBeInTheDocument();
    expect(lastGet(mock.calls, "/crypto/jobs").get("limit")).toBe("25");
  });
});

describe("KeysPage · diseño", () => {
  it.each([
    ["claro", null],
    ["oscuro", "dark"],
  ])("sin violaciones de accesibilidad en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    const { container } = renderPage();
    await screen.findByRole("table", { name: "Inventario de llaves" });
    await waitFor(() => {
      expect(within(card("Llaves activas")).getByText("5")).toBeInTheDocument();
    });

    expect(await axe(container)).toHaveNoViolations();
  });

  it("solo usa tokens: ni colores literales ni fuentes literales", () => {
    const code = SOURCES.join("\n");

    expect(code).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(code).not.toMatch(/\b(rgb|rgba|hsl|hsla|oklch)\(/);
    expect(code).not.toMatch(/font-family\s*:\s*(?!var\()/);
  });
});

// S6-F2 · US-143 (S6-D13, S6-D16): inventario de llaves (Llaves.html, pestaña Inventario). DataTable
// paginada en el servidor con filtros de propósito, estado y proveedor en la URL; StatusTag de texto,
// hora de Bogotá, `records_count` o «n/a»; «Rotar» solo en filas activas de propósito `encrypt`.
// Nunca se pinta material de llave: el contrato no lo trae y Zod rechaza campos extra.
import { screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { KEYS, apiError, cryptoKey, keysReply, keysSummary, lastGet, renderKeys } from "../../../test/keys";
import { KeysInventory } from "./KeysInventory";

afterEach(() => {
  vi.unstubAllGlobals();
});

async function loadedTable(): Promise<HTMLElement> {
  const table = await screen.findByRole("table", { name: "Inventario de llaves" });
  await waitFor(() => {
    expect(screen.queryByText("Cargando…")).not.toBeInTheDocument();
  });
  return table;
}

const rowOf = (table: HTMLElement, pattern: RegExp): HTMLElement => within(table).getByRole("row", { name: pattern });

describe("KeysInventory · tabla", () => {
  it("pide la primera página con limit 25 y offset 0 y pinta una fila por llave", async () => {
    const { mock, container } = renderKeys(<KeysInventory />);

    const table = await loadedTable();
    expect(Object.fromEntries(lastGet(mock.calls, "/crypto/keys"))).toEqual({ limit: "25", offset: "0" });
    expect(within(table).getAllByRole("row")).toHaveLength(KEYS.length + 1);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("cada fila dice clase, propósito, algoritmo, proveedor, versión, fechas de Bogotá, antigüedad y registros", async () => {
    renderKeys(<KeysInventory />);
    const table = await loadedTable();

    const doc = rowOf(table, /member\.document.*v2/);
    for (const text of ["Cifrado", "A256GCM", "OpenBao", "v2", "2 mar 2026, 10:00 a. m.", "18 oct 2026, 1:00 p. m.", "255 días", "342", "Activa"]) {
      expect(within(doc).getByText(text, { exact: false })).toBeInTheDocument();
    }
    const phone = rowOf(table, /member\.phone/);
    expect(within(phone).getByText("—")).toBeInTheDocument();
    expect(within(rowOf(table, /member\.birth_date/)).getByText("Local")).toBeInTheDocument();
  });

  it("registros: el número cuando el api lo da y «n/a» para índice y firma", async () => {
    renderKeys(<KeysInventory />);
    const table = await loadedTable();

    expect(within(rowOf(table, /member\.email/)).getByText("n/a")).toBeInTheDocument();
    expect(within(rowOf(table, /member\.email/)).getByText("Índice ciego")).toBeInTheDocument();
    expect(within(rowOf(table, /audit\.signature/)).getByText("n/a")).toBeInTheDocument();
    expect(within(rowOf(table, /audit\.signature/)).getByText("Firma")).toBeInTheDocument();
    expect(within(rowOf(table, /attachment\.sensitive/)).getByText("0")).toBeInTheDocument();
  });

  it("el estado es texto: Activa, Solo descifrar y Retirada", async () => {
    renderKeys(<KeysInventory />);
    const table = await loadedTable();

    expect(within(rowOf(table, /member\.document.*v1/)).getByText("Solo descifrar")).toBeInTheDocument();
    expect(within(rowOf(table, /attachment\.sensitive/)).getByText("Retirada")).toBeInTheDocument();
    expect(within(rowOf(table, /member\.phone/)).getByText("Activa")).toBeInTheDocument();
  });

  it("nunca pinta material ni referencias de llave", async () => {
    const { container } = renderKeys(<KeysInventory />);
    await loadedTable();

    expect(container.textContent).not.toMatch(/vault:|wrapped|local:|\/keys\/|BEGIN /i);
  });

  it("«Rotar» solo aparece en filas activas de cifrado: nunca en índice, firma, solo descifrar ni retirada", async () => {
    renderKeys(<KeysInventory />);
    await loadedTable();

    const names = screen.getAllByRole("button", { name: /^Rotar / }).map((b) => b.getAttribute("aria-label") ?? b.textContent);
    expect(names.sort()).toEqual(["Rotar member.birth_date", "Rotar member.document", "Rotar member.phone"]);
  });

  it("«Rotar» abre el modal de esa llave", async () => {
    const { user } = renderKeys(<KeysInventory />);
    await loadedTable();

    await user.click(screen.getByRole("button", { name: "Rotar member.phone" }));

    expect(screen.getByRole("dialog", { name: "¿Rotar la llave de member.phone?" })).toBeInTheDocument();
  });

  it("cerrar el modal con Volver lo quita", async () => {
    const { user } = renderKeys(<KeysInventory />);
    await loadedTable();
    await user.click(screen.getByRole("button", { name: "Rotar member.phone" }));

    await user.click(screen.getByRole("button", { name: "Volver" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("KeysInventory · filtros en la URL", () => {
  it("Propósito, Estado y Proveedor quedan en la URL y viajan al api", async () => {
    const { mock, router, user } = renderKeys(<KeysInventory />);
    await loadedTable();

    await user.selectOptions(screen.getByRole("combobox", { name: "Propósito" }), "Cifrado");
    await waitFor(() => {
      expect(lastGet(mock.calls, "/crypto/keys").get("purpose")).toBe("encrypt");
    });
    await user.selectOptions(screen.getByRole("combobox", { name: "Estado" }), "Solo descifrar");
    await waitFor(() => {
      expect(lastGet(mock.calls, "/crypto/keys").get("state")).toBe("decrypt_only");
    });
    await user.selectOptions(screen.getByRole("combobox", { name: "Proveedor" }), "OpenBao");
    await waitFor(() => {
      expect(lastGet(mock.calls, "/crypto/keys").get("provider")).toBe("openbao");
    });
    const search = new URLSearchParams(router.state.location.search);
    expect(search.get("purpose")).toBe("encrypt");
    expect(search.get("state")).toBe("decrypt_only");
    expect(search.get("provider")).toBe("openbao");
  });

  it("los filtros de la URL se leen al entrar y marcan los selects", async () => {
    const { mock } = renderKeys(<KeysInventory />, "/sistema/llaves?purpose=sign&state=active&provider=local");
    await loadedTable();

    expect(Object.fromEntries(lastGet(mock.calls, "/crypto/keys"))).toEqual({ limit: "25", offset: "0", purpose: "sign", state: "active", provider: "local" });
    expect(screen.getByRole("combobox", { name: "Propósito" })).toHaveValue("sign");
    expect(screen.getByRole("combobox", { name: "Estado" })).toHaveValue("active");
    expect(screen.getByRole("combobox", { name: "Proveedor" })).toHaveValue("local");
  });

  it("un valor ajeno de la URL no viaja al api", async () => {
    const { mock } = renderKeys(<KeysInventory />, "/sistema/llaves?purpose=todas&state=x&provider=aws");
    await loadedTable();

    expect(Object.fromEntries(lastGet(mock.calls, "/crypto/keys"))).toEqual({ limit: "25", offset: "0" });
  });

  it("la búsqueda por clase de dato viaja como q y no queda en la URL", async () => {
    const { mock, router, user } = renderKeys(<KeysInventory />);
    await loadedTable();

    await user.type(screen.getByRole("searchbox", { name: "Clase de dato" }), "member.phone");

    await waitFor(() => {
      expect(lastGet(mock.calls, "/crypto/keys").get("q")).toBe("member.phone");
    });
    expect(router.state.location.search).not.toContain("member.phone");
  });
});

describe("KeysInventory · paginación por offset", () => {
  const manyHandler = {
    "GET /crypto/keys": (call: Parameters<typeof keysReply>[0]) => keysReply(call, KEYS, keysSummary(), 60),
  };

  it("Siguiente pide offset 25 y lo deja en la URL", async () => {
    const { mock, router, user } = renderKeys(<KeysInventory />, "/sistema/llaves", { handlers: manyHandler });
    await loadedTable();

    await user.click(screen.getByRole("button", { name: /Siguiente/ }));

    await waitFor(() => {
      expect(lastGet(mock.calls, "/crypto/keys").get("offset")).toBe("25");
    });
    expect(new URLSearchParams(router.state.location.search).get("offset")).toBe("25");
  });

  it("cambiar el tamaño de página pide limit 50 y vuelve a offset 0", async () => {
    const { mock, user } = renderKeys(<KeysInventory />, "/sistema/llaves?offset=25", { handlers: manyHandler });
    await loadedTable();

    await user.selectOptions(screen.getByRole("combobox", { name: "Mostrar" }), "50");

    await waitFor(() => {
      expect(Object.fromEntries(lastGet(mock.calls, "/crypto/keys"))).toMatchObject({ limit: "50", offset: "0" });
    });
  });
});

describe("KeysInventory · estados", () => {
  it("carga: anuncia «Cargando…» mientras llega la primera página", () => {
    renderKeys(<KeysInventory />);

    expect(screen.getByText("Cargando…")).toBeInTheDocument();
  });

  it("vacío con filtros: guía a limpiar los filtros", async () => {
    const { user, router } = renderKeys(<KeysInventory />, "/sistema/llaves?purpose=sign", {
      handlers: { "GET /crypto/keys": (call) => keysReply(call, [], keysSummary(), 0) },
    });

    expect(await screen.findByText("No hay llaves con estos filtros")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));

    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
  });

  it("error 500: mensaje accionable y Reintentar vuelve a pedir", async () => {
    const { mock, user } = renderKeys(<KeysInventory />, "/sistema/llaves", { handlers: { "GET /crypto/keys": apiError(500, "internal_error", "x") } });

    expect(await screen.findByText("No pudimos cargar las llaves. Intenta de nuevo en un momento.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(mock.callsTo("GET /crypto/keys").length).toBeGreaterThanOrEqual(2);
  });

  it("403: dice que solo el administrador ve las llaves", async () => {
    renderKeys(<KeysInventory />, "/sistema/llaves", { handlers: { "GET /crypto/keys": apiError(403, "forbidden", "x") } });

    expect(await screen.findByText("No tienes permiso para ver las llaves. Solo un administrador puede consultarlas.")).toBeInTheDocument();
  });

  it("429: dice cuánto esperar", async () => {
    renderKeys(<KeysInventory />, "/sistema/llaves", { handlers: { "GET /crypto/keys": apiError(429, "rate_limited", "x", {}, { "Retry-After": "12" }) } });

    expect(await screen.findByText(/Demasiadas consultas seguidas; espera 12 segundos/)).toBeInTheDocument();
  });

  it("una respuesta con material de llave (campo extra) se rechaza como inválida", async () => {
    const leaking = { ...cryptoKey(), wrapped_material: "vault:v1:AAAA" };
    renderKeys(<KeysInventory />, "/sistema/llaves", { handlers: { "GET /crypto/keys": (call) => keysReply(call, [leaking]) } });

    expect(await screen.findByText(/La respuesta del servidor no es válida/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("vault:");
  });
});

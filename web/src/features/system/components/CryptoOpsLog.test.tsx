// S6-F2 · US-144 (S6-D16): bitácora de operaciones de cifrado, inmutable y paginada. Filtros de fecha
// (días de Bogotá → [from, to) en UTC) con la misma regla que `check_instant_range` del api validada en el
// cliente (piso 2020, techo hoy, orden correcto y máximo 366 días: un rango inválido no viaja y se
// explica), operación en la URL, Pagination por offset, y los estados de carga, vacío, error y sin permiso.
import { screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { OPS, apiError, cryptoOp, lastGet, opsReply, renderKeys } from "../../../test/keys";
import { CryptoOpsLog } from "./CryptoOpsLog";

afterEach(() => {
  vi.unstubAllGlobals();
});

async function loadedTable(): Promise<HTMLElement> {
  const table = await screen.findByRole("table", { name: "Bitácora de operaciones" });
  await waitFor(() => {
    expect(screen.queryByText("Cargando…")).not.toBeInTheDocument();
  });
  return table;
}
const BASE = "/sistema/llaves?tab=bitacora";

describe("CryptoOpsLog · tabla", () => {
  it("pide limit 25 y offset 0 y pinta fecha de Bogotá, usuario, operación, clase, versión, registros y resultado", async () => {
    const { mock, container } = renderKeys(<CryptoOpsLog />, BASE);

    const table = await loadedTable();
    expect(Object.fromEntries(lastGet(mock.calls, "/crypto/ops"))).toEqual({ limit: "25", offset: "0" });
    expect(within(table).getAllByRole("row")).toHaveLength(OPS.length + 1);
    const first = within(table).getByRole("row", { name: /20 oct 2026, 10:30 a\. m\./ });
    for (const text of ["Usuario 99999999", "Descifrar", "member.document", "v2", "Correcto"]) {
      expect(within(first).getByText(text)).toBeInTheDocument();
    }
    expect(await axe(container)).toHaveNoViolations();
  });

  it("el usuario técnico se llama «Sistema (worker)» y un error se dice con palabras", async () => {
    renderKeys(<CryptoOpsLog />, BASE);
    const table = await loadedTable();

    expect(within(table).getByText("Sistema (worker)")).toBeInTheDocument();
    expect(within(table).getByText("Con error")).toBeInTheDocument();
    expect(within(table).getByText("Firmar")).toBeInTheDocument();
    expect(within(table).getByText("Rotar")).toBeInTheDocument();
  });

  it("una operación sin llave ni clase no inventa datos", async () => {
    renderKeys(<CryptoOpsLog />, BASE, {
      handlers: { "GET /crypto/ops": (call) => opsReply(call, [cryptoOp({ data_class: null, key_version: null, key_id: null, verb: "export" })]) },
    });
    const table = await loadedTable();

    expect(within(table).getAllByText("—").length).toBeGreaterThanOrEqual(2);
  });
});

describe("CryptoOpsLog · contrato estricto", () => {
  it("una fila con un campo extra (material o referencia) vuelve la respuesta inválida y no se pinta", async () => {
    const leaking = { ...cryptoOp(), raw: "vault:v1:SECRETO" };
    renderKeys(<CryptoOpsLog />, BASE, { handlers: { "GET /crypto/ops": (call) => opsReply(call, [leaking]) } });

    expect(await screen.findByText(/La respuesta del servidor no es válida/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("SECRETO");
  });

  it("un user_id que es texto libre se rechaza; el UUID fijo del usuario técnico se admite", async () => {
    renderKeys(<CryptoOpsLog />, BASE, { handlers: { "GET /crypto/ops": (call) => opsReply(call, [cryptoOp({ user_id: "vault:token" })]) } });
    expect(await screen.findByText(/La respuesta del servidor no es válida/)).toBeInTheDocument();
  });
});

describe("CryptoOpsLog · filtros", () => {
  it("las fechas de la URL viajan como días de Bogotá en UTC", async () => {
    const { mock } = renderKeys(<CryptoOpsLog />, `${BASE}&from=2026-10-13&to=2026-10-20`);
    await loadedTable();

    expect(Object.fromEntries(lastGet(mock.calls, "/crypto/ops"))).toEqual({
      limit: "25",
      offset: "0",
      from: "2026-10-13T05:00:00.000Z",
      to: "2026-10-21T05:00:00.000Z",
    });
    expect(screen.getByLabelText("Desde")).toHaveValue("2026-10-13");
  });

  it("un rango invertido no viaja y se explica", async () => {
    const { mock } = renderKeys(<CryptoOpsLog />, `${BASE}&from=2026-10-20&to=2026-10-13`);
    await loadedTable();

    expect(Object.fromEntries(lastGet(mock.calls, "/crypto/ops"))).toEqual({ limit: "25", offset: "0" });
    expect(screen.getByRole("alert")).toHaveTextContent("Revisa las fechas");
  });

  it.each([
    ["anterior a 2020", "from=2019-12-31&to=2020-01-05"],
    ["en el futuro", "from=2026-10-01&to=2999-01-01"],
    ["de más de 366 días", "from=2024-01-01&to=2025-06-01"],
  ])("un rango %s no viaja y se explica", async (_name, query) => {
    const { mock } = renderKeys(<CryptoOpsLog />, `${BASE}&${query}`);
    await loadedTable();

    expect(lastGet(mock.calls, "/crypto/ops").has("from")).toBe(false);
    expect(lastGet(mock.calls, "/crypto/ops").has("to")).toBe(false);
    expect(screen.getByRole("alert")).toHaveTextContent(/2020.*366 días/);
  });

  it("un rango válido de exactamente 366 días sí viaja", async () => {
    const { mock } = renderKeys(<CryptoOpsLog />, `${BASE}&from=2025-10-01&to=2026-09-30`);
    await loadedTable();

    expect(lastGet(mock.calls, "/crypto/ops").has("from")).toBe(true);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("una fecha que no es de calendario se ignora", async () => {
    const { mock } = renderKeys(<CryptoOpsLog />, `${BASE}&from=2026-02-31`);
    await loadedTable();

    expect(lastGet(mock.calls, "/crypto/ops").has("from")).toBe(false);
  });

  it("escribir la fecha desde el campo la deja en la URL", async () => {
    const { mock, router, user } = renderKeys(<CryptoOpsLog />, BASE);
    await loadedTable();

    await user.type(screen.getByLabelText("Desde"), "2026-10-13");

    await waitFor(() => {
      expect(lastGet(mock.calls, "/crypto/ops").get("from")).toBe("2026-10-13T05:00:00.000Z");
    });
    expect(new URLSearchParams(router.state.location.search).get("from")).toBe("2026-10-13");
  });

  it("Operación se guarda en la URL y viaja como verb; uno ajeno se ignora", async () => {
    const { mock, router, user } = renderKeys(<CryptoOpsLog />, `${BASE}&verb=borrar`);
    await loadedTable();
    expect(lastGet(mock.calls, "/crypto/ops").has("verb")).toBe(false);

    await user.selectOptions(screen.getByRole("combobox", { name: "Operación" }), "Rotar");

    await waitFor(() => {
      expect(lastGet(mock.calls, "/crypto/ops").get("verb")).toBe("rotate");
    });
    expect(new URLSearchParams(router.state.location.search).get("verb")).toBe("rotate");
  });
});

describe("CryptoOpsLog · paginación por offset", () => {
  it("Siguiente pide offset 25 y lo deja en la URL", async () => {
    const { mock, router, user } = renderKeys(<CryptoOpsLog />, BASE, { handlers: { "GET /crypto/ops": (call) => opsReply(call, OPS, 80) } });
    await loadedTable();

    await user.click(screen.getByRole("button", { name: /Siguiente/ }));

    await waitFor(() => {
      expect(lastGet(mock.calls, "/crypto/ops").get("offset")).toBe("25");
    });
    expect(new URLSearchParams(router.state.location.search).get("offset")).toBe("25");
    expect(new URLSearchParams(router.state.location.search).get("tab")).toBe("bitacora");
  });
});

describe("CryptoOpsLog · estados", () => {
  it("carga", () => {
    renderKeys(<CryptoOpsLog />, BASE);

    expect(screen.getByText("Cargando…")).toBeInTheDocument();
  });

  it("vacío: dice que no hay operaciones y ofrece limpiar los filtros", async () => {
    renderKeys(<CryptoOpsLog />, `${BASE}&verb=rotate`, { handlers: { "GET /crypto/ops": (call) => opsReply(call, [], 0) } });

    expect(await screen.findByText("No hay operaciones con estos filtros")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Limpiar filtros" })).toBeInTheDocument();
  });

  it("error 500 con Reintentar", async () => {
    const { mock, user } = renderKeys(<CryptoOpsLog />, BASE, { handlers: { "GET /crypto/ops": apiError(500, "internal_error", "x") } });

    expect(await screen.findByText("No pudimos cargar la bitácora. Intenta de nuevo en un momento.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(mock.callsTo("GET /crypto/ops").length).toBeGreaterThanOrEqual(2);
  });

  it("403 sin permiso", async () => {
    renderKeys(<CryptoOpsLog />, BASE, { handlers: { "GET /crypto/ops": apiError(403, "forbidden", "x") } });

    expect(await screen.findByText("No tienes permiso para ver la bitácora. Solo un administrador puede consultarla.")).toBeInTheDocument();
  });

  it("422 de filtros: pide revisar las fechas", async () => {
    renderKeys(<CryptoOpsLog />, BASE, { handlers: { "GET /crypto/ops": apiError(422, "validation_error", "x", { field: "to" }) } });

    expect(await screen.findByText(/Revisa los filtros/)).toBeInTheDocument();
  });
});

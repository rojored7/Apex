// S5-F2 · US-130 (front): /avisos/historial (Notif_Historial.html), admin y coach.
// - Título "Historial de envíos", enlace a las reglas, FilterBar (Socio en memoria; Desde y Hasta,
//   Regla, Canal y Resultado en la URL), tabla paginada en el servidor (25, 50 y 100) y "Ver mensaje".
// - Solo viaja al api lo que el contrato acepta: estado y canal de la lista, regla UUID y fechas reales.
// - Estados: carga, vacío (con y sin filtros), error con Reintentar, 403.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { apiError, callsOf, HISTORY_ROWS, pageOf, RULE_IDS, renderHistory } from "../../../test/notificationAdmin";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";

const table = () => screen.getByRole("table", { name: "Historial de envíos" });
const lastCall = (mock: Parameters<typeof callsOf>[0]) => callsOf(mock, "GET /notifications").at(-1);

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("coach");
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("HistoryPage · estructura (Notif_Historial.html)", () => {
  it("muestra el título, el enlace a las reglas, los filtros y la tabla", async () => {
    renderHistory();

    expect(screen.getByRole("heading", { level: 1, name: "Historial de envíos" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Reglas y plantillas" })).toHaveAttribute("href", "/avisos/reglas");
    expect(screen.getByRole("searchbox", { name: "Socio" })).toHaveAttribute("placeholder", "Nombre");
    expect(screen.getByLabelText("Desde")).toHaveValue("");
    expect(screen.getByLabelText("Hasta")).toHaveValue("");
    expect(within(screen.getByRole("combobox", { name: "Canal" })).getAllByRole("option").map((o) => o.textContent)).toEqual(["Todos", "Correo", "WhatsApp manual"]);
    expect(within(screen.getByRole("combobox", { name: "Resultado" })).getAllByRole("option").map((o) => o.textContent)).toEqual(["Todos", "Enviado", "Fallido", "Pendiente", "Omitido"]);
    await screen.findByRole("link", { name: "Juan Pérez" });
    expect(within(table()).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Fecha y hora",
      "Socio",
      "Regla",
      "Canal",
      "Resultado",
      "Detalle",
      "Quién",
      "Acción",
    ]);
  });

  it("la lista de reglas llena el filtro Regla", async () => {
    renderHistory();

    await waitFor(() => {
      expect(within(screen.getByRole("combobox", { name: "Regla" })).getAllByRole("option").map((o) => o.textContent)).toEqual(["Todas", "Por vencer", "Vence hoy", "Vencido"]);
    });
  });

  it("cada fila trae fecha de Bogotá, socio con enlace, regla, canal, resultado, detalle y quién", async () => {
    renderHistory();

    const link = await screen.findByRole("link", { name: "Juan Pérez" });
    expect(link).toHaveAttribute("href", `/socios/${HISTORY_ROWS[0]?.member_id ?? ""}`);
    const rows = within(table()).getAllByRole("row");
    const cells = (row: HTMLElement | undefined) => within(row as HTMLElement).getAllByRole("cell").map((c) => c.textContent);
    expect(cells(rows[1])).toEqual(["20 oct 2026, 8:12 a. m.", "Juan Pérez", "Vence hoy", "WhatsApp manual", "Enviado", "enlace abierto", "Equipo", "Ver mensaje"]);
    expect(cells(rows[2])).toEqual(["20 oct 2026, 7:00 a. m.", "Laura Gómez", "Por vencer", "Correo", "Enviado", "correo enviado", "sistema", "Ver mensaje"]);
    expect(cells(rows[3])).toEqual(["20 oct 2026, 7:00 a. m.", "Andrés Ruiz", "Por vencer", "Correo", "Fallido", "tiempo agotado", "sistema", "Ver mensaje"]);
    expect(cells(rows[4])).toEqual(["20 oct 2026, 7:00 a. m.", "Camila Torres", "Vencido", "WhatsApp manual", "Omitido", "motivo: pidió no contactar", "sistema", "Ver mensaje"]);
  });

  it("la primera petición pide la primera página de 25 sin filtros", async () => {
    const { mock } = renderHistory();
    await screen.findByRole("link", { name: "Juan Pérez" });

    expect(callsOf(mock, "GET /notifications")[0]?.toString()).toBe("limit=25&offset=0");
  });

  it("Ver mensaje abre el asunto y el mensaje del aviso", async () => {
    const { user } = renderHistory();
    await screen.findByRole("link", { name: "Juan Pérez" });

    await user.click(screen.getByRole("button", { name: "Ver mensaje de Juan Pérez" }));

    const panel = screen.getByRole("dialog", { name: "Mensaje para Juan Pérez" });
    expect(within(panel).getByText("Tu plan Trimestral vence hoy")).toBeInTheDocument();
    expect(within(panel).getByText(/Hola Juan, tu plan Trimestral en APEX vence hoy/)).toBeInTheDocument();
  });

  it("el admin también la ve", async () => {
    signOutForTests();
    signInAs("admin");
    renderHistory();

    expect(await screen.findByRole("link", { name: "Juan Pérez" })).toBeInTheDocument();
  });
});

describe("HistoryPage · filtros en la URL", () => {
  it("Resultado y Canal viajan al api y quedan en la URL", async () => {
    const { user, mock, router } = renderHistory();
    await screen.findByRole("link", { name: "Juan Pérez" });

    await user.selectOptions(screen.getByRole("combobox", { name: "Resultado" }), "failed");
    await user.selectOptions(screen.getByRole("combobox", { name: "Canal" }), "email");

    await waitFor(() => {
      expect(lastCall(mock)?.toString()).toBe("limit=25&offset=0&status=failed&channel=email");
    });
    expect(router.state.location.search).toContain("status=failed");
    expect(router.state.location.search).toContain("channel=email");
  });

  it("Regla y el rango de fechas viajan como rule_id, from y to", async () => {
    const { user, mock } = renderHistory();
    await screen.findByRole("link", { name: "Juan Pérez" });
    await waitFor(() => {
      expect(within(screen.getByRole("combobox", { name: "Regla" })).getAllByRole("option")).toHaveLength(4);
    });

    await user.selectOptions(screen.getByRole("combobox", { name: "Regla" }), RULE_IDS.vencido);
    await user.type(screen.getByLabelText("Desde"), "2026-10-01");
    await user.type(screen.getByLabelText("Hasta"), "2026-10-20");

    await waitFor(() => {
      expect(Object.fromEntries(lastCall(mock) ?? [])).toEqual({ limit: "25", offset: "0", rule_id: RULE_IDS.vencido, from: "2026-10-01", to: "2026-10-20" });
    });
  });

  it("lo que llega en la URL se aplica: ?status=sent&channel=whatsapp_link&from=2026-10-01", async () => {
    const { mock } = renderHistory("/avisos/historial?status=sent&channel=whatsapp_link&from=2026-10-01&limit=50");
    await screen.findByRole("link", { name: "Juan Pérez" });

    expect(Object.fromEntries(callsOf(mock, "GET /notifications")[0] ?? [])).toEqual({ limit: "50", offset: "0", status: "sent", channel: "whatsapp_link", from: "2026-10-01" });
    expect(screen.getByRole("combobox", { name: "Resultado" })).toHaveValue("sent");
    expect(screen.getByLabelText("Desde")).toHaveValue("2026-10-01");
  });

  it("un valor inválido en la URL no viaja al api (estado, canal, regla, fechas, q)", async () => {
    const { mock } = renderHistory("/avisos/historial?status=hack&channel=sms&rule_id=no-uuid&from=2026-13-40&to=ayer&q=Juan");
    await screen.findByRole("link", { name: "Juan Pérez" });

    expect(callsOf(mock, "GET /notifications")[0]?.toString()).toBe("limit=25&offset=0");
  });

  it("un rango invertido no viaja", async () => {
    const { mock } = renderHistory("/avisos/historial?from=2026-10-20&to=2026-10-01");
    await screen.findByRole("link", { name: "Juan Pérez" });

    expect(callsOf(mock, "GET /notifications")[0]?.toString()).toBe("limit=25&offset=0");
  });

  it("la búsqueda por socio va al api como q pero nunca a la URL", async () => {
    const { user, mock, router } = renderHistory();
    await screen.findByRole("link", { name: "Juan Pérez" });

    await user.type(screen.getByRole("searchbox", { name: "Socio" }), "Juan");

    await waitFor(() => {
      expect(lastCall(mock)?.get("q")).toBe("Juan");
    });
    expect(router.state.location.search).not.toContain("q=");
  });

  it("Limpiar quita los filtros", async () => {
    const { user, mock, router } = renderHistory("/avisos/historial?status=failed");
    await screen.findByRole("link", { name: "Andrés Ruiz" });

    await user.click(screen.getByRole("button", { name: "Limpiar" }));

    await waitFor(() => {
      expect(lastCall(mock)?.toString()).toBe("limit=25&offset=0");
    });
    expect(router.state.location.search).toBe("");
  });
});

describe("HistoryPage · paginación", () => {
  const sixty = { "GET /notifications": (call: Parameters<typeof pageOf>[0]) => pageOf(call, HISTORY_ROWS, 60) };

  it("Siguiente pide offset=25 y el tamaño 50 vuelve a la primera página", async () => {
    const { user, mock } = renderHistory("/avisos/historial", { handlers: sixty });
    await screen.findByRole("link", { name: "Juan Pérez" });
    expect(screen.getByText("Mostrando 1–25 de 60")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Siguiente/ }));
    await waitFor(() => {
      expect(lastCall(mock)?.toString()).toBe("limit=25&offset=25");
    });

    await user.selectOptions(screen.getByRole("combobox", { name: "Mostrar" }), "50");
    await waitFor(() => {
      expect(lastCall(mock)?.toString()).toBe("limit=50&offset=0");
    });
  });
});

describe("HistoryPage · estados", () => {
  it("sin envíos ni filtros guía hacia las reglas", async () => {
    renderHistory("/avisos/historial", { handlers: { "GET /notifications": (call) => pageOf(call, []) } });

    expect(await screen.findByText("Todavía no hay envíos. Cuando el sistema genere avisos aparecerán aquí.")).toBeInTheDocument();
  });

  it("sin coincidencias con filtros ofrece Limpiar filtros", async () => {
    const { user } = renderHistory("/avisos/historial?status=failed", { handlers: { "GET /notifications": (call) => pageOf(call, new URL(call.url, "http://apex.test").searchParams.has("status") ? [] : HISTORY_ROWS) } });

    expect(await screen.findByText("No hay envíos con estos filtros. Prueba con otro rango o limpia los filtros.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));
    expect(await screen.findByRole("link", { name: "Juan Pérez" })).toBeInTheDocument();
  });

  it("un 500 dice qué pasó y Reintentar vuelve a pedir", async () => {
    let calls = 0;
    const { user } = renderHistory("/avisos/historial", { handlers: { "GET /notifications": (call) => (++calls <= 1 ? apiError(500, "internal_error") : pageOf(call, HISTORY_ROWS)) } });

    expect(await screen.findByText("No pudimos cargar el historial. Intenta de nuevo en un momento.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("link", { name: "Juan Pérez" })).toBeInTheDocument();
  });

  it("un 403 explica el permiso y un 429 pide esperar", async () => {
    renderHistory("/avisos/historial", { handlers: { "GET /notifications": apiError(403, "forbidden") } });
    expect(await screen.findByText("No tienes permiso para ver el historial de envíos. Si lo necesitas, pídeselo a un administrador.")).toBeInTheDocument();
    cleanup();

    renderHistory("/avisos/historial", { handlers: { "GET /notifications": apiError(429, "rate_limited", {}, { "Retry-After": "20" }) } });
    expect(await screen.findByText(/Espera 20 segundos/)).toBeInTheDocument();
  });

  it("una página más allá del final ofrece volver a la primera", async () => {
    const { user } = renderHistory("/avisos/historial?offset=50", {
      handlers: { "GET /notifications": (call) => (new URL(call.url, "http://apex.test").searchParams.get("offset") === "0" ? pageOf(call, HISTORY_ROWS) : pageOf(call, [], 4)) },
    });

    expect(await screen.findByText("Esta página ya no tiene envíos.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ir a la primera página" }));
    expect(await screen.findByRole("link", { name: "Juan Pérez" })).toBeInTheDocument();
  });

  it("si la lista de reglas falla el filtro Regla queda con 'Todas' y la tabla sigue", async () => {
    renderHistory("/avisos/historial", { handlers: { "GET /notification-rules": apiError(500, "internal_error") } });

    expect(await screen.findByRole("link", { name: "Juan Pérez" })).toBeInTheDocument();
    expect(within(table()).getAllByRole("cell").some((c) => c.textContent === "—")).toBe(true);
  });
});

describe("HistoryPage · accesibilidad", () => {
  it.each([["claro", null], ["oscuro", "dark"]])("no tiene violaciones en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    const { user, container } = renderHistory();
    await screen.findByRole("link", { name: "Juan Pérez" });
    expect(await axe(container)).toHaveNoViolations();

    await user.click(screen.getByRole("button", { name: "Ver mensaje de Juan Pérez" }));
    expect(await axe(document.body)).toHaveNoViolations();
  });
});

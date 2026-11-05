// S5-F3 · US-123 y US-130 (front): pestaña Avisos de la ficha (/socios/:id/avisos), admin y coach
// (`notifications.view`). Ruta hija de /socios/:id (S3-D65): la ficha la pinta en su <Outlet /> y le pasa el
// socio por el contexto; se registra en la tabla de rutas con carga diferida y la feature `notifications`.
// - Canales de aviso (ChannelPreferences) y el historial del socio (GET /members/{id}/notifications),
//   paginado en el servidor (25, 50 o 100; `offset` en la URL), con "Ver mensaje".
// - Estados: carga, vacío, error con Reintentar (404, 403, 429 y el resto en palabras de la pantalla).
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { ROUTE_TABLE } from "../../../config/routeTable";
import { CHANNELS_PATH, channelsOut, MEMBER_NOTIFICATIONS_PATH, MEMBER_ID, MEMBER_ROWS, apiError, pageOf, RULE_ROWS } from "../../../test/memberNotifications";
import { DELETED_TAB_MEMBER, listCallsTo, renderMemberTab } from "../../../test/memberTabs";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { axe } from "vitest-axe";
import NotificationsTab from "./NotificationsTab";

const handlers = (extra: Parameters<typeof renderMemberTab>[3] = {}) => ({
  ...extra,
  handlers: {
    [`GET ${CHANNELS_PATH}`]: { status: 200, body: channelsOut() },
    [`GET ${MEMBER_NOTIFICATIONS_PATH}`]: (call: Parameters<typeof pageOf>[0]) => pageOf(call, MEMBER_ROWS),
    "GET /notification-rules": (call: Parameters<typeof pageOf>[0]) => pageOf(call, RULE_ROWS),
    ...(extra.handlers ?? {}),
  },
});

const renderTab = (options: Parameters<typeof renderMemberTab>[3] = {}, entry?: string) => renderMemberTab(NotificationsTab, "avisos", entry, handlers(options));
const table = () => screen.getByRole("table", { name: "Historial de avisos del socio" });

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("NotificationsTab · registro (S3-D65)", () => {
  it("es una hija de /socios/:id de la feature notifications, con carga diferida y acceso notifications.view", () => {
    const route = ROUTE_TABLE.find((r) => r.path === "/socios/:id/avisos");

    expect(route).toMatchObject({ parent: "/socios/:id", feature: "notifications", access: "notifications.view", layout: "panel" });
    expect(typeof route?.load).toBe("function");
  });
});

describe("NotificationsTab · contenido", () => {
  it("muestra los canales y el historial del socio con sus columnas", async () => {
    renderTab();

    expect(await screen.findByRole("heading", { level: 2, name: "Canales de aviso" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Historial de avisos" })).toBeInTheDocument();
    await screen.findByText("tiempo agotado");
    expect(within(table()).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Fecha y hora", "Regla", "Canal", "Resultado", "Detalle", "Quién", "Acción"]);
    const rows = within(table()).getAllByRole("row");
    const cells = (row: HTMLElement | undefined) => within(row as HTMLElement).getAllByRole("cell").map((c) => c.textContent);
    expect(cells(rows[1])).toEqual(["20 oct 2026, 8:12 a. m.", "Vence hoy", "WhatsApp manual", "Enviado", "enlace abierto", "Equipo", "Ver mensaje"]);
    expect(cells(rows[3])).toEqual(["20 oct 2026, 7:00 a. m.", "Por vencer", "Correo", "Fallido", "tiempo agotado", "sistema", "Ver mensaje"]);
  });

  it("pide la primera página de 25 al api del socio y las preferencias una sola vez", async () => {
    const { mock } = renderTab();
    await screen.findByText("tiempo agotado");

    expect(listCallsTo(mock, MEMBER_NOTIFICATIONS_PATH)[0]?.toString()).toBe("limit=25&offset=0");
    expect(mock.callsTo(`GET ${CHANNELS_PATH}`)).toHaveLength(1);
  });

  it("usa el socio de la ficha: no pide GET /members/{id}", async () => {
    const { mock } = renderTab();
    await screen.findByText("tiempo agotado");

    expect(mock.callsTo(`GET /members/${MEMBER_ID}`)).toHaveLength(0);
  });

  it("pagina en el servidor: Siguiente pide offset=25 y el tamaño 50 vuelve a la primera página", async () => {
    const { mock, user } = renderTab({ handlers: { [`GET ${MEMBER_NOTIFICATIONS_PATH}`]: (call) => pageOf(call, MEMBER_ROWS, 60) } });
    await screen.findByText("tiempo agotado");

    await user.click(screen.getByRole("button", { name: /Siguiente/ }));
    await waitFor(() => {
      expect(listCallsTo(mock, MEMBER_NOTIFICATIONS_PATH).at(-1)?.toString()).toBe("limit=25&offset=25");
    });
    await user.selectOptions(screen.getByRole("combobox", { name: "Mostrar" }), "50");
    await waitFor(() => {
      expect(listCallsTo(mock, MEMBER_NOTIFICATIONS_PATH).at(-1)?.toString()).toBe("limit=50&offset=0");
    });
  });

  it("Ver mensaje abre el asunto y el mensaje del aviso", async () => {
    const { user } = renderTab();
    await screen.findByText("tiempo agotado");

    await user.click(screen.getAllByRole("button", { name: /^Ver mensaje de/ })[0] as HTMLElement);

    const panel = screen.getByRole("dialog", { name: "Mensaje para Laura Gómez" });
    expect(within(panel).getByText("Tu plan Trimestral vence hoy")).toBeInTheDocument();
  });

  it("el coach también la ve y puede cambiar las preferencias", async () => {
    signOutForTests();
    signInAs("coach");
    renderTab();

    expect(await screen.findByRole("checkbox", { name: "Correo" })).toBeEnabled();
    await screen.findByText("tiempo agotado");
  });

  it("un socio dado de baja ve las preferencias de solo lectura", async () => {
    renderTab({ member: DELETED_TAB_MEMBER });

    expect(await screen.findByText("Este socio está dado de baja: sus preferencias son de solo lectura.")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Correo" })).toBeDisabled();
  });
});

describe("NotificationsTab · estados", () => {
  it("mientras carga el historial dice 'Cargando…'", () => {
    renderTab({ handlers: { [`GET ${MEMBER_NOTIFICATIONS_PATH}`]: () => new Promise(() => undefined) } });

    expect(screen.getAllByText("Cargando…").length).toBeGreaterThan(0);
  });

  it("sin avisos dice 'Este socio todavía no tiene avisos.'", async () => {
    renderTab({ handlers: { [`GET ${MEMBER_NOTIFICATIONS_PATH}`]: (call) => pageOf(call, []) } });

    expect(await screen.findByText("Este socio todavía no tiene avisos.")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Paginación" })).not.toBeInTheDocument();
  });

  it("un 500 dice qué pasó y Reintentar vuelve a pedir", async () => {
    let calls = 0;
    const { user } = renderTab({ handlers: { [`GET ${MEMBER_NOTIFICATIONS_PATH}`]: (call) => (++calls <= 1 ? apiError(500, "internal_error") : pageOf(call, MEMBER_ROWS)) } });

    expect(await screen.findByText("No pudimos cargar los avisos del socio. Intenta de nuevo en un momento.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("tiempo agotado")).toBeInTheDocument();
  });

  it("un 404 y un 403 se explican", async () => {
    renderTab({ handlers: { [`GET ${MEMBER_NOTIFICATIONS_PATH}`]: apiError(404, "member_not_found") } });
    expect(await screen.findByText("No encontramos a este socio. Puede que lo hayan eliminado; vuelve a la lista de socios.")).toBeInTheDocument();
    cleanup();

    renderTab({ handlers: { [`GET ${MEMBER_NOTIFICATIONS_PATH}`]: apiError(403, "forbidden") } });
    expect(await screen.findByText("No tienes permiso para ver los avisos de este socio. Si lo necesitas, pídeselo a un administrador.")).toBeInTheDocument();
  });

  it.each([["claro", null], ["oscuro", "dark"]])("no tiene violaciones de accesibilidad en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    const { container } = renderTab();
    await screen.findByText("tiempo agotado");

    expect(await axe(container)).toHaveNoViolations();
  });
});

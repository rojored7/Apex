// S5-F1 · US-127 y US-128 (front): /avisos/hoy (PorAvisarHoy.html).
// - Título "Por avisar hoy · martes 20 de octubre" (fecha de Bogotá), nota con el total, "Historial",
//   "Regenerar lista" (DESIGN-GAP: sin endpoint, deshabilitado), chips de canal y "Cómo funciona".
// - Filas: socio (enlace a la ficha), mensaje, etiqueta de canal y estado, "Abrir WhatsApp" (solo
//   canal whatsapp_link) y "Omitir".
// - Estados: carga, vacío con guía, error con Reintentar, 403, respuesta inválida, fuera de rango.
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { apiError, NOTIFICATIONS, renderToday, todayCalls, todayPage, TODAY_ROWS, WA_URL } from "../../../test/notifications";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";

const { juan, camila, andres, laura } = NOTIFICATIONS;
const rowOf = (name: string): HTMLElement => {
  const item = screen.getByRole("link", { name }).closest("li");
  if (!item) throw new Error(`sin fila para ${name}`);
  return item;
};

let openSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-20T15:00:00Z"));
  setViewportWidth(1440);
  signInAs("coach");
  openSpy = vi.fn(() => null);
  vi.stubGlobal("open", openSpy);
  document.documentElement.removeAttribute("data-theme");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("TodayPage · estructura (PorAvisarHoy.html)", () => {
  it("muestra el título con la fecha, la nota, Historial, Regenerar lista deshabilitado y Cómo funciona", async () => {
    renderToday();

    expect(screen.getByRole("heading", { level: 1, name: "Por avisar hoy · martes 20 de octubre" })).toBeInTheDocument();
    expect(await screen.findByText("4 por atender: 2 esperan WhatsApp, 2 son de correo.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Historial" })).toHaveAttribute("href", "/avisos/historial");
    const regenerate = screen.getByRole("button", { name: "Regenerar lista" });
    expect(regenerate).toBeDisabled();
    expect(screen.getByText("La lista la genera el sistema cada mañana.")).toBeInTheDocument();
    expect(screen.getByText(/«Abrir WhatsApp» lanza wa\.me con el mensaje ya escrito/)).toBeInTheDocument();
    expect(screen.getByText(/El teléfono nunca se muestra completo: el enlace lo arma el servidor\./)).toBeInTheDocument();
  });

  it.each([["claro", null], ["oscuro", "dark"]])("da la ayuda fija de ventanas emergentes en tema %s (S5-D244)", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    renderToday();

    expect(await screen.findByText("Si no se abre WhatsApp, permite las ventanas emergentes de este sitio.")).toBeInTheDocument();
  });

  it("ofrece los chips de canal con sus conteos y Todos activo", async () => {
    renderToday();

    const group = await screen.findByRole("group", { name: "Canal" });
    expect(within(group).getByRole("button", { name: "Pendientes de WhatsApp2" })).toHaveAttribute("aria-pressed", "false");
    expect(within(group).getByRole("button", { name: "Correo por enviar2" })).toHaveAttribute("aria-pressed", "false");
    expect(within(group).getByRole("button", { name: "Todos4" })).toHaveAttribute("aria-pressed", "true");
  });

  it("cada fila trae el socio como enlace a su ficha, el mensaje, la fecha y la etiqueta", async () => {
    renderToday();

    const link = await screen.findByRole("link", { name: "Juan Pérez" });
    expect(link).toHaveAttribute("href", `/socios/${juan.member_id}`);
    const row = rowOf("Juan Pérez");
    expect(within(row).getByText("Tu plan Trimestral vence hoy")).toBeInTheDocument();
    expect(within(row).getByText("Para hoy")).toBeInTheDocument();
    expect(within(row).getByText(juan.rendered_body)).toBeInTheDocument();
    expect(within(row).getByText("WhatsApp pendiente")).toBeInTheDocument();
    expect(within(rowOf("Camila Torres")).getByText("Del 15 oct 2026")).toBeInTheDocument();
  });

  it("un correo fallido dice el motivo en palabras y un correo pendiente dice que sale solo", async () => {
    renderToday();
    await screen.findByRole("link", { name: "Andrés Ruiz" });

    expect(within(rowOf("Andrés Ruiz")).getByText("Correo: falló · tiempo agotado")).toBeInTheDocument();
    expect(within(rowOf("Laura Gómez")).getByText("Correo por enviar")).toBeInTheDocument();
  });

  it("solo los avisos de WhatsApp traen 'Abrir WhatsApp'; todos traen 'Omitir'", async () => {
    renderToday();
    await screen.findByRole("link", { name: "Juan Pérez" });

    expect(within(rowOf("Juan Pérez")).getByRole("button", { name: "Abrir WhatsApp de Juan Pérez" })).toBeInTheDocument();
    expect(within(rowOf("Camila Torres")).getByRole("button", { name: "Abrir WhatsApp de Camila Torres" })).toBeInTheDocument();
    expect(within(rowOf("Andrés Ruiz")).queryByRole("button", { name: /Abrir WhatsApp/ })).not.toBeInTheDocument();
    expect(within(rowOf("Laura Gómez")).queryByRole("button", { name: /Abrir WhatsApp/ })).not.toBeInTheDocument();
    for (const name of ["Juan Pérez", "Camila Torres", "Andrés Ruiz", "Laura Gómez"]) {
      expect(within(rowOf(name)).getByRole("button", { name: `Omitir aviso de ${name}` })).toHaveTextContent("Omitir");
    }
  });

  it("la primera petición pide la primera página de 25", async () => {
    const { mock } = renderToday();
    await screen.findByRole("link", { name: "Juan Pérez" });

    expect(todayCalls(mock)[0]?.toString()).toBe("limit=25&offset=0");
  });

  it("el admin también la ve", async () => {
    signOutForTests();
    signInAs("admin");
    renderToday();

    expect(await screen.findByRole("link", { name: "Juan Pérez" })).toBeInTheDocument();
  });
});

describe("TodayPage · chips de canal", () => {
  it("'Pendientes de WhatsApp' deja solo esas filas y lo guarda en la URL (canal=whatsapp)", async () => {
    const { user, router } = renderToday();
    await screen.findByRole("link", { name: "Juan Pérez" });

    await user.click(screen.getByRole("button", { name: "Pendientes de WhatsApp2" }));

    expect(screen.getByRole("button", { name: "Pendientes de WhatsApp2" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("link", { name: "Juan Pérez" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Camila Torres" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Andrés Ruiz" })).not.toBeInTheDocument();
    expect(router.state.location.search).toBe("?canal=whatsapp");
  });

  it("'Correo por enviar' deja los de correo", async () => {
    const { user } = renderToday("/avisos/hoy");
    await screen.findByRole("link", { name: "Juan Pérez" });

    await user.click(screen.getByRole("button", { name: "Correo por enviar2" }));

    expect(screen.queryByRole("link", { name: "Juan Pérez" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Andrés Ruiz" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Laura Gómez" })).toBeInTheDocument();
  });

  it("un canal desconocido en la URL se ignora (Todos)", async () => {
    renderToday("/avisos/hoy?canal=sms");

    expect(await screen.findByRole("link", { name: "Andrés Ruiz" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Todos4" })).toHaveAttribute("aria-pressed", "true");
  });

  it("si el filtro no deja filas en la página, lo dice y ofrece ver Todos", async () => {
    const { user } = renderToday("/avisos/hoy?canal=whatsapp", { rows: [andres, laura] });

    expect(await screen.findByText("No hay avisos de WhatsApp en esta página.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ver todos" }));
    expect(await screen.findByRole("link", { name: "Andrés Ruiz" })).toBeInTheDocument();
  });

  it("con más de una página solo Todos lleva conteo (el api no filtra por canal)", async () => {
    renderToday("/avisos/hoy", { rows: TODAY_ROWS, total: 60 });

    expect(await screen.findByRole("button", { name: "Todos60" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pendientes de WhatsApp" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Correo por enviar" })).toBeInTheDocument();
    expect(screen.getByText("60 por atender.")).toBeInTheDocument();
  });

  it("pagina: 'Siguiente' pide offset=25", async () => {
    const { user, mock } = renderToday("/avisos/hoy", { rows: TODAY_ROWS, total: 60 });
    await screen.findByRole("link", { name: "Juan Pérez" });

    await user.click(screen.getByRole("button", { name: /Siguiente/ }));

    await waitFor(() => {
      expect(todayCalls(mock).at(-1)?.toString()).toBe("limit=25&offset=25");
    });
  });
});

describe("TodayPage · estados", () => {
  it("mientras carga dice 'Cargando avisos'", () => {
    renderToday("/avisos/hoy", { handlers: { "GET /notifications/today": () => new Promise(() => undefined) } });

    expect(screen.getByRole("status")).toHaveTextContent("Cargando avisos");
  });

  it("sin avisos dice 'Nadie por avisar hoy' y guía al historial", async () => {
    renderToday("/avisos/hoy", { rows: [], total: 0 });

    expect(await screen.findByText("Nadie por avisar hoy")).toBeInTheDocument();
    expect(screen.getByText(/El sistema genera los avisos cada mañana/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver el historial de envíos" })).toHaveAttribute("href", "/avisos/historial");
    expect(screen.queryByRole("navigation", { name: "Paginación" })).not.toBeInTheDocument();
  });

  it("un 500 dice qué pasó y qué hacer, y Reintentar vuelve a pedir", async () => {
    let calls = 0;
    const { user } = renderToday("/avisos/hoy", {
      handlers: { "GET /notifications/today": (call) => (++calls === 1 ? apiError(500, "internal_error") : todayPage(call)) },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar los avisos de hoy. Intenta de nuevo en un momento.");
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByRole("link", { name: "Juan Pérez" })).toBeInTheDocument();
  });

  it("un 403 explica que no tiene permiso", async () => {
    renderToday("/avisos/hoy", { handlers: { "GET /notifications/today": apiError(403, "forbidden") } });

    expect(await screen.findByRole("alert")).toHaveTextContent("No tienes permiso para ver los avisos de hoy. Si lo necesitas, pídeselo a un administrador.");
  });

  it("un 429 pide esperar", async () => {
    renderToday("/avisos/hoy", { handlers: { "GET /notifications/today": apiError(429, "rate_limited", {}, { "Retry-After": "20" }) } });

    expect(await screen.findByRole("alert")).toHaveTextContent("Espera 20 segundos");
  });

  it("una respuesta con forma inesperada no se pinta", async () => {
    renderToday("/avisos/hoy", { handlers: { "GET /notifications/today": { status: 200, body: { items: [{ id: 1 }], total: 1, limit: 25, offset: 0 } } } });

    expect(await screen.findByRole("alert")).toHaveTextContent("La respuesta del servidor no es válida");
  });

  it("una página más allá del final ofrece volver a la primera", async () => {
    const { user } = renderToday("/avisos/hoy?offset=50", {
      handlers: { "GET /notifications/today": (call) => (new URL(call.url, "http://apex.test").searchParams.get("offset") === "0" ? todayPage(call) : todayPage(call, [], 4)) },
    });

    expect(await screen.findByText("Esta página ya no tiene avisos.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ir a la primera página" }));
    expect(await screen.findByRole("link", { name: "Juan Pérez" })).toBeInTheDocument();
  });
});

describe("TodayPage · abrir WhatsApp (US-127)", () => {
  it("abre WhatsApp tras el 200, avisa que quedó enviado y relee la lista sin ese aviso", async () => {
    let sent = false;
    const { user, mock } = renderToday("/avisos/hoy", {
      handlers: {
        "GET /notifications/today": (call) => todayPage(call, sent ? TODAY_ROWS.filter((r) => r.id !== juan.id) : TODAY_ROWS),
        [`POST /notifications/${juan.id}/wa-link`]: () => {
          sent = true;
          return { status: 200, body: { url: WA_URL } };
        },
      },
    });
    await screen.findByRole("link", { name: "Juan Pérez" });

    await user.click(screen.getByRole("button", { name: "Abrir WhatsApp de Juan Pérez" }));

    await waitFor(() => {
      expect(openSpy).toHaveBeenCalledWith(WA_URL, "_blank", "noopener,noreferrer");
    });
    expect(await screen.findByText("WhatsApp abierto para Juan Pérez. El aviso quedó marcado como enviado.")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("link", { name: "Juan Pérez" })).not.toBeInTheDocument();
    });
    expect(mock.callsTo("GET /notifications/today").length).toBeGreaterThanOrEqual(2);
    expect(document.body.innerHTML).not.toContain("wa.me/57");
  });

  it("un 422 invalid_phone se ve en la fila y no abre nada", async () => {
    const { user } = renderToday("/avisos/hoy", {
      handlers: { [`POST /notifications/${juan.id}/wa-link`]: apiError(422, "invalid_phone", {}, undefined, "El teléfono de este socio no es un celular válido.") },
    });
    await screen.findByRole("link", { name: "Juan Pérez" });

    await user.click(screen.getByRole("button", { name: "Abrir WhatsApp de Juan Pérez" }));

    expect(await within(rowOf("Juan Pérez")).findByRole("alert")).toHaveTextContent("El teléfono de este socio no es un celular válido.");
    expect(openSpy).not.toHaveBeenCalled();
  });
});

describe("TodayPage · omitir (US-129)", () => {
  it("pide el motivo, envía el POST, avisa y cierra", async () => {
    const { user, mock } = renderToday("/avisos/hoy", {
      handlers: { [`POST /notifications/${camila.id}/skip`]: { status: 200, body: { ...camila, status: "skipped", skip_reason: "Ya pagó en el box" } } },
    });
    await screen.findByRole("link", { name: "Camila Torres" });

    await user.click(screen.getByRole("button", { name: "Omitir aviso de Camila Torres" }));
    const dialog = screen.getByRole("dialog", { name: "¿Omitir el aviso de Camila Torres?" });
    await user.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "Ya pagó en el box");
    await user.click(within(dialog).getByRole("button", { name: "Omitir aviso" }));

    expect(await screen.findByText("Aviso de Camila Torres omitido. Quedó en el historial con tu motivo.")).toBeInTheDocument();
    expect(mock.callsTo(`POST /notifications/${camila.id}/skip`)[0]?.body).toEqual({ reason: "Ya pagó en el box" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("el aviso se puede cerrar", async () => {
    const { user } = renderToday("/avisos/hoy", {
      handlers: { [`POST /notifications/${camila.id}/skip`]: { status: 200, body: { ...camila, status: "skipped", skip_reason: "No contactar" } } },
    });
    await screen.findByRole("link", { name: "Camila Torres" });
    await user.click(screen.getByRole("button", { name: "Omitir aviso de Camila Torres" }));
    await user.type(screen.getByRole("textbox", { name: /Motivo/ }), "No contactar");
    await user.click(screen.getByRole("button", { name: "Omitir aviso" }));
    await screen.findByText(/Aviso de Camila Torres omitido/);

    await user.click(screen.getByRole("button", { name: "Cerrar aviso" }));

    expect(screen.queryByText(/Aviso de Camila Torres omitido/)).not.toBeInTheDocument();
  });
});

describe("TodayPage · celular y temas", () => {
  it("en 360 px sigue siendo una lista de tarjetas con los mismos botones", async () => {
    setViewportWidth(360);
    renderToday();

    expect(await screen.findByRole("list", { name: "Avisos de hoy" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
    expect(screen.getByRole("button", { name: "Abrir WhatsApp de Juan Pérez" })).toBeInTheDocument();
  });

  it.each([["claro", null], ["oscuro", "dark"]])("no tiene violaciones de accesibilidad en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    const { container } = renderToday();
    await screen.findByRole("link", { name: "Juan Pérez" });

    await act(async () => {
      await Promise.resolve();
    });
    expect(await axe(container)).toHaveNoViolations();
  });
});

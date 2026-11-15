// S7-F3 · US-157 (front): /clases (Sesiones.html), admin y coach (`classes.view`).
// - La semana vive en la URL (`?semana=AAAA-Www`); sin ella o con una inválida es la semana de hoy; `?dia=hoy` también.
// - Rejilla de lunes a domingo: hoy resaltado («· hoy»), «Sin clases» en los días vacíos, cancelada con borde punteado y texto,
//   cupo lleno con texto, sesión extra marcada. Elegir una sesión muestra su detalle con «Abrir check-in» y «Cancelar sesión».
// - Estados: carga, semana vacía, error con Reintentar, 403. «+ Sesión extra» abre el panel; el coach no ve la pestaña Horario.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { axe } from "vitest-axe";
import { SessionRoleProvider } from "../../../core/auth";
import { apiError, NOW, SESSIONS, sessionsPage, usersPage, WEEK } from "../../../test/classes";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import SessionsPage from "./SessionsPage";

function Where() {
  const location = useLocation();
  return <output data-testid="where">{`${location.pathname}${location.search}`}</output>;
}

function renderPage(entry = `/clases?semana=${WEEK}`, handlers: Record<string, MockHandler> = {}) {
  const mock = mockApi({ "GET /class-sessions": sessionsPage(), "GET /users": usersPage, ...handlers });
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <MemoryRouter initialEntries={[entry]}>
          <SessionsPage />
          <Where />
        </MemoryRouter>
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, user: userEvent.setup(), ...view };
}

const day = (name: string | RegExp) => screen.getByRole("group", { name });
const weekCalls = (mock: { callsTo: (key: string) => { url: string }[] }) => mock.callsTo("GET /class-sessions").map((c) => new URL(c.url, "http://apex.test").searchParams.get("week"));
const where = () => screen.getByTestId("where").textContent;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
  signInAs("coach");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("SessionsPage · estructura (Sesiones.html)", () => {
  it("título, pestañas y la semana de la URL", async () => {
    const { mock } = renderPage();

    expect(await screen.findByRole("heading", { level: 1, name: "Clases" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Sesiones", selected: true })).toBeInTheDocument();
    expect(screen.getByText("Semana del 19 al 25 de octubre de 2026")).toBeInTheDocument();
    await screen.findByText("Carlos · 9/12");
    expect(weekCalls(mock)).toEqual([WEEK]);
    const url = new URL(mock.callsTo("GET /class-sessions")[0]?.url ?? "", "http://apex.test");
    expect(url.searchParams.get("limit")).toBe("200");
  });

  it("siete días de lunes a domingo con hoy resaltado y «Sin clases» donde no hay sesiones", async () => {
    renderPage();
    await screen.findByText("Carlos · 9/12");

    for (const name of ["Lun 19", "Mié 21", "Jue 22", "Vie 23", "Sáb 24", "Dom 25"]) expect(day(name)).toBeInTheDocument();
    const hoy = day(/^Mar 20/);
    expect(within(hoy).getByRole("heading", { name: "Mar 20 · hoy" })).toHaveAttribute("aria-current", "date");
    expect(within(day("Mié 21")).getByText("Sin clases")).toBeInTheDocument();
    expect(within(day("Dom 25")).getByText("Sin clases")).toBeInTheDocument();
    expect(within(day("Lun 19")).queryByText("Sin clases")).toBeNull();
  });

  it("cada sesión dice hora, coach y cupo; llena, cancelada y open box con texto", async () => {
    renderPage();
    await screen.findByText("Carlos · 9/12");

    const lunes = day("Lun 19");
    expect(within(lunes).getByRole("button", { name: /06:00.*Carlos · 12\/12.*Llena/ })).toBeInTheDocument();
    expect(within(lunes).getByRole("button", { name: /07:00.*Carlos · 9\/12/ })).toBeInTheDocument();
    expect(within(day(/^Mar 20/)).getByRole("button", { name: /17:00.*María · 3\/12/ })).toBeInTheDocument();
    const cancelada = within(day("Jue 22")).getByRole("button", { name: /17:00.*Cancelada · festivo/ });
    expect(cancelada).toHaveAttribute("data-status", "cancelled");
    expect(within(day("Sáb 24")).getByRole("button", { name: /09:30.*Open box · 0\/20/ })).toBeInTheDocument();
  });

  it("no tiene violaciones de axe", async () => {
    const { container } = renderPage();
    await screen.findByText("Carlos · 9/12");

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("SessionsPage · semana en la URL", () => {
  it("sin semana usa la de hoy; una inválida también", async () => {
    const { mock } = renderPage("/clases");
    await screen.findByText("Semana del 19 al 25 de octubre de 2026");
    expect(weekCalls(mock)).toEqual([WEEK]);
    cleanup();

    const second = renderPage("/clases?semana=basura");
    await screen.findByText("Semana del 19 al 25 de octubre de 2026");
    expect(weekCalls(second.mock)).toEqual([WEEK]);
  });

  it("`?dia=hoy` pide la semana de hoy aunque la URL traiga otra y muestra solo el día de hoy (Q25)", async () => {
    const { mock } = renderPage("/clases?dia=hoy&semana=2026-W30");

    expect(await screen.findByText("Hoy, martes 20 de octubre")).toBeInTheDocument();
    await screen.findByText("María · 3/12");
    expect(weekCalls(mock)).toEqual([WEEK]);
    expect(screen.getAllByRole("group")).toHaveLength(1);
    expect(day(/^Mar 20/)).toBeInTheDocument();
    expect(screen.queryByText("Carlos · 9/12")).toBeNull();
    expect(screen.queryByRole("button", { name: "Semana siguiente ›" })).toBeNull();
  });

  it("`?dia=hoy` ofrece «Ver toda la semana», que vuelve a la rejilla de la semana", async () => {
    const { user } = renderPage("/clases?dia=hoy");
    await screen.findByText("Hoy, martes 20 de octubre");

    await user.click(screen.getByRole("link", { name: "Ver toda la semana" }));

    expect(await screen.findByText("Semana del 19 al 25 de octubre de 2026")).toBeInTheDocument();
    expect(where()).toBe(`/clases?semana=${WEEK}`);
    expect(screen.getAllByRole("group")).toHaveLength(7);
  });

  it("«Semana siguiente» y «Semana anterior» cambian la semana de la URL y piden la nueva", async () => {
    const { mock, user } = renderPage();
    await screen.findByText("Carlos · 9/12");

    await user.click(screen.getByRole("button", { name: "Semana siguiente ›" }));
    expect(await screen.findByText("Semana del 26 de octubre al 1 de noviembre de 2026")).toBeInTheDocument();
    expect(where()).toBe("/clases?semana=2026-W44");
    await waitFor(() => {
      expect(weekCalls(mock)).toContain("2026-W44");
    });

    await user.click(screen.getByRole("button", { name: "‹ Semana anterior" }));
    await user.click(screen.getByRole("button", { name: "‹ Semana anterior" }));
    expect(await screen.findByText("Semana del 12 al 18 de octubre de 2026")).toBeInTheDocument();
    expect(where()).toBe("/clases?semana=2026-W42");
  });

  it("«Hoy» vuelve a la semana de hoy", async () => {
    const { user } = renderPage("/clases?semana=2026-W30");
    await screen.findByText("Semana del 20 al 26 de julio de 2026");

    await user.click(screen.getByRole("link", { name: "Hoy" }));

    expect(await screen.findByText("Semana del 19 al 25 de octubre de 2026")).toBeInTheDocument();
    expect(where()).toBe(`/clases?semana=${WEEK}`);
  });
});

describe("SessionsPage · detalle y acciones", () => {
  it("elegir una sesión muestra su detalle con check-in y cancelar", async () => {
    const { user } = renderPage();
    await screen.findByText("Carlos · 9/12");

    await user.click(within(day(/^Mar 20/)).getByRole("button", { name: /17:00/ }));

    const detail = screen.getByRole("region", { name: "Sesión · mar 20 oct · 17:00 · María" });
    expect(within(detail).getByText("Cupo 12 · 3 con check-in")).toBeInTheDocument();
    expect(within(detail).getByRole("link", { name: "Abrir check-in" })).toHaveAttribute("href", `/clases/${SESSIONS.hoy17.id}/checkin`);
    expect(within(detail).getByRole("button", { name: "Cancelar sesión" })).toBeInTheDocument();
  });

  it("una sesión cancelada muestra el motivo y no ofrece cancelar", async () => {
    const { user } = renderPage();
    await screen.findByText("Carlos · 9/12");

    await user.click(within(day("Jue 22")).getByRole("button", { name: /17:00/ }));

    const detail = screen.getByRole("region", { name: /Sesión · jue 22 oct · 17:00/ });
    expect(within(detail).getByText("Cancelada: festivo")).toBeInTheDocument();
    expect(within(detail).queryByRole("button", { name: "Cancelar sesión" })).toBeNull();
  });

  it("«Cancelar sesión» abre el modal y, al cancelar, avisa y relee la semana", async () => {
    const reply = { ...SESSIONS.hoy17, status: "cancelled", cancel_reason: "Se enfermó la coach", cancelled_at: "2026-10-20T15:00:00Z" };
    const { user, mock } = renderPage(`/clases?semana=${WEEK}`, { [`POST /class-sessions/${SESSIONS.hoy17.id}/cancel`]: { status: 200, body: reply } });
    await screen.findByText("Carlos · 9/12");
    await user.click(within(day(/^Mar 20/)).getByRole("button", { name: /17:00/ }));
    await user.click(screen.getByRole("button", { name: "Cancelar sesión" }));

    const dialog = screen.getByRole("dialog", { name: "¿Cancelar la sesión de las 17:00?" });
    await user.type(within(dialog).getByRole("textbox", { name: /^Motivo/ }), "Se enfermó la coach");
    await user.click(within(dialog).getByRole("button", { name: "Sí, cancelar sesión" }));

    expect(await screen.findByText("Sesión de las 17:00 cancelada.")).toBeInTheDocument();
    await waitFor(() => {
      expect(mock.callsTo("GET /class-sessions").length).toBeGreaterThan(1);
    });
  });

  it("el filtro de coach deja solo las sesiones de ese coach", async () => {
    const { user } = renderPage();
    await screen.findByText("Carlos · 9/12");

    await user.selectOptions(screen.getByRole("combobox", { name: "Coach" }), "María");

    expect(screen.queryByText("Carlos · 9/12")).toBeNull();
    expect(within(day(/^Mar 20/)).getByRole("button", { name: /17:00/ })).toBeInTheDocument();
  });

  it("«+ Sesión extra» abre el panel", async () => {
    const { user } = renderPage();
    await screen.findByText("Carlos · 9/12");

    await user.click(screen.getByRole("button", { name: "+ Sesión extra" }));

    expect(screen.getByRole("dialog", { name: "Sesión extra" })).toBeInTheDocument();
  });

  it("«Check-in de la próxima clase» lleva a la primera sesión de hoy que aún no termina", async () => {
    renderPage();
    await screen.findByText("Carlos · 9/12");

    expect(screen.getByRole("link", { name: "Check-in de la próxima clase" })).toHaveAttribute("href", `/clases/${SESSIONS.hoy17.id}/checkin`);
  });

  it("el coach no ve la pestaña Horario semanal y el admin sí", async () => {
    renderPage();
    await screen.findByText("Carlos · 9/12");
    expect(screen.queryByRole("tab", { name: "Horario semanal" })).toBeNull();
    cleanup();
    signInAs("admin");

    renderPage();
    await screen.findByText("Carlos · 9/12");
    expect(screen.getByRole("tab", { name: "Horario semanal" })).toBeInTheDocument();
  });
});

describe("SessionsPage · estados", () => {
  it("mientras carga dice «Cargando sesiones…»", () => {
    renderPage(`/clases?semana=${WEEK}`, { "GET /class-sessions": () => new Promise(() => undefined) });

    expect(screen.getByText("Cargando sesiones…")).toBeInTheDocument();
  });

  it("una semana sin sesiones guía a crear una extra o a revisar el horario", async () => {
    renderPage(`/clases?semana=${WEEK}`, { "GET /class-sessions": sessionsPage([]) });

    expect(await screen.findByText("Esta semana no tiene sesiones. Se generan solas desde el horario semanal; también puedes crear una sesión extra.")).toBeInTheDocument();
    expect(within(day("Lun 19")).getByText("Sin clases")).toBeInTheDocument();
  });

  it("error 500 con Reintentar", async () => {
    let calls = 0;
    const { user } = renderPage(`/clases?semana=${WEEK}`, {
      "GET /class-sessions": () => {
        calls += 1;
        return calls === 1 ? apiError(500, "internal_error") : sessionsPage();
      },
    });

    expect(await screen.findByText("No pudimos cargar las sesiones. Intenta de nuevo en un momento.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("Carlos · 9/12")).toBeInTheDocument();
  });

  it("403 se dice como permiso", async () => {
    renderPage(`/clases?semana=${WEEK}`, { "GET /class-sessions": apiError(403, "forbidden") });

    expect(await screen.findByText("No tienes permiso para ver las sesiones. Si lo necesitas, pídeselo a un administrador.")).toBeInTheDocument();
  });

  it("una semana con más sesiones de las que caben avisa cuántas se ven", async () => {
    renderPage(`/clases?semana=${WEEK}`, { "GET /class-sessions": { status: 200, body: { items: [SESSIONS.llena], total: 250, limit: 200, offset: 0 } } });

    expect(await screen.findByText("Se muestran 1 de 250 sesiones de esta semana. Las demás no caben en la pantalla.")).toBeInTheDocument();
  });
});

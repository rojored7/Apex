// S2-F5 · US-055 criterios 4 y 6: pantalla Configuración con pestañas en ?tab=, una lectura
// por pestaña, confirmación al salir con cambios sin guardar (useBlocker + ConfirmModal y
// beforeunload), guardar una sección no recarga las otras y nada se guarda en localStorage.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, Link, Outlet, RouterProvider } from "react-router";
import { axe } from "vitest-axe";
import { createQueryClient } from "../../../core/api/queryClient";
import { RoleProvider } from "../../../core/auth";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { gymSection, membershipsSection, privacySection } from "../../../test/settings";
import ConfigPage from "./ConfigPage";

const PATH = "/sistema/configuracion";

function defaultHandlers(): Record<string, MockHandler> {
  return {
    "GET /settings/gym": { status: 200, body: gymSection() },
    "GET /settings/privacy": { status: 200, body: privacySection({ policy_version: "2026-10", policy_text: "Autorizo." }, 1) },
    "GET /settings/memberships": { status: 200, body: membershipsSection() },
  };
}

function renderPage(entry = PATH, handlers: Record<string, MockHandler> = {}, client: QueryClient = testQueryClient()) {
  const mock = mockApi({ ...defaultHandlers(), ...handlers });
  const router = createMemoryRouter(
    [
      {
        // Como en PanelShell: un menú y el contenido dentro de <main>.
        element: (
          <>
            <nav aria-label="Menú principal">
              <Link to="/">Ir a Inicio</Link>
            </nav>
            <main>
              <Outlet />
            </main>
          </>
        ),
        children: [
          { path: PATH, element: <ConfigPage /> },
          { path: "/", element: <h1>Inicio</h1> },
        ],
      },
    ],
    { initialEntries: [entry] },
  );
  const user = userEvent.setup();
  const view = render(
    <QueryClientProvider client={client}>
      <RoleProvider value="admin">
        <RouterProvider router={router} />
      </RoleProvider>
    </QueryClientProvider>,
  );
  return { mock, router, user, ...view };
}

const tab = (name: string) => screen.getByRole("tab", { name });
const nameInput = () => screen.findByRole("textbox", { name: /Nombre/ });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ConfigPage", () => {
  it("muestra el título, la nota de auditoría y las tres pestañas en orden", async () => {
    renderPage();

    expect(screen.getByRole("heading", { level: 1, name: "Configuración del gimnasio" })).toBeInTheDocument();
    expect(screen.getByText("Cada sección se guarda por separado y queda en auditoría.")).toBeInTheDocument();
    const list = screen.getByRole("tablist", { name: "Secciones de la configuración" });
    expect(within(list).getAllByRole("tab").map((t) => t.textContent)).toEqual(["Gimnasio", "Privacidad", "Membresías"]);
    expect(tab("Gimnasio")).toHaveAttribute("aria-selected", "true");
    await nameInput();
  });

  it("solo lee la sección de la pestaña abierta", async () => {
    const { mock } = renderPage();
    await nameInput();

    expect(mock.callsTo("GET /settings/gym")).toHaveLength(1);
    expect(mock.callsTo("GET /settings/privacy")).toHaveLength(0);
    expect(mock.callsTo("GET /settings/memberships")).toHaveLength(0);
  });

  it.each([
    ["privacidad", "Privacidad", /Versión de la política/],
    ["membresias", "Membresías", /Por vencer/],
  ])("?tab=%s abre la pestaña %s", async (id, label, field) => {
    renderPage(`${PATH}?tab=${id}`);

    expect(tab(label)).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByLabelText(field)).toBeInTheDocument();
  });

  it("una pestaña desconocida abre Gimnasio", async () => {
    renderPage(`${PATH}?tab=canales`);

    expect(tab("Gimnasio")).toHaveAttribute("aria-selected", "true");
    await nameInput();
  });

  it("cambiar de pestaña sin cambios no pide confirmación y deja la pestaña en la URL", async () => {
    const { router, user } = renderPage();
    await nameInput();

    await user.click(tab("Membresías"));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(router.state.location.search).toBe("?tab=membresias");
    expect(await screen.findByRole("spinbutton", { name: /Por vencer/ })).toBeInTheDocument();
  });

  it("con cambios sin guardar, cambiar de pestaña pide confirmación; Volver conserva lo escrito", async () => {
    const { router, user } = renderPage();
    const name = await nameInput();
    await user.type(name, " Norte");

    await user.click(tab("Privacidad"));

    const dialog = await screen.findByRole("dialog", { name: "Tienes cambios sin guardar. ¿Descartarlos?" });
    expect(dialog).toHaveTextContent("Si sigues, se pierden los cambios de esta sección.");
    await user.click(within(dialog).getByRole("button", { name: "Volver" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(router.state.location.search).toBe("");
    expect(tab("Gimnasio")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("textbox", { name: /Nombre/ })).toHaveValue("APEX Norte");
  });

  it("con cambios sin guardar, Descartar cambios lleva a la otra pestaña", async () => {
    const { router, user } = renderPage();
    await user.type(await nameInput(), " Norte");

    await user.click(tab("Privacidad"));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Descartar cambios" }));

    await waitFor(() => {
      expect(router.state.location.search).toBe("?tab=privacidad");
    });
    expect(await screen.findByRole("textbox", { name: /Versión de la política/ })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("con cambios sin guardar, salir de la pantalla también pide confirmación", async () => {
    const { router, user } = renderPage();
    await user.type(await nameInput(), " Norte");

    await user.click(screen.getByRole("link", { name: "Ir a Inicio" }));
    const dialog = await screen.findByRole("dialog");
    expect(router.state.location.pathname).toBe(PATH);

    await user.click(within(dialog).getByRole("button", { name: "Descartar cambios" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Inicio" })).toBeInTheDocument();
  });

  it("después de guardar ya no pide confirmación", async () => {
    const { router, user } = renderPage(PATH, { "PATCH /settings/gym": { status: 200, body: gymSection({ name: "APEX Norte" }, 1) } });
    await user.type(await nameInput(), " Norte");
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await screen.findByText("Cambios guardados");

    await user.click(tab("Membresías"));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(router.state.location.search).toBe("?tab=membresias");
  });

  it("con cambios sin guardar, recargar o cerrar la pestaña del navegador pide confirmación", async () => {
    const { user } = renderPage();
    await nameInput();

    const clean = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);

    await user.type(screen.getByRole("textbox", { name: /Nombre/ }), " Norte");
    const dirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirty);

    expect(dirty.defaultPrevented).toBe(true);
  });

  it("guardar una sección no vuelve a leer las otras", async () => {
    const { mock, user } = renderPage(`${PATH}?tab=privacidad`, { "PATCH /settings/gym": { status: 200, body: gymSection({ name: "APEX Norte" }, 1) } }, createQueryClient());
    await screen.findByRole("textbox", { name: /Versión de la política/ });

    await user.click(tab("Gimnasio"));
    await user.type(await nameInput(), " Norte");
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await screen.findByText("Cambios guardados");
    await user.click(tab("Privacidad"));
    await screen.findByRole("textbox", { name: /Versión de la política/ });

    expect(mock.callsTo("GET /settings/privacy")).toHaveLength(1);
    expect(mock.callsTo("GET /settings/gym")).toHaveLength(1);
  });

  it("no guarda borradores en localStorage ni sessionStorage", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const { user } = renderPage(PATH, { "PATCH /settings/gym": { status: 200, body: gymSection({ name: "APEX Norte" }, 1) } });

    await user.type(await nameInput(), " Norte");
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await screen.findByText("Cambios guardados");

    expect(setItem).not.toHaveBeenCalled();
  });

  it("es accesible, también con el modal abierto", async () => {
    const { container, user } = renderPage();
    await user.type(await nameInput(), " Norte");
    expect(await axe(container)).toHaveNoViolations();

    await user.click(tab("Privacidad"));
    await screen.findByRole("dialog");

    expect(await axe(document.body)).toHaveNoViolations();
  });
});

// S5-F5 · US-131 (front, S5-D37): el alta de un usuario con `email_sent`.
// - email_sent: true  -> "Enlace enviado por correo a <correo>." y NO se muestra el enlace
//   (el token no sale del correo; el administrador no necesita copiarlo).
// - email_sent: false (o ausente, v0.1) -> el enlace copiable de siempre.
// - Carga ("Creando…") y error del api con su mensaje, sin enlace.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { NewUserPanel } from "./NewUserPanel";

const URL_ACTIVACION = "https://apex.test/restablecer/AbCdEfGhIjKlMnOpQrStUvWxYz0123456789";

function created(emailSent: boolean | undefined) {
  return {
    status: 201,
    body: {
      user: { id: "55555555-5555-4555-8555-555555555555", email: "carlos@apex.test", role: "coach", status: "pending_activation", member_id: null, must_change_password: false },
      activation_url: URL_ACTIVACION,
      expires_at: "2026-10-25T19:30:00Z",
      ...(emailSent === undefined ? {} : { email_sent: emailSent }),
    },
  };
}

function renderPanel(handler: MockHandler) {
  const mock = mockApi({ "POST /users": handler });
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <MemoryRouter>
        <NewUserPanel open onClose={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { mock, user: userEvent.setup(), ...view };
}

const dialog = () => screen.getByRole("dialog", { name: "Nuevo usuario del equipo" });

async function create(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.type(within(dialog()).getByRole("textbox", { name: /^Correo/ }), "carlos@apex.test");
  await user.click(within(dialog()).getByRole("button", { name: /Crear usuario|Creando/ }));
}

beforeEach(() => {
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  delete document.documentElement.dataset.theme;
});

describe("NewUserPanel · correo enviado (US-131)", () => {
  it("con email_sent true dice que se envió por correo y no muestra el enlace", async () => {
    const { user } = renderPanel(created(true));

    await create(user);

    expect(await within(dialog()).findByText("Enlace enviado por correo a carlos@apex.test.")).toBeInTheDocument();
    expect(within(dialog()).queryByRole("textbox", { name: "Enlace de activación" })).not.toBeInTheDocument();
    expect(within(dialog()).queryByRole("button", { name: "Copiar" })).not.toBeInTheDocument();
    expect(dialog()).not.toHaveTextContent(URL_ACTIVACION);
    expect(dialog()).toHaveTextContent("El enlace vence el 25 oct 2026");
  });

  it.each([
    ["false", false],
    ["ausente (v0.1)", undefined],
  ])("con email_sent %s muestra el enlace copiable como en v0.1", async (_label, flag) => {
    const { user } = renderPanel(created(flag));

    await create(user);

    const link = await within(dialog()).findByRole("textbox", { name: "Enlace de activación" });
    expect(link).toHaveValue(URL_ACTIVACION);
    expect(within(dialog()).getByRole("button", { name: "Copiar" })).toBeInTheDocument();
    expect(dialog()).toHaveTextContent("El correo no salió: entrega este enlace por un medio seguro.");
  });

  it("mientras crea el botón dice 'Creando…' y está deshabilitado", async () => {
    const { user } = renderPanel(() => new Promise(() => undefined));

    await create(user);

    expect(await within(dialog()).findByRole("button", { name: "Creando…" })).toBeDisabled();
  });

  it("un 5xx se explica sin enlace ni mensaje de envío", async () => {
    const { user } = renderPanel({ status: 500, body: { error: { code: "internal_error", message: "x" } } });

    await create(user);

    expect(await within(dialog()).findByRole("alert")).toHaveTextContent("No pudimos crear el usuario. Intenta de nuevo en un momento.");
    expect(dialog()).not.toHaveTextContent("Enlace enviado por correo");
  });

  it.each([
    ["claro", null],
    ["oscuro", "dark"],
  ])("el resultado enviado no tiene violaciones de accesibilidad en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    const { user, container } = renderPanel(created(true));
    await create(user);
    await within(dialog()).findByText("Enlace enviado por correo a carlos@apex.test.");

    expect(await axe(container)).toHaveNoViolations();
  });
});

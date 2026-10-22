// S2-F4a · US-048 (front): /restablecer/:token, la tarjeta "Nueva contraseña · Activar
// cuenta" de Login.html. El mismo enlace sirve para activar (lo da el admin) y para recuperar.
// - Al llegar saca el token de la barra con history.replaceState (no queda en el historial).
// - Zod: contraseña de 12 a 128 caracteres y confirmación igual.
// - 204: va a /login con el aviso de contraseña guardada (S2-D18: no inicia sesión).
// - 400 invalid_token: "El enlace ya no es válido. Pide uno nuevo al administrador."
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { axe } from "vitest-axe";
import { clearSession, resetSessionForTests } from "../../../core/auth/session";
import { AccessLayout } from "../../../layouts/AccessLayout";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import LoginPage from "./LoginPage";
import ResetPage from "./ResetPage";

const TOKEN = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789-_";
const PASSWORD = "Clave-nueva-segura-2026";
const INVALID = "El enlace ya no es válido. Pide uno nuevo al administrador.";

function renderReset(token = TOKEN, handlers: Record<string, MockHandler> = {}) {
  window.history.replaceState(null, "", `/restablecer/${token}`);
  const mock = mockApi({ "POST /auth/reset": { status: 204 }, ...handlers });
  const router = createMemoryRouter(
    [
      {
        element: <AccessLayout />,
        children: [
          { path: "/restablecer/:token", element: <ResetPage /> },
          { path: "/login", element: <LoginPage /> },
        ],
      },
    ],
    { initialEntries: [`/restablecer/${token}`] },
  );
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { mock, router, user: userEvent.setup(), ...view };
}

const newBox = () => screen.getByLabelText(/^Contraseña nueva/);
const confirmBox = () => screen.getByLabelText(/^Repite la contraseña nueva/);
const saveButton = () => screen.getByRole("button", { name: /Guardar contraseña|Guardando/ });

async function fill(user: ReturnType<typeof userEvent.setup>, password = PASSWORD, confirm = password): Promise<void> {
  await user.type(newBox(), password);
  await user.type(confirmBox(), confirm);
}

beforeEach(() => {
  resetSessionForTests();
  clearSession("restore_failed");
});

afterEach(() => {
  cleanup();
  resetSessionForTests();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("ResetPage · estructura (Login.html, tarjeta Nueva contraseña)", () => {
  it("muestra el título, la explicación, los dos campos con la política y el botón", async () => {
    const { container } = renderReset();

    expect(screen.getByRole("heading", { level: 1, name: "Nueva contraseña" })).toBeInTheDocument();
    expect(screen.getByText("Sirve para activar tu cuenta o para recuperar el acceso.")).toBeInTheDocument();
    expect(newBox()).toHaveAttribute("type", "password");
    expect(newBox()).toHaveAttribute("autocomplete", "new-password");
    expect(confirmBox()).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByText("Entre 12 y 128 caracteres. Evita las contraseñas comunes.")).toBeInTheDocument();
    expect(saveButton()).toHaveAttribute("type", "submit");
    expect(newBox()).toHaveFocus();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("saca el token de la barra de direcciones con history.replaceState", () => {
    const spy = vi.spyOn(window.history, "replaceState");
    renderReset();

    expect(spy).toHaveBeenCalled();
    expect(window.location.pathname).toBe("/restablecer");
    expect(window.location.href).not.toContain(TOKEN);
    spy.mockRestore();
  });
});

describe("ResetPage · validación (Zod)", () => {
  it("vacío marca los dos campos y no llama al api", async () => {
    const { mock, user } = renderReset();

    await user.click(saveButton());

    expect(await screen.findByText("Escribe la contraseña nueva.")).toBeInTheDocument();
    expect(screen.getByText("Repite la contraseña nueva.")).toBeInTheDocument();
    expect(mock.callsTo("POST /auth/reset")).toHaveLength(0);
  });

  it("menos de 12 caracteres se rechaza", async () => {
    const { mock, user } = renderReset();

    await fill(user, "once-letras", "once-letras");
    await user.click(saveButton());

    expect(await screen.findByText("La contraseña nueva debe tener al menos 12 caracteres.")).toBeInTheDocument();
    expect(mock.callsTo("POST /auth/reset")).toHaveLength(0);
  });

  it("12 caracteres exactos se aceptan y 129 no", async () => {
    const { mock, user } = renderReset();
    const long = "b".repeat(129);

    await fill(user, long, long);
    await user.click(saveButton());
    expect(await screen.findByText("La contraseña nueva admite hasta 128 caracteres.")).toBeInTheDocument();

    await user.clear(newBox());
    await user.clear(confirmBox());
    await fill(user, "doce-letras!", "doce-letras!");
    await user.click(saveButton());
    await screen.findByRole("heading", { name: "Iniciar sesión" });
    expect(mock.callsTo("POST /auth/reset")).toHaveLength(1);
  });

  it("la confirmación distinta se marca en su campo", async () => {
    const { mock, user } = renderReset();

    await fill(user, PASSWORD, `${PASSWORD}!`);
    await user.click(saveButton());

    expect(await screen.findByText("Las contraseñas no coinciden. Escribe la misma en los dos campos.")).toBeInTheDocument();
    expect(confirmBox()).toHaveAttribute("aria-invalid", "true");
    expect(mock.callsTo("POST /auth/reset")).toHaveLength(0);
  });
});

describe("ResetPage · envío", () => {
  it("204: envía token y contraseña sin sesión y va a /login con el aviso", async () => {
    const { mock, router, user } = renderReset();

    await fill(user);
    await user.click(saveButton());

    expect(await screen.findByRole("heading", { level: 1, name: "Iniciar sesión" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(screen.getByRole("status")).toHaveTextContent("Tu contraseña quedó guardada. Inicia sesión con ella.");
    const [call] = mock.callsTo("POST /auth/reset");
    expect(call?.body).toEqual({ token: TOKEN, new_password: PASSWORD });
    expect(call?.headers.get("Authorization")).toBeNull();
  });

  it("al volver a /login no queda la ruta con el token en el historial", async () => {
    const { router, user } = renderReset();

    await fill(user);
    await user.click(saveButton());
    await screen.findByRole("heading", { name: "Iniciar sesión" });

    expect(router.state.historyAction).toBe("REPLACE");
  });

  it("400 invalid_token: avisa que el enlace no sirve y ofrece volver al login", async () => {
    const { user } = renderReset(TOKEN, {
      "POST /auth/reset": { status: 400, body: { error: { code: "invalid_token", message: "El enlace ya no es válido." } } },
    });

    await fill(user);
    await user.click(saveButton());

    expect(await screen.findByRole("alert")).toHaveTextContent(INVALID);
    expect(screen.queryByLabelText(/^Contraseña nueva/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir a iniciar sesión" })).toHaveAttribute("href", "/login");
  });

  it("un token mal formado en el enlace muestra el mismo aviso sin llamar al api", () => {
    const { mock } = renderReset("corto");

    expect(screen.getByRole("alert")).toHaveTextContent(INVALID);
    expect(mock.calls).toHaveLength(0);
  });

  it("422 new_password se muestra bajo el campo con el motivo del api", async () => {
    const { user } = renderReset(TOKEN, {
      "POST /auth/reset": { status: 422, body: { error: { code: "weak_password", message: "La contraseña es demasiado débil.", field: "new_password" } } },
    });

    await fill(user);
    await user.click(saveButton());

    expect(await screen.findByText("La contraseña es demasiado débil. Elige otra.")).toBeInTheDocument();
    expect(newBox()).toHaveAttribute("aria-invalid", "true");
  });

  it("429 dice cuánto esperar", async () => {
    const { user } = renderReset(TOKEN, {
      "POST /auth/reset": { status: 429, body: { error: { code: "rate_limited", message: "x" } }, headers: { "Retry-After": "12" } },
    });

    await fill(user);
    await user.click(saveButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("Demasiados intentos. Espera 12 s y vuelve a intentarlo.");
    expect(newBox()).toBeInTheDocument();
  });

  it("mientras envía el botón dice 'Guardando…' y está deshabilitado", async () => {
    const { user } = renderReset(TOKEN, { "POST /auth/reset": () => new Promise(() => undefined) });

    await fill(user);
    await user.click(saveButton());

    const form = screen.getByRole("form", { name: "Nueva contraseña" });
    expect(await within(form).findByRole("button", { name: "Guardando…" })).toBeDisabled();
  });
});

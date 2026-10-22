// S2-F4a · US-048 (front, criterio 10): /recuperar, la tarjeta "Olvidé mi contraseña" de
// Login.html. Envía POST /auth/forgot y muestra siempre el mismo mensaje, exista o no el
// correo y pase lo que pase con la petición (H-2: en v0.1 forgot no envía correos; el enlace
// lo entrega el administrador).
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { axe } from "vitest-axe";
import { AccessLayout } from "../../../layouts/AccessLayout";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import ForgotPage from "./ForgotPage";

const DONE = "Pídele al administrador tu enlace de recuperación.";

function renderForgot(handlers: Record<string, MockHandler> = {}) {
  const mock = mockApi({ "POST /auth/forgot": { status: 204 }, ...handlers });
  const router = createMemoryRouter([{ element: <AccessLayout />, children: [{ path: "/recuperar", element: <ForgotPage /> }] }], {
    initialEntries: ["/recuperar"],
  });
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { mock, user: userEvent.setup(), ...view };
}

const emailBox = () => screen.getByRole("textbox", { name: /^Correo/ });
const sendButton = () => screen.getByRole("button", { name: /Enviar enlace|Enviando/ });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ForgotPage · estructura", () => {
  it("muestra el título, el correo, la explicación y la vuelta al login", async () => {
    const { container } = renderForgot();

    expect(screen.getByRole("heading", { level: 1, name: "Olvidé mi contraseña" })).toBeInTheDocument();
    expect(emailBox()).toHaveAttribute("type", "email");
    expect(emailBox()).toHaveAttribute("autocomplete", "username");
    expect(emailBox()).toHaveFocus();
    expect(screen.getByText("En esta versión el enlace no llega por correo: te lo entrega el administrador del gimnasio.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Volver a iniciar sesión" })).toHaveAttribute("href", "/login");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("un correo inválido se marca y no llama al api", async () => {
    const { mock, user } = renderForgot();

    await user.type(emailBox(), "no-es-correo");
    await user.click(sendButton());

    expect(await screen.findByText("Escribe un correo válido, por ejemplo ana@correo.com.")).toBeInTheDocument();
    expect(mock.callsTo("POST /auth/forgot")).toHaveLength(0);
  });
});

describe("ForgotPage · siempre el mismo mensaje", () => {
  const OUTCOMES: [string, MockHandler | "network"][] = [
    ["204 de un correo registrado", { status: 204 }],
    ["204 de un correo que no existe", { status: 204 }],
    ["429 por demasiados intentos", { status: 429, body: { error: { code: "rate_limited", message: "x" } }, headers: { "Retry-After": "30" } }],
    ["500 del servidor", { status: 500, body: { error: { code: "internal", message: "x" } } }],
    ["la red caída", "network"],
  ];

  it.each(OUTCOMES)("con %s envía el correo y muestra el mensaje fijo", async (_case, outcome) => {
    const { mock, user } = renderForgot(outcome === "network" ? {} : { "POST /auth/forgot": outcome });
    if (outcome === "network") {
      vi.stubGlobal(
        "fetch",
        vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
      );
    }

    await user.type(emailBox(), "  Ana@Apex.test ");
    await user.click(sendButton());

    expect(await screen.findByRole("status")).toHaveTextContent(DONE);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /^Correo/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Volver a iniciar sesión" })).toBeInTheDocument();
    if (outcome !== "network") expect(mock.callsTo("POST /auth/forgot")[0]?.body).toEqual({ email: "Ana@Apex.test" });
  });

  it("mientras envía el botón dice 'Enviando…' y está deshabilitado", async () => {
    const { user } = renderForgot({ "POST /auth/forgot": () => new Promise(() => undefined) });

    await user.type(emailBox(), "ana@apex.test");
    await user.click(sendButton());

    expect(await screen.findByRole("button", { name: "Enviando…" })).toBeDisabled();
  });
});

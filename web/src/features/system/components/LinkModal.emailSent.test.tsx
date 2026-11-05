// S5-F5 · US-131 (front, S5-D37): "Reenviar enlace" con `email_sent`.
// - true: "Enlace enviado por correo" con el propósito y el vencimiento, sin mostrar el token.
// - false o ausente: el enlace copiable de v0.1.
import { cleanup, screen, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { findRow, renderUsersPage, USERS } from "../../../test/users";

const RESET_URL = "https://apex.test/restablecer/ReSeTtOkEnAbCdEfGhIjKlMnOpQrStUv0123";
const modal = () => screen.getByRole("dialog", { name: /^Reenviar enlace/ });
const issued = (emailSent: boolean | undefined) => ({
  status: 200,
  body: { url: RESET_URL, purpose: "reset", expires_at: "2026-10-21T20:30:00Z", ...(emailSent === undefined ? {} : { email_sent: emailSent }) },
});

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  delete document.documentElement.dataset.theme;
});

async function generate(user: ReturnType<typeof renderUsersPage>["user"]): Promise<void> {
  const row = await findRow(USERS.coach.email);
  await user.click(within(row).getByRole("button", { name: /^Reenviar enlace/ }));
  await user.click(within(modal()).getByRole("button", { name: "Generar enlace" }));
}

describe("LinkModal · correo enviado (US-131)", () => {
  it("con email_sent true avisa que salió por correo y no muestra el enlace", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.coach.id}/resend-link`]: issued(true) } });

    await generate(user);

    expect(await within(modal()).findByText(`Enlace enviado por correo a ${USERS.coach.email}.`)).toBeInTheDocument();
    expect(modal()).toHaveTextContent("Recuperación, vence en 1 hora");
    expect(modal()).toHaveTextContent("Vence el 21 oct 2026, 3:30 p. m.");
    expect(within(modal()).queryByRole("textbox", { name: "Enlace" })).not.toBeInTheDocument();
    expect(modal()).not.toHaveTextContent(RESET_URL);
    expect(within(modal()).getByRole("button", { name: "Listo" })).toBeInTheDocument();
  });

  it.each([
    ["false", false],
    ["ausente (v0.1)", undefined],
  ])("con email_sent %s muestra el enlace copiable", async (_label, flag) => {
    const { user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.coach.id}/resend-link`]: issued(flag) } });

    await generate(user);

    expect(await within(modal()).findByRole("textbox", { name: "Enlace" })).toHaveValue(RESET_URL);
    expect(modal()).toHaveTextContent("El correo no salió: entrega este enlace por un medio seguro.");
  });

  it("mientras genera el botón dice 'Generando…'", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.coach.id}/resend-link`]: () => new Promise(() => undefined) } });

    await generate(user);

    expect(await within(modal()).findByRole("button", { name: "Generando…" })).toBeDisabled();
  });

  it.each([
    ["claro", null],
    ["oscuro", "dark"],
  ])("el resultado enviado no tiene violaciones de accesibilidad en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    const { user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.coach.id}/resend-link`]: issued(true) } });
    await generate(user);
    await within(modal()).findByText(`Enlace enviado por correo a ${USERS.coach.email}.`);

    expect(await axe(modal())).toHaveNoViolations();
  });
});

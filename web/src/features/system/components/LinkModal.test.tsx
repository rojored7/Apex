// S2-F4b · US-052 (front), L-7 y L-13: "Reenviar enlace" desde la fila de una cuenta.
// - Oculto para bloqueados, dados de baja, la propia fila y admins activos con contraseña
//   (en el front: role admin y status active; un admin pendiente de activación sí lo recibe).
// - El modal avisa que el enlace anterior deja de servir antes de generar uno nuevo; POST
//   /users/{id}/resend-link. El enlace va en un campo de solo lectura con "Copiar", el
//   propósito en texto ("Activación, vence en 72 horas" o "Recuperación, vence en 1 hora"), el
//   vencimiento en hora de Bogotá y "Entrégalo por un medio seguro. Al generar uno nuevo, el
//   anterior deja de servir."
// - L-7: la mutación usa gcTime 0 y, al cerrar, reset(): el enlace no queda ni en la
//   pantalla ni en la caché. El 409 user_not_eligible muestra su mensaje.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { apiError, findRow, renderUsersPage, USERS } from "../../../test/users";

const RESET_URL = "https://apex.test/restablecer/ReSeTtOkEnAbCdEfGhIjKlMnOpQrStUv0123";
const ACTIVATE_URL = "https://apex.test/restablecer/AcTiVaTeAbCdEfGhIjKlMnOpQrStUv4567";
const HANDOFF = "Entrégalo por un medio seguro. Al generar uno nuevo, el anterior deja de servir.";

const issued = (url: string, purpose: "activate" | "reset", expires_at: string) => ({ status: 200, body: { url, purpose, expires_at } });
const modal = () => screen.getByRole("dialog", { name: /^Reenviar enlace/ });

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function openFor(user: ReturnType<typeof renderUsersPage>["user"], email: string): Promise<void> {
  const row = await findRow(email);
  await user.click(within(row).getByRole("button", { name: /^Reenviar enlace/ }));
}

async function generate(user: ReturnType<typeof renderUsersPage>["user"], email: string): Promise<void> {
  await openFor(user, email);
  await user.click(within(modal()).getByRole("button", { name: "Generar enlace" }));
}

describe("UsersPage · dónde aparece 'Reenviar enlace' (L-13)", () => {
  it.each([
    ["un coach activo", USERS.coach.email],
    ["una cuenta pendiente de activación", USERS.pending.email],
    ["un admin pendiente de activación", USERS.pendingAdmin.email],
  ])("aparece en %s", async (_label, email) => {
    renderUsersPage();

    expect(within(await findRow(email)).getByRole("button", { name: /^Reenviar enlace/ })).toBeInTheDocument();
  });

  it.each([
    ["la propia fila", USERS.own.email],
    ["un admin activo con contraseña", USERS.admin.email],
    ["una cuenta bloqueada", USERS.locked.email],
    ["una cuenta dada de baja", USERS.deleted.email],
  ])("no aparece en %s", async (_label, email) => {
    renderUsersPage();

    expect(within(await findRow(email)).queryByRole("button", { name: /^Reenviar enlace/ })).not.toBeInTheDocument();
  });
});

describe("LinkModal · generar (US-052)", () => {
  it("antes de generar avisa que el anterior deja de servir y no llama al api", async () => {
    const { mock, user } = renderUsersPage();

    await openFor(user, USERS.coach.email);

    expect(modal()).toHaveTextContent(`Se genera un enlace nuevo para ${USERS.coach.email}.`);
    expect(modal()).toHaveTextContent(HANDOFF);
    expect(mock.calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });

  it("Volver cierra sin generar nada", async () => {
    const { mock, user } = renderUsersPage();
    await openFor(user, USERS.coach.email);

    await user.click(within(modal()).getByRole("button", { name: "Volver" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });

  it("un enlace de recuperación: solo lectura, Copiar, propósito y vencimiento en hora de Bogotá", async () => {
    const { mock, user } = renderUsersPage("/sistema/usuarios", {
      handlers: { [`POST /users/${USERS.coach.id}/resend-link`]: issued(RESET_URL, "reset", "2026-10-21T20:30:00Z") },
    });

    await generate(user, USERS.coach.email);

    const link = await within(modal()).findByRole("textbox", { name: "Enlace" });
    expect(link).toHaveValue(RESET_URL);
    expect(link).toHaveAttribute("readonly");
    expect(within(modal()).getByRole("button", { name: "Copiar" })).toBeInTheDocument();
    expect(modal()).toHaveTextContent("Recuperación, vence en 1 hora");
    expect(modal()).toHaveTextContent("Vence el 21 oct 2026, 3:30 p. m.");
    expect(modal()).toHaveTextContent(HANDOFF);
    expect(mock.callsTo(`POST /users/${USERS.coach.id}/resend-link`)).toHaveLength(1);
  });

  it("un enlace de activación dice que vence en 72 horas", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", {
      handlers: { [`POST /users/${USERS.pending.id}/resend-link`]: issued(ACTIVATE_URL, "activate", "2026-10-24T19:30:00Z") },
    });

    await generate(user, USERS.pending.email);

    expect(await within(modal()).findByText("Activación, vence en 72 horas")).toBeInTheDocument();
    expect(modal()).toHaveTextContent("Vence el 24 oct 2026, 2:30 p. m.");
  });

  it("Copiar lleva el enlace al portapapeles y lo confirma", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", {
      handlers: { [`POST /users/${USERS.coach.id}/resend-link`]: issued(RESET_URL, "reset", "2026-10-21T20:30:00Z") },
    });
    await generate(user, USERS.coach.email);
    await within(modal()).findByRole("textbox", { name: "Enlace" });
    const write = vi.spyOn(navigator.clipboard, "writeText");

    await user.click(within(modal()).getByRole("button", { name: "Copiar" }));

    expect(write).toHaveBeenCalledWith(RESET_URL);
    expect(await within(modal()).findByRole("status")).toHaveTextContent("Enlace copiado.");
  });

  it("mientras genera no se puede cerrar ni pedir otro", async () => {
    const { mock, user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.coach.id}/resend-link`]: () => new Promise(() => undefined) } });

    await generate(user, USERS.coach.email);
    await user.keyboard("{Escape}");

    expect(modal()).toBeInTheDocument();
    expect(within(modal()).getByRole("button", { name: "Generando…" })).toHaveAttribute("aria-busy", "true");
    expect(within(modal()).getByRole("button", { name: "Volver" })).toBeDisabled();
    expect(mock.callsTo(`POST /users/${USERS.coach.id}/resend-link`)).toHaveLength(1);
  });

  it("L-7: gcTime 0 y, al cerrar, el enlace sale de la pantalla y de la caché", async () => {
    const { queryClient, user } = renderUsersPage("/sistema/usuarios", {
      handlers: { [`POST /users/${USERS.coach.id}/resend-link`]: issued(RESET_URL, "reset", "2026-10-21T20:30:00Z") },
    });
    await generate(user, USERS.coach.email);
    await within(modal()).findByRole("textbox", { name: "Enlace" });
    const withLink = () => queryClient.getMutationCache().getAll().filter((m) => JSON.stringify(m.state.data ?? null).includes(RESET_URL));
    expect(withLink()).toHaveLength(1);
    expect(withLink()[0]?.options.gcTime).toBe(0);

    await user.click(within(modal()).getByRole("button", { name: "Listo" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(withLink()).toHaveLength(0);
    });
    expect(document.body.innerHTML).not.toContain(RESET_URL);
    await openFor(user, USERS.coach.email);
    expect(within(modal()).queryByRole("textbox", { name: "Enlace" })).not.toBeInTheDocument();
  });

  it("409 user_not_eligible muestra su mensaje y no muestra ningún enlace", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", {
      handlers: { [`POST /users/${USERS.coach.id}/resend-link`]: apiError(409, "user_not_eligible", "Esta cuenta no puede recibir un enlace nuevo.") },
    });

    await generate(user, USERS.coach.email);

    expect(await within(modal()).findByRole("alert")).toHaveTextContent(
      "Esta cuenta no puede recibir un enlace nuevo. Si está bloqueada, desbloquéala primero; el enlace de un administrador activo se genera desde la consola del servidor.",
    );
    expect(within(modal()).queryByRole("textbox", { name: "Enlace" })).not.toBeInTheDocument();
  });

  it("un enlace que no es http(s) es una respuesta inválida, no un enlace", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", {
      handlers: { [`POST /users/${USERS.coach.id}/resend-link`]: issued("javascript:alert(1)", "reset", "2026-10-21T20:30:00Z") },
    });

    await generate(user, USERS.coach.email);

    expect(await within(modal()).findByRole("alert")).toHaveTextContent("La respuesta del servidor no es válida. Recarga la página e intenta de nuevo.");
    expect(document.body.innerHTML).not.toContain("javascript:alert");
  });

  it("un 404 explica que la cuenta ya no está", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.coach.id}/resend-link`]: apiError(404, "user_not_found") } });

    await generate(user, USERS.coach.email);

    expect(await within(modal()).findByRole("alert")).toHaveTextContent("No encontramos esta cuenta: puede que otra persona ya la haya dado de baja. Cierra y recarga la lista.");
  });

  it("no tiene violaciones de accesibilidad con el enlace a la vista", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", {
      handlers: { [`POST /users/${USERS.coach.id}/resend-link`]: issued(RESET_URL, "reset", "2026-10-21T20:30:00Z") },
    });
    await generate(user, USERS.coach.email);
    await within(modal()).findByRole("textbox", { name: "Enlace" });

    expect(await axe(modal())).toHaveNoViolations();
  });
});

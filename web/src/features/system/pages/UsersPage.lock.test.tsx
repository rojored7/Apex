// S2-F4b · US-051 (front): "Bloquear" y "Desbloquear" en la fila de una cuenta.
// - Bloquear: ConfirmModal "Cierra todas sus sesiones y le impide entrar hasta que lo
//   desbloquees" y POST /users/{id}/lock. No aparece en la propia fila ni en una cuenta ya
//   bloqueada o dada de baja.
// - Desbloquear: solo si la cuenta está bloqueada; POST /users/{id}/unlock.
// - Los 409 (cannot_lock_self, already_locked, last_admin, not_locked) se explican por código.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { apiError, findRow, pageNotice, renderUsersPage, userOut, USERS } from "../../../test/users";

const LOCK_CONSEQUENCE = /Cierra todas sus sesiones y le impide entrar hasta que lo desbloquees/;

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

async function confirmIn(user: ReturnType<typeof renderUsersPage>["user"], email: string, action: RegExp): Promise<HTMLElement> {
  const row = await findRow(email);
  await user.click(within(row).getByRole("button", { name: action }));
  const dialog = screen.getByRole("dialog");
  await user.click(within(dialog).getByRole("button", { name: action }));
  return dialog;
}

describe("UsersPage · bloquear (US-051)", () => {
  it("pide confirmación con la consecuencia y hace POST /users/{id}/lock", async () => {
    const { mock, user } = renderUsersPage("/sistema/usuarios", {
      handlers: { [`POST /users/${USERS.coach.id}/lock`]: { status: 200, body: userOut(USERS.coach, { status: "locked" }) } },
    });
    const row = await findRow(USERS.coach.email);

    await user.click(within(row).getByRole("button", { name: /^Bloquear/ }));
    const dialog = screen.getByRole("dialog", { name: `¿Bloquear a ${USERS.coach.email}?` });
    expect(dialog).toHaveTextContent(LOCK_CONSEQUENCE);
    await user.click(within(dialog).getByRole("button", { name: /^Bloquear/ }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(mock.callsTo(`POST /users/${USERS.coach.id}/lock`)).toHaveLength(1);
    expect(pageNotice()).toHaveTextContent(`${USERS.coach.email} quedó bloqueado.`);
  });

  it("no aparece en la propia fila", async () => {
    renderUsersPage();
    const own = await findRow(USERS.own.email);

    expect(within(own).queryByRole("button", { name: /^Bloquear/ })).not.toBeInTheDocument();
    expect(within(own).queryByRole("button", { name: /^Desbloquear/ })).not.toBeInTheDocument();
  });

  it("no aparece en una cuenta bloqueada ni en una dada de baja", async () => {
    renderUsersPage();

    expect(within(await findRow(USERS.locked.email)).queryByRole("button", { name: /^Bloquear/ })).not.toBeInTheDocument();
    expect(within(await findRow(USERS.deleted.email)).queryByRole("button", { name: /^Bloquear/ })).not.toBeInTheDocument();
    expect(within(await findRow(USERS.pending.email)).getByRole("button", { name: /^Bloquear/ })).toBeInTheDocument();
  });

  it.each([
    ["cannot_lock_self", "No puedes bloquear tu propia cuenta. Si necesitas bloquearla, pídeselo a otro administrador."],
    ["already_locked", "Esta cuenta ya estaba bloqueada. Cierra y recarga la lista para ver su estado."],
    ["last_admin", "Debe quedar al menos un administrador activo. Nombra a otro administrador antes de hacer este cambio."],
  ])("409 %s se explica dentro del modal", async (code, message) => {
    const { user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.admin.id}/lock`]: apiError(409, code) } });

    const dialog = await confirmIn(user, USERS.admin.email, /^Bloquear/);

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(message);
  });
});

describe("UsersPage · desbloquear (US-051)", () => {
  it("solo aparece si la cuenta está bloqueada", async () => {
    renderUsersPage();

    expect(within(await findRow(USERS.locked.email)).getByRole("button", { name: /^Desbloquear/ })).toBeInTheDocument();
    for (const fixture of [USERS.coach, USERS.pending, USERS.admin, USERS.deleted]) {
      expect(within(await findRow(fixture.email)).queryByRole("button", { name: /^Desbloquear/ })).not.toBeInTheDocument();
    }
  });

  it("pide confirmación y hace POST /users/{id}/unlock", async () => {
    const { mock, user } = renderUsersPage("/sistema/usuarios", {
      handlers: { [`POST /users/${USERS.locked.id}/unlock`]: { status: 200, body: userOut(USERS.locked, { status: "active" }) } },
    });
    const row = await findRow(USERS.locked.email);

    await user.click(within(row).getByRole("button", { name: /^Desbloquear/ }));
    const dialog = screen.getByRole("dialog", { name: `¿Desbloquear a ${USERS.locked.email}?` });
    expect(dialog).toHaveTextContent("Podrá volver a entrar con su contraseña.");
    await user.click(within(dialog).getByRole("button", { name: /^Desbloquear/ }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(mock.callsTo(`POST /users/${USERS.locked.id}/unlock`)).toHaveLength(1);
    expect(pageNotice()).toHaveTextContent(`${USERS.locked.email} quedó desbloqueado.`);
  });

  it("409 not_locked se explica dentro del modal", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.locked.id}/unlock`]: apiError(409, "not_locked") } });

    const dialog = await confirmIn(user, USERS.locked.email, /^Desbloquear/);

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Esta cuenta ya no estaba bloqueada. Cierra y recarga la lista para ver su estado.");
  });

  it("un 403 dice que solo un administrador puede hacerlo", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.locked.id}/unlock`]: apiError(403, "forbidden") } });

    const dialog = await confirmIn(user, USERS.locked.email, /^Desbloquear/);

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Solo un administrador puede hacer esto. Si lo necesitas, pídeselo a uno.");
  });

  it("un 429 pide esperar", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.locked.id}/unlock`]: apiError(429, "rate_limited") } });

    const dialog = await confirmIn(user, USERS.locked.email, /^Desbloquear/);

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Demasiados intentos. Espera un momento y vuelve a intentarlo.");
  });
});

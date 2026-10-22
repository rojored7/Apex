// S2-F4b · US-051 (front): "Cerrar sesiones" en la fila de una cuenta.
// - El botón lleva el número de sesiones abiertas; ConfirmModal y POST
//   /users/{id}/revoke-sessions; el aviso usa {revoked} de la respuesta.
// - Sobre la propia cuenta (S2-D37) termina en clearSession() y /login: el api ya cortó el
//   access token de esta pestaña.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { getSession, installSessionBridge } from "../../../core/auth/session";
import { installTabDoubles, posted, resetTabDoubles } from "../../../test/authChannel";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { apiError, findRow, pageNotice, renderUsersPage, USERS } from "../../../test/users";

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

async function openRevoke(user: ReturnType<typeof renderUsersPage>["user"], email: string, label: RegExp): Promise<HTMLElement> {
  const row = await findRow(email);
  await user.click(within(row).getByRole("button", { name: label }));
  return screen.getByRole("dialog");
}

describe("UsersPage · cerrar sesiones (US-051)", () => {
  it("el botón lleva el número de sesiones abiertas y no aparece en una cuenta dada de baja", async () => {
    renderUsersPage();

    expect(within(await findRow(USERS.coach.email)).getByRole("button", { name: /^Cerrar sesiones \(3\)/ })).toBeInTheDocument();
    expect(within(await findRow(USERS.own.email)).getByRole("button", { name: /^Cerrar sesiones \(2\)/ })).toBeInTheDocument();
    expect(within(await findRow(USERS.pending.email)).getByRole("button", { name: /^Cerrar sesiones \(0\)/ })).toBeInTheDocument();
    expect(within(await findRow(USERS.deleted.email)).queryByRole("button", { name: /Cerrar sesiones/ })).not.toBeInTheDocument();
  });

  it("confirma y avisa cuántas cerró el api", async () => {
    const { mock, user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.coach.id}/revoke-sessions`]: { status: 200, body: { revoked: 4 } } } });

    const dialog = await openRevoke(user, USERS.coach.email, /^Cerrar sesiones \(3\)/);
    expect(dialog).toHaveAccessibleName(`¿Cerrar las sesiones de ${USERS.coach.email}?`);
    expect(dialog).toHaveTextContent("Se cierran sus 3 sesiones abiertas y tendrá que volver a iniciar sesión.");
    await user.click(within(dialog).getByRole("button", { name: "Cerrar sesiones" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(mock.callsTo(`POST /users/${USERS.coach.id}/revoke-sessions`)).toHaveLength(1);
    expect(pageNotice()).toHaveTextContent(`Se cerraron 4 sesiones de ${USERS.coach.email}.`);
    expect(getSession().status).toBe("authenticated");
  });

  it("con una sola sesión la consecuencia y el aviso van en singular", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.admin.id}/revoke-sessions`]: { status: 200, body: { revoked: 1 } } } });

    const dialog = await openRevoke(user, USERS.admin.email, /^Cerrar sesiones \(1\)/);
    expect(dialog).toHaveTextContent("Se cierra su sesión abierta y tendrá que volver a iniciar sesión.");
    await user.click(within(dialog).getByRole("button", { name: "Cerrar sesiones" }));

    expect(await screen.findByText(`Se cerró 1 sesión de ${USERS.admin.email}.`)).toBeInTheDocument();
  });

  it("sin sesiones abiertas igual corta los accesos vigentes", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.pending.id}/revoke-sessions`]: { status: 200, body: { revoked: 0 } } } });

    const dialog = await openRevoke(user, USERS.pending.email, /^Cerrar sesiones \(0\)/);
    expect(dialog).toHaveTextContent("No tiene sesiones abiertas; igual se corta cualquier acceso que siga vigente.");
    await user.click(within(dialog).getByRole("button", { name: "Cerrar sesiones" }));

    expect(await screen.findByText(`No había sesiones abiertas de ${USERS.pending.email}.`)).toBeInTheDocument();
  });

  it("sobre uno mismo avisa que también se cierra esta, limpia la sesión y lleva a /login", async () => {
    const { mock, router, user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.own.id}/revoke-sessions`]: { status: 200, body: { revoked: 2 } } } });

    const dialog = await openRevoke(user, USERS.own.email, /^Cerrar sesiones \(2\)/);
    expect(dialog).toHaveAccessibleName("¿Cerrar todas tus sesiones?");
    expect(dialog).toHaveTextContent("También se cierra la de este navegador y tendrás que volver a iniciar sesión.");
    await user.click(within(dialog).getByRole("button", { name: "Cerrar sesiones" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/login");
    });
    expect(mock.callsTo(`POST /users/${USERS.own.id}/revoke-sessions`)).toHaveLength(1);
    expect(getSession().status).toBe("anonymous");
    expect(screen.getByRole("heading", { name: "Iniciar sesión" })).toBeInTheDocument();
  });

  it("L3 (revisión del Sprint 2): sobre uno mismo publica logout para que las demás pestañas también salgan", async () => {
    installTabDoubles();
    const uninstall = installSessionBridge();
    const { router, user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.own.id}/revoke-sessions`]: { status: 200, body: { revoked: 2 } } } });

    const dialog = await openRevoke(user, USERS.own.email, /^Cerrar sesiones \(2\)/);
    await user.click(within(dialog).getByRole("button", { name: "Cerrar sesiones" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/login");
    });

    expect(posted.map((m) => (m.data as { type: string }).type)).toContain("logout");
    uninstall();
    resetTabDoubles();
  });

  it("si falla sobre uno mismo la sesión sigue y el error se explica", async () => {
    const { router, user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.own.id}/revoke-sessions`]: apiError(503, "unavailable") } });

    const dialog = await openRevoke(user, USERS.own.email, /^Cerrar sesiones \(2\)/);
    await user.click(within(dialog).getByRole("button", { name: "Cerrar sesiones" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("No pudimos completar la acción. Intenta de nuevo en un momento.");
    expect(getSession().status).toBe("authenticated");
    expect(router.state.location.pathname).toBe("/sistema/usuarios");
  });

  it("una respuesta con forma inesperada no se presenta como éxito", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.coach.id}/revoke-sessions`]: { status: 200, body: { revoked: "todas" } } } });

    const dialog = await openRevoke(user, USERS.coach.email, /^Cerrar sesiones \(3\)/);
    await user.click(within(dialog).getByRole("button", { name: "Cerrar sesiones" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("La respuesta del servidor no es válida. Recarga la página e intenta de nuevo.");
  });

  it("sin conexión lo dice y no cierra el modal", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", {
      handlers: {
        [`POST /users/${USERS.coach.id}/revoke-sessions`]: () => {
          throw new TypeError("Failed to fetch");
        },
      },
    });

    const dialog = await openRevoke(user, USERS.coach.email, /^Cerrar sesiones \(3\)/);
    await user.click(within(dialog).getByRole("button", { name: "Cerrar sesiones" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("No pudimos conectar con el servidor. Intenta de nuevo.");
  });

  it("el aviso se puede cerrar", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", { handlers: { [`POST /users/${USERS.coach.id}/revoke-sessions`]: { status: 200, body: { revoked: 3 } } } });
    const dialog = await openRevoke(user, USERS.coach.email, /^Cerrar sesiones \(3\)/);
    await user.click(within(dialog).getByRole("button", { name: "Cerrar sesiones" }));
    await screen.findByText(`Se cerraron 3 sesiones de ${USERS.coach.email}.`);

    await user.click(screen.getByRole("button", { name: "Cerrar aviso" }));

    expect(pageNotice()).toHaveTextContent("");
  });
});

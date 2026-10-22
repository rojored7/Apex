// S2-F4b · US-050 (front): "Dar de baja" en la fila de una cuenta.
// - ConfirmModal "La cuenta pierde el acceso de inmediato. Su historial se conserva." y
//   DELETE /users/{id}; al terminar la lista se vuelve a pedir y hay un aviso.
// - No aparece en la fila del usuario conectado (row.id === session.user.id; el api igual
//   protege) ni en una cuenta ya dada de baja.
// - 409 last_admin va como mensaje general dentro del modal, que sigue abierto.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { apiError, findRow, pageNotice, renderUsersPage, USERS } from "../../../test/users";

const CONSEQUENCE = "La cuenta pierde el acceso de inmediato. Su historial se conserva.";

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("UsersPage · dar de baja (US-050)", () => {
  it("la tabla tiene la columna Acción", async () => {
    renderUsersPage();
    await findRow(USERS.coach.email);

    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toContain("Acción");
  });

  it("pide confirmación con la consecuencia y hace DELETE /users/{id}", async () => {
    const { mock, user } = renderUsersPage("/sistema/usuarios", { handlers: { [`DELETE /users/${USERS.coach.id}`]: { status: 204 } } });
    const row = await findRow(USERS.coach.email);

    await user.click(within(row).getByRole("button", { name: /^Dar de baja/ }));

    const dialog = screen.getByRole("dialog", { name: `¿Dar de baja a ${USERS.coach.email}?` });
    expect(dialog).toHaveTextContent(CONSEQUENCE);
    expect(mock.callsTo(`DELETE /users/${USERS.coach.id}`)).toHaveLength(0);
    const before = mock.callsTo("GET /users").length;

    await user.click(within(dialog).getByRole("button", { name: /^Dar de baja/ }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(mock.callsTo(`DELETE /users/${USERS.coach.id}`)).toHaveLength(1);
    expect(pageNotice()).toHaveTextContent(`Se dio de baja a ${USERS.coach.email}.`);
    await waitFor(() => {
      expect(mock.callsTo("GET /users").length).toBeGreaterThan(before);
    });
  });

  it("Volver cierra el modal sin llamar al api", async () => {
    const { mock, user } = renderUsersPage();
    const row = await findRow(USERS.coach.email);

    await user.click(within(row).getByRole("button", { name: /^Dar de baja/ }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Volver" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.calls.filter((c) => c.method === "DELETE")).toHaveLength(0);
  });

  it("no aparece en la fila del usuario conectado", async () => {
    renderUsersPage();
    const own = await findRow(USERS.own.email);

    expect(within(own).queryByRole("button", { name: /^Dar de baja/ })).not.toBeInTheDocument();
    expect(within(await findRow(USERS.admin.email)).getByRole("button", { name: /^Dar de baja/ })).toBeInTheDocument();
  });

  it("cada botón nombra la cuenta, empezando por su texto visible", async () => {
    renderUsersPage();
    const row = await findRow(USERS.coach.email);

    expect(within(row).getByRole("button", { name: `Dar de baja: ${USERS.coach.email}` })).toHaveTextContent("Dar de baja");
    expect(within(row).getByRole("link", { name: `Editar: ${USERS.coach.email}` })).toHaveTextContent("Editar");
  });

  it("no aparece en una cuenta ya dada de baja", async () => {
    renderUsersPage();
    const row = await findRow(USERS.deleted.email);

    expect(within(row).queryByRole("button", { name: /^Dar de baja/ })).not.toBeInTheDocument();
  });

  it("409 last_admin se muestra como mensaje general y el modal sigue abierto", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", {
      handlers: { [`DELETE /users/${USERS.admin.id}`]: apiError(409, "last_admin", "Debe quedar al menos un administrador activo.") },
    });
    const row = await findRow(USERS.admin.email);

    await user.click(within(row).getByRole("button", { name: /^Dar de baja/ }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^Dar de baja/ }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Debe quedar al menos un administrador activo. Nombra a otro administrador antes de hacer este cambio.",
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("404 (otra persona ya la dio de baja) explica qué pasó y qué hacer", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", { handlers: { [`DELETE /users/${USERS.coach.id}`]: apiError(404, "user_not_found") } });
    const row = await findRow(USERS.coach.email);

    await user.click(within(row).getByRole("button", { name: /^Dar de baja/ }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^Dar de baja/ }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("No encontramos esta cuenta: puede que otra persona ya la haya dado de baja. Cierra y recarga la lista.");
  });

  it("un 5xx o la red no se presentan como éxito", async () => {
    const { user } = renderUsersPage("/sistema/usuarios", { handlers: { [`DELETE /users/${USERS.coach.id}`]: apiError(500, "internal") } });
    const row = await findRow(USERS.coach.email);

    await user.click(within(row).getByRole("button", { name: /^Dar de baja/ }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^Dar de baja/ }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("No pudimos completar la acción. Intenta de nuevo en un momento.");
    expect(pageNotice()).toHaveTextContent("");
  });

  it("la lista con las acciones no tiene violaciones de accesibilidad", async () => {
    const { container } = renderUsersPage();
    await findRow(USERS.coach.email);

    expect(await axe(container)).toHaveNoViolations();
  });
});

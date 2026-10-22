// S2-F4b · US-049 (front): edición de una cuenta en el SidePanel de Usuarios.html.
// - Se abre desde `?usuario=<id>` (enlace del correo, del 409 del alta o compartido) y desde
//   "Editar" en la fila, sin perder los filtros de la URL. GET /users/{id} (incluye bajas).
// - Correo y rol (admin o coach). PATCH /users/{id} solo con lo que cambió.
// - 409 email_taken bajo el correo con enlace al existente; 409 last_admin como mensaje
//   general; 422 al campo. Una cuenta dada de baja se ve, pero no se edita.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { getSession } from "../../../core/auth/session";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { apiError, findRow, OWN_ID, renderUsersPage, userOut, USERS } from "../../../test/users";

const at = (id: string, extra = ""): string => `/sistema/usuarios?${extra}usuario=${id}`;
const panel = () => screen.getByRole("dialog", { name: "Editar usuario" });
const emailField = () => within(panel()).getByRole("textbox", { name: /Correo/ });

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("EditUserPanel · abrir (US-049)", () => {
  it("se abre desde ?usuario=<id> con el correo y el rol de GET /users/{id}", async () => {
    const { mock } = renderUsersPage(at(USERS.coach.id));

    expect(await within(panel()).findByDisplayValue(USERS.coach.email)).toBeInTheDocument();
    const role = within(panel()).getByRole("combobox", { name: /Rol/ });
    expect(role).toHaveValue("coach");
    expect(within(role).getAllByRole("option").map((o) => o.textContent)).toEqual(["Coach", "Admin"]);
    expect(mock.callsTo(`GET /users/${USERS.coach.id}`)).toHaveLength(1);
  });

  it("un ?usuario= vacío no abre el panel ni pide nada", async () => {
    const { mock } = renderUsersPage("/sistema/usuarios?usuario=");
    await findRow(USERS.coach.email);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.calls.filter((c) => c.path.startsWith("/users/"))).toHaveLength(0);
  });

  it("mientras carga lo anuncia", () => {
    renderUsersPage(at(USERS.coach.id), { handlers: { [`GET /users/${USERS.coach.id}`]: () => new Promise(() => undefined) } });

    expect(within(panel()).getByText("Cargando la cuenta…")).toBeInTheDocument();
  });

  it("'Editar' en la fila abre el panel y conserva los filtros de la URL", async () => {
    const { router, user } = renderUsersPage("/sistema/usuarios?role=coach");
    const row = await findRow(USERS.coach.email);

    await user.click(within(row).getByRole("link", { name: /^Editar/ }));

    expect(await within(panel()).findByDisplayValue(USERS.coach.email)).toBeInTheDocument();
    expect(router.state.location.search).toBe(`?role=coach&usuario=${USERS.coach.id}`);
  });

  it("el correo de la fila también abre el panel", async () => {
    const { user } = renderUsersPage();

    await user.click(await screen.findByRole("link", { name: USERS.pending.email }));

    expect(await within(panel()).findByDisplayValue(USERS.pending.email)).toBeInTheDocument();
    // Los cambios y el error de la cuenta anterior no pasan a la nueva.
    expect(within(panel()).getByRole("button", { name: "Guardar" })).toBeDisabled();
    expect(within(panel()).queryByText("Ya existe una cuenta con este correo.")).not.toBeInTheDocument();
    await user.click(within(panel()).getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("Cancelar cierra el panel y quita ?usuario de la URL sin tocar los filtros", async () => {
    const { router, user } = renderUsersPage(at(USERS.coach.id, "status=active&"));
    await within(panel()).findByDisplayValue(USERS.coach.email);

    await user.click(within(panel()).getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(router.state.location.search).toBe("?status=active");
  });

  it("un id que no existe explica qué pasó y qué hacer", async () => {
    renderUsersPage(at("99999999-9999-4999-8999-999999999999"), {
      handlers: { "GET /users/99999999-9999-4999-8999-999999999999": apiError(404, "user_not_found") },
    });

    expect(await within(panel()).findByRole("alert")).toHaveTextContent("No encontramos esta cuenta. Cierra el panel y búscala en la lista.");
  });

  it("un error del servidor se puede reintentar", async () => {
    let fail = true;
    const { user } = renderUsersPage(at(USERS.coach.id), {
      handlers: { [`GET /users/${USERS.coach.id}`]: () => (fail ? apiError(500, "internal") : { status: 200, body: userOut(USERS.coach) }) },
    });

    expect(await within(panel()).findByRole("alert")).toHaveTextContent("No pudimos cargar la cuenta. Intenta de nuevo en un momento.");
    fail = false;
    await user.click(within(panel()).getByRole("button", { name: "Reintentar" }));

    expect(await within(panel()).findByDisplayValue(USERS.coach.email)).toBeInTheDocument();
  });

  it("una cuenta dada de baja se ve, pero no se edita", async () => {
    renderUsersPage(at(USERS.deleted.id));

    expect(await within(panel()).findByText("Esta cuenta está dada de baja. Su historial se conserva y ya no se puede editar.")).toBeInTheDocument();
    expect(within(panel()).getByText(USERS.deleted.email)).toBeInTheDocument();
    expect(within(panel()).queryByRole("button", { name: "Guardar" })).not.toBeInTheDocument();
  });

  it("el rol de un socio no se cambia aquí", async () => {
    const member = { ...USERS.coach, id: "88888888-8888-4888-8888-888888888888", email: "socia@apex.test", role: "member" as const, member_id: "m-1" };
    renderUsersPage(at(member.id), { rows: [member] });

    await within(panel()).findByDisplayValue(member.email);
    expect(within(panel()).queryByRole("combobox", { name: /Rol/ })).not.toBeInTheDocument();
    expect(within(panel()).getByText("Socio: su rol no se cambia desde aquí.")).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    renderUsersPage(at(USERS.coach.id));
    await within(panel()).findByDisplayValue(USERS.coach.email);

    expect(await axe(panel())).toHaveNoViolations();
  });
});

describe("EditUserPanel · guardar (US-049)", () => {
  it("Guardar queda deshabilitado mientras no hay cambios", async () => {
    renderUsersPage(at(USERS.coach.id));
    await within(panel()).findByDisplayValue(USERS.coach.email);

    expect(within(panel()).getByRole("button", { name: "Guardar" })).toBeDisabled();
  });

  it("envía solo el correo si solo cambió el correo; cierra, avisa y relee la lista", async () => {
    const { mock, router, user } = renderUsersPage(at(USERS.coach.id), {
      handlers: { [`PATCH /users/${USERS.coach.id}`]: { status: 200, body: userOut(USERS.coach, { email: "carlos.r@apex.test" }) } },
    });
    await within(panel()).findByDisplayValue(USERS.coach.email);
    const before = mock.callsTo("GET /users").length;

    await user.clear(emailField());
    await user.type(emailField(), "  carlos.r@apex.test ");
    await user.click(within(panel()).getByRole("button", { name: "Guardar" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(mock.callsTo(`PATCH /users/${USERS.coach.id}`).map((c) => c.body)).toEqual([{ email: "carlos.r@apex.test" }]);
    expect(router.state.location.search).toBe("");
    expect(screen.getByRole("status")).toHaveTextContent("Cambios guardados para carlos.r@apex.test.");
    await waitFor(() => {
      expect(mock.callsTo("GET /users").length).toBeGreaterThan(before);
    });
  });

  it("envía solo el rol si solo cambió el rol", async () => {
    const { mock, user } = renderUsersPage(at(USERS.coach.id), {
      handlers: { [`PATCH /users/${USERS.coach.id}`]: { status: 200, body: userOut(USERS.coach, { role: "admin" }) } },
    });
    await within(panel()).findByDisplayValue(USERS.coach.email);

    await user.selectOptions(within(panel()).getByRole("combobox", { name: /Rol/ }), "Admin");
    await user.click(within(panel()).getByRole("button", { name: "Guardar" }));

    await waitFor(() => {
      expect(mock.callsTo(`PATCH /users/${USERS.coach.id}`).map((c) => c.body)).toEqual([{ role: "admin" }]);
    });
  });

  it("un correo inválido se marca en el campo sin llamar al api", async () => {
    const { mock, user } = renderUsersPage(at(USERS.coach.id));
    await within(panel()).findByDisplayValue(USERS.coach.email);

    await user.clear(emailField());
    await user.type(emailField(), "no-es-correo");
    await user.click(within(panel()).getByRole("button", { name: "Guardar" }));

    expect(await within(panel()).findByText("Escribe un correo válido, por ejemplo ana@correo.com.")).toBeInTheDocument();
    expect(mock.calls.filter((c) => c.method === "PATCH")).toHaveLength(0);
  });

  it("409 email_taken va bajo el correo con enlace al usuario existente, que abre su edición", async () => {
    const { router, user } = renderUsersPage(at(USERS.coach.id), {
      handlers: { [`PATCH /users/${USERS.coach.id}`]: apiError(409, "email_taken", "Ya existe una cuenta con este correo.", { field: "email", existing_id: USERS.pending.id }) },
    });
    await within(panel()).findByDisplayValue(USERS.coach.email);

    await user.clear(emailField());
    await user.type(emailField(), USERS.pending.email);
    await user.click(within(panel()).getByRole("button", { name: "Guardar" }));

    expect(await within(panel()).findByText("Ya existe una cuenta con este correo.")).toBeInTheDocument();
    const existing = within(panel()).getByRole("link", { name: "Ver el usuario existente" });
    expect(existing).toHaveAttribute("href", at(USERS.pending.id));
    await user.click(existing);

    await waitFor(() => {
      expect(router.state.location.search).toBe(`?usuario=${USERS.pending.id}`);
    });
    expect(await within(panel()).findByDisplayValue(USERS.pending.email)).toBeInTheDocument();
  });

  it("409 last_admin va como mensaje general y el panel sigue abierto", async () => {
    const { user } = renderUsersPage(at(USERS.admin.id), {
      handlers: { [`PATCH /users/${USERS.admin.id}`]: apiError(409, "last_admin", "Debe quedar al menos un administrador activo.") },
    });
    await within(panel()).findByDisplayValue(USERS.admin.email);

    await user.selectOptions(within(panel()).getByRole("combobox", { name: /Rol/ }), "Coach");
    await user.click(within(panel()).getByRole("button", { name: "Guardar" }));

    expect(await within(panel()).findByRole("alert")).toHaveTextContent(
      "Debe quedar al menos un administrador activo. Nombra a otro administrador antes de quitarle el rol a esta cuenta.",
    );
    expect(panel()).toBeInTheDocument();
  });

  it("un 422 del correo se marca en el campo", async () => {
    const { user } = renderUsersPage(at(USERS.coach.id), {
      handlers: { [`PATCH /users/${USERS.coach.id}`]: apiError(422, "validation_error", "value is not a valid email", { field: "email" }) },
    });
    await within(panel()).findByDisplayValue(USERS.coach.email);

    await user.clear(emailField());
    await user.type(emailField(), "otro@apex.test");
    await user.click(within(panel()).getByRole("button", { name: "Guardar" }));

    expect(await within(panel()).findByText("El servidor no aceptó este correo. Revísalo e intenta de nuevo.")).toBeInTheDocument();
  });

  it("un 404 al guardar (la dieron de baja mientras tanto) lo explica", async () => {
    const { user } = renderUsersPage(at(USERS.coach.id), { handlers: { [`PATCH /users/${USERS.coach.id}`]: apiError(404, "user_not_found") } });
    await within(panel()).findByDisplayValue(USERS.coach.email);

    await user.selectOptions(within(panel()).getByRole("combobox", { name: /Rol/ }), "Admin");
    await user.click(within(panel()).getByRole("button", { name: "Guardar" }));

    expect(await within(panel()).findByRole("alert")).toHaveTextContent("No encontramos esta cuenta: puede que otra persona ya la haya dado de baja. Cierra y recarga la lista.");
  });

  it("mientras guarda no se puede cerrar", async () => {
    const { user } = renderUsersPage(at(USERS.coach.id), { handlers: { [`PATCH /users/${USERS.coach.id}`]: () => new Promise(() => undefined) } });
    await within(panel()).findByDisplayValue(USERS.coach.email);

    await user.selectOptions(within(panel()).getByRole("combobox", { name: /Rol/ }), "Admin");
    await user.click(within(panel()).getByRole("button", { name: "Guardar" }));
    await user.click(within(panel()).getByRole("button", { name: "Cancelar" }));

    expect(panel()).toBeInTheDocument();
    expect(within(panel()).getByRole("button", { name: "Guardando…" })).toHaveAttribute("aria-busy", "true");
  });

  it("enviar dos veces con el guardado en curso hace un solo PATCH", async () => {
    const { mock, user } = renderUsersPage(at(USERS.coach.id), { handlers: { [`PATCH /users/${USERS.coach.id}`]: () => new Promise(() => undefined) } });
    await within(panel()).findByDisplayValue(USERS.coach.email);
    await user.selectOptions(within(panel()).getByRole("combobox", { name: /Rol/ }), "Admin");
    const form = within(panel()).getByRole("form", { name: "Editar usuario" });

    fireEvent.submit(form);
    await waitFor(() => {
      expect(mock.callsTo(`PATCH /users/${USERS.coach.id}`)).toHaveLength(1);
    });
    fireEvent.submit(form);
    fireEvent.submit(form);

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(mock.callsTo(`PATCH /users/${USERS.coach.id}`)).toHaveLength(1);
  });

  it("al cambiar la propia cuenta relee la sesión (rol y correo vigentes)", async () => {
    const own = { ...USERS.own };
    const { mock, user } = renderUsersPage(at(OWN_ID), {
      handlers: {
        [`PATCH /users/${OWN_ID}`]: { status: 200, body: userOut(own, { role: "coach" }) },
        "GET /auth/me": { status: 200, body: { id: OWN_ID, email: own.email, role: "coach", member_id: null, gym_name: "Box de prueba", must_change_password: false } },
      },
    });
    await within(panel()).findByDisplayValue(own.email);

    await user.selectOptions(within(panel()).getByRole("combobox", { name: /Rol/ }), "Coach");
    await user.click(within(panel()).getByRole("button", { name: "Guardar" }));

    await waitFor(() => {
      expect(mock.callsTo("GET /auth/me")).toHaveLength(1);
    });
    await waitFor(() => {
      expect(getSession().user?.role).toBe("coach");
    });
  });
});

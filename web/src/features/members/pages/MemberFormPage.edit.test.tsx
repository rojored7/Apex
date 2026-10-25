// S3-F1 · US-075 (front): /socios/:id/editar (Socio_Form.html en modo editar).
// - Precarga lo no sensible desde GET /members/{id}; los cinco sensibles NO se precargan en claro:
//   muestran su máscara como ayuda y "Cambiar" (el documento solo con members.document.update; el
//   coach no lo ve) o "Quitar" (los opcionales). Nunca se llama a reveal desde el formulario.
// - PATCH /members/{id} lleva solo lo modificado (dirtyFields y "Cambiar"/"Quitar"; S3-D46).
// - 403 `forbidden_field` y 409 `member_document_duplicated` (con enlace al socio) bajo su campo;
//   `consent_cannot_be_withdrawn` bajo la autorización; `member_deactivated`, 403, 429, 5xx y busy
//   como aviso general. La autorización solo se marca ("Registrar autorización") si falta.
// - Tras guardar vuelve a la ficha con "Cambios guardados" y la caché de mutaciones no conserva el
//   cuerpo (gcTime 0 y reset(), S3-D52).
import { screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { BUSY_MESSAGE } from "../../../core/api/errorCodes";
import {
  apiError,
  DELETED_OVERRIDES,
  DETAIL_PATH,
  DUPLICATE_ID,
  MEMBER_ID,
  memberDetailBody,
  ok,
  patchBodies,
  REVEAL_PATH,
  renderMemberDetail,
} from "../../../test/memberDetail";
import { setViewportWidth, testQueryClient, type MockReply } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";

const EDIT = `/socios/${MEMBER_ID}/editar`;
const group = (name: string): HTMLElement => screen.getByRole("group", { name });
const save = () => screen.getByRole("button", { name: "Guardar cambios" });

/** El texto de error asociado a un control por aria-describedby. */
function errorOf(control: HTMLElement): string {
  const ids = control.getAttribute("aria-describedby")?.split(" ") ?? [];
  return ids
    .map((id) => document.getElementById(id))
    .filter((node): node is HTMLElement => node !== null && node.id.endsWith("-error"))
    .map((node) => node.textContent)
    .join(" ");
}

async function openEdit(options: Parameters<typeof renderMemberDetail>[1] = {}) {
  const harness = renderMemberDetail(EDIT, options);
  await screen.findByRole("heading", { level: 1, name: "Editar socio" });
  return harness;
}

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

describe("MemberFormPage en edición · estructura y precarga", () => {
  it("muestra las migas hasta la ficha y precarga nombres, apellidos y sexo", async () => {
    await openEdit();

    const crumbs = screen.getByRole("navigation", { name: "Migas" });
    expect(within(crumbs).getByRole("link", { name: "Socios" })).toHaveAttribute("href", "/socios");
    expect(within(crumbs).getByRole("link", { name: "Laura Gómez" })).toHaveAttribute("href", `/socios/${MEMBER_ID}`);
    expect(screen.getByRole("textbox", { name: /^Nombres/ })).toHaveValue("Laura");
    expect(screen.getByRole("textbox", { name: /^Apellidos/ })).toHaveValue("Gómez");
    expect(screen.getByRole("combobox", { name: /^Sexo/ })).toHaveValue("f");
    expect(screen.getByRole("link", { name: "Cancelar" })).toHaveAttribute("href", `/socios/${MEMBER_ID}`);
  });

  it("los sensibles no se precargan: muestran la máscara como ayuda y 'Cambiar', sin pedir el claro", async () => {
    const { mock } = await openEdit();

    for (const [name, masked] of [
      ["Documento", "CC •••• 4417"],
      ["Fecha de nacimiento", "••/••/1991"],
      ["Teléfono (WhatsApp)", "••• ••• 4567"],
      ["Correo", "l•••@•••.co"],
      ["Contacto de emergencia", "Registrado"],
    ] as const) {
      expect(within(group(name)).getByText(`Actual: ${masked}`)).toBeInTheDocument();
      expect(within(group(name)).getByRole("button", { name: "Cambiar" })).toBeInTheDocument();
      expect(within(group(name)).queryByRole("textbox")).not.toBeInTheDocument();
    }
    expect(mock.callsTo(`POST ${REVEAL_PATH}`)).toHaveLength(0);
    for (const input of screen.getAllByRole("textbox")) expect((input as HTMLInputElement).value).not.toContain("•");
  });

  it("el admin cambia el tipo de documento; el coach no ve 'Cambiar' del documento ni el selector de tipo", async () => {
    await openEdit();
    expect(screen.getByRole("combobox", { name: /^Tipo de documento/ })).toHaveValue("CC");
    signOutForTests();

    signInAs("coach");
    await openEdit();
    expect(within(group("Documento")).queryByRole("button", { name: "Cambiar" })).not.toBeInTheDocument();
    expect(within(group("Documento")).getByText("Solo un administrador puede cambiar el documento.")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: /^Tipo de documento/ })).not.toBeInTheDocument();
    expect(within(group("Teléfono (WhatsApp)")).getByRole("button", { name: "Cambiar" })).toBeInTheDocument();
  });

  it("con la autorización registrada la muestra; sin ella ofrece 'Registrar autorización' sin marcar", async () => {
    await openEdit();
    expect(screen.getByText("Autorización registrada el 12 mar 2026 · versión 2026-03")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    signOutForTests();

    signInAs("admin");
    await openEdit({ handlers: { [`GET ${DETAIL_PATH}`]: ok(memberDetailBody({ data_consent_at: null, data_consent_version: null })) } });
    expect(screen.getByRole("checkbox", { name: "Registrar autorización" })).not.toBeChecked();
  });
});

describe("MemberFormPage en edición · solo lo modificado", () => {
  it("cambiar el nombre envía solo first_name y vuelve a la ficha con 'Cambios guardados'", async () => {
    const { mock, user } = await openEdit({ handlers: { [`PATCH ${DETAIL_PATH}`]: ok(memberDetailBody({ first_name: "Laurita" })) } });

    await user.clear(screen.getByRole("textbox", { name: /^Nombres/ }));
    await user.type(screen.getByRole("textbox", { name: /^Nombres/ }), "Laurita");
    await user.click(save());

    expect(await screen.findByText("Cambios guardados")).toBeInTheDocument();
    expect(patchBodies(mock)).toEqual([{ first_name: "Laurita" }]);
    expect(screen.getByTestId("location").textContent).toBe(`/socios/${MEMBER_ID}`);
  });

  it("'Cambiar' del teléfono abre un campo vacío y envía solo phone", async () => {
    const { mock, user } = await openEdit({ handlers: { [`PATCH ${DETAIL_PATH}`]: ok(memberDetailBody()) } });

    await user.click(within(group("Teléfono (WhatsApp)")).getByRole("button", { name: "Cambiar" }));
    const input = within(group("Teléfono (WhatsApp)")).getByRole("textbox", { name: /^Nuevo teléfono/ });
    expect(input).toHaveValue("");
    expect(input).toHaveFocus();
    await user.type(input, "300 765 4321");
    await user.click(save());

    await waitFor(() => {
      expect(patchBodies(mock)).toEqual([{ phone: "300 765 4321" }]);
    });
  });

  it("'Cancelar cambio' vuelve a la máscara y no envía nada de ese campo", async () => {
    const { mock, user } = await openEdit();

    await user.click(within(group("Correo")).getByRole("button", { name: "Cambiar" }));
    await user.type(within(group("Correo")).getByRole("textbox"), "nuevo@correo.co");
    await user.click(within(group("Correo")).getByRole("button", { name: "Cancelar cambio" }));

    expect(within(group("Correo")).queryByRole("textbox")).not.toBeInTheDocument();
    expect(within(group("Correo")).getByRole("button", { name: "Cambiar" })).toHaveFocus();
    // Revisión S3-F1 (TS LOW-8): lo escrito se descarta y guardar no envía nada.
    await user.click(save());
    expect(await screen.findByText("No hay cambios para guardar.")).toBeInTheDocument();
    expect(patchBodies(mock)).toEqual([]);
    await user.click(within(group("Correo")).getByRole("button", { name: "Cambiar" }));
    expect(within(group("Correo")).getByRole("textbox")).toHaveValue("");
  });

  it("'Quitar' el correo envía email: null y se puede deshacer", async () => {
    const { mock, user } = await openEdit({ handlers: { [`PATCH ${DETAIL_PATH}`]: ok(memberDetailBody({ email: null })) } });

    await user.click(within(group("Correo")).getByRole("button", { name: "Quitar" }));
    expect(within(group("Correo")).getByText("Se quitará al guardar.")).toBeInTheDocument();
    expect(within(group("Correo")).getByRole("button", { name: "Deshacer" })).toHaveFocus();
    await user.click(within(group("Correo")).getByRole("button", { name: "Deshacer" }));
    expect(within(group("Correo")).queryByText("Se quitará al guardar.")).not.toBeInTheDocument();
    expect(within(group("Correo")).getByRole("button", { name: "Quitar" })).toHaveFocus();
    await user.click(within(group("Correo")).getByRole("button", { name: "Quitar" }));
    await user.click(save());

    await waitFor(() => {
      expect(patchBodies(mock)).toEqual([{ email: null }]);
    });
  });

  it("el documento no se puede quitar y el contacto nuevo viaja como objeto", async () => {
    const { mock, user } = await openEdit({ handlers: { [`PATCH ${DETAIL_PATH}`]: ok(memberDetailBody()) } });

    expect(within(group("Documento")).queryByRole("button", { name: "Quitar" })).not.toBeInTheDocument();
    await user.click(within(group("Contacto de emergencia")).getByRole("button", { name: "Cambiar" }));
    await user.type(within(group("Contacto de emergencia")).getByRole("textbox", { name: /^Nombre del contacto/ }), "Marta Gómez");
    await user.type(within(group("Contacto de emergencia")).getByRole("textbox", { name: /^Teléfono del contacto/ }), "3110000008");
    await user.click(save());

    await waitFor(() => {
      expect(patchBodies(mock)).toEqual([{ emergency_contact: { name: "Marta Gómez", phone: "3110000008" } }]);
    });
  });

  it("marcar 'Registrar autorización' envía data_consent: true", async () => {
    const { mock, user } = await openEdit({
      handlers: {
        [`GET ${DETAIL_PATH}`]: ok(memberDetailBody({ data_consent_at: null, data_consent_version: null })),
        [`PATCH ${DETAIL_PATH}`]: ok(memberDetailBody()),
      },
    });

    await user.click(screen.getByRole("checkbox", { name: "Registrar autorización" }));
    await user.click(save());

    await waitFor(() => {
      expect(patchBodies(mock)).toEqual([{ data_consent: true }]);
    });
  });

  it("sin cambios no envía nada y lo dice", async () => {
    const { mock, user } = await openEdit();

    await user.click(save());

    expect(await screen.findByText("No hay cambios para guardar.")).toBeInTheDocument();
    expect(patchBodies(mock)).toEqual([]);
  });

  it("un 'Cambiar' sin valor nuevo no se envía: avisa bajo el campo", async () => {
    const { mock, user } = await openEdit();

    await user.click(within(group("Teléfono (WhatsApp)")).getByRole("button", { name: "Cambiar" }));
    await user.click(save());

    const input = within(group("Teléfono (WhatsApp)")).getByRole("textbox", { name: /^Nuevo teléfono/ });
    expect(errorOf(input)).toBe("Escribe el nuevo teléfono o cancela el cambio.");
    expect(input).toHaveFocus();
    expect(patchBodies(mock)).toEqual([]);
  });

  it("tras guardar la caché de mutaciones no conserva el cuerpo (S3-D52)", async () => {
    const queryClient = testQueryClient();
    const { user } = await openEdit({ queryClient, handlers: { [`PATCH ${DETAIL_PATH}`]: ok(memberDetailBody()) } });

    await user.click(within(group("Teléfono (WhatsApp)")).getByRole("button", { name: "Cambiar" }));
    await user.type(within(group("Teléfono (WhatsApp)")).getByRole("textbox"), "300 765 4321");
    await user.click(save());

    await screen.findByText("Cambios guardados");
    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toEqual([]);
    });
  });
});

describe("MemberFormPage en edición · errores del api", () => {
  async function changeDocument(reply: MockReply) {
    const harness = await openEdit({ handlers: { [`PATCH ${DETAIL_PATH}`]: reply } });
    await harness.user.click(within(group("Documento")).getByRole("button", { name: "Cambiar" }));
    await harness.user.type(within(group("Documento")).getByRole("textbox", { name: /^Nuevo documento/ }), "1020304418");
    await harness.user.click(save());
    return harness;
  }

  it("403 forbidden_field del documento se muestra bajo el campo", async () => {
    await changeDocument(apiError(403, "forbidden_field", { field: "document" }));

    const input = within(group("Documento")).getByRole("textbox", { name: /^Nuevo documento/ });
    await waitFor(() => {
      expect(errorOf(input)).toBe("Solo un administrador puede cambiar el documento.");
    });
  });

  it("409 de documento repetido enlaza a la ficha del otro socio (S2-D34)", async () => {
    const { user } = await changeDocument(apiError(409, "member_document_duplicated", { field: "document", existing_id: DUPLICATE_ID }));

    const input = within(group("Documento")).getByRole("textbox", { name: /^Nuevo documento/ });
    await waitFor(() => {
      expect(errorOf(input)).toContain("Ya existe un socio con este documento.");
    });
    await user.click(screen.getByRole("link", { name: "Ver socio existente" }));
    expect(screen.getByTestId("location").textContent).toBe(`/socios/${DUPLICATE_ID}`);
  });

  it("consent_cannot_be_withdrawn va bajo la autorización", async () => {
    const { user } = await openEdit({
      handlers: {
        [`GET ${DETAIL_PATH}`]: ok(memberDetailBody({ data_consent_at: null, data_consent_version: null })),
        [`PATCH ${DETAIL_PATH}`]: apiError(422, "consent_cannot_be_withdrawn", { field: "data_consent" }),
      },
    });

    await user.click(screen.getByRole("checkbox", { name: "Registrar autorización" }));
    await user.click(save());

    expect(await screen.findByText("La autorización no se puede retirar desde aquí. Si el socio la retira, pídeselo a un administrador.")).toBeInTheDocument();
  });

  it("un 422 de un campo va bajo ese campo", async () => {
    const { user } = await openEdit({ handlers: { [`PATCH ${DETAIL_PATH}`]: apiError(422, "validation_error", { field: "phone" }) } });

    await user.click(within(group("Teléfono (WhatsApp)")).getByRole("button", { name: "Cambiar" }));
    await user.type(within(group("Teléfono (WhatsApp)")).getByRole("textbox"), "300 765 4321");
    await user.click(save());

    const input = within(group("Teléfono (WhatsApp)")).getByRole("textbox");
    await waitFor(() => {
      expect(errorOf(input)).toBe("El teléfono no tiene suficientes dígitos. Revísalo e intenta de nuevo.");
    });
  });

  it.each([
    [apiError(409, "member_deactivated"), "Este socio está dado de baja. Reactívalo desde su ficha antes de editarlo."],
    [apiError(403, "forbidden"), "No tienes permiso para editar socios. Si lo necesitas, pídeselo a un administrador."],
    [apiError(404, "member_not_found"), "Este socio ya no existe. Vuelve a la lista de socios."],
    [apiError(429, "rate_limited", {}, { "Retry-After": "15" }), "Hiciste muchos cambios seguidos. Espera 15 segundos e intenta de nuevo."],
    [apiError(500, "internal_error"), "No pudimos guardar los cambios. Intenta de nuevo en un momento."],
    [apiError(503, "busy", {}, { "Retry-After": "1" }), BUSY_MESSAGE],
  ])("un error general se avisa arriba, con foco, y el formulario conserva lo escrito (%#)", async (reply, message) => {
    const { user } = await openEdit({ handlers: { [`PATCH ${DETAIL_PATH}`]: reply } });

    await user.clear(screen.getByRole("textbox", { name: /^Nombres/ }));
    await user.type(screen.getByRole("textbox", { name: /^Nombres/ }), "Laurita");
    await user.click(save());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(message);
    expect(alert).toHaveFocus();
    expect(screen.getByRole("textbox", { name: /^Nombres/ })).toHaveValue("Laurita");
  });
});

describe("MemberFormPage en edición · estados de la carga", () => {
  it("un dado de baja no se edita: lo explica y enlaza a su ficha", async () => {
    renderMemberDetail(EDIT, { handlers: { [`GET ${DETAIL_PATH}`]: ok(memberDetailBody(DELETED_OVERRIDES)) } });

    expect(await screen.findByText("Este socio está dado de baja. Reactívalo desde su ficha antes de editarlo.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Guardar cambios" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Volver a la ficha" })).toHaveAttribute("href", `/socios/${MEMBER_ID}`);
  });

  it("un 404 dice 'Socio no encontrado'", async () => {
    renderMemberDetail(EDIT, { handlers: { [`GET ${DETAIL_PATH}`]: apiError(404, "member_not_found") } });

    expect(await screen.findByRole("heading", { level: 1, name: "Socio no encontrado" })).toBeInTheDocument();
  });

  it("mientras carga lo anuncia y un 500 ofrece reintentar", async () => {
    let fail = true;
    const { user } = renderMemberDetail(EDIT, { handlers: { [`GET ${DETAIL_PATH}`]: () => (fail ? apiError(500, "internal_error") : ok(memberDetailBody())) } });

    expect(screen.getByRole("status")).toHaveTextContent("Cargando el socio…");
    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar la ficha del socio. Intenta de nuevo en un momento.");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Editar socio" })).toBeInTheDocument();
  });

  it("sin violaciones de axe con un campo en 'Cambiar' y otro en 'Quitar'", async () => {
    const { container, user } = await openEdit();

    await user.click(within(group("Teléfono (WhatsApp)")).getByRole("button", { name: "Cambiar" }));
    await user.click(within(group("Correo")).getByRole("button", { name: "Quitar" }));

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("MemberFormPage en edición · revisión S3-F1", () => {
  it("TS MEDIUM-2: un error de un campo sin control en pantalla se avisa arriba con foco", async () => {
    const { user } = await openEdit({ handlers: { [`PATCH ${DETAIL_PATH}`]: apiError(403, "forbidden_field", { field: "document" }) } });

    await user.clear(screen.getByRole("textbox", { name: /^Nombres/ }));
    await user.type(screen.getByRole("textbox", { name: /^Nombres/ }), "Laurita");
    await user.click(save());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Solo un administrador puede cambiar el documento.");
    expect(alert).toHaveFocus();
  });

  it("TS MEDIUM-1: una relectura fallida con el formulario abierto no pierde lo escrito", async () => {
    let fail = false;
    const queryClient = testQueryClient();
    const { user } = await openEdit({ queryClient, handlers: { [`GET ${DETAIL_PATH}`]: () => (fail ? apiError(500, "internal_error") : ok(memberDetailBody())) } });
    await user.clear(screen.getByRole("textbox", { name: /^Nombres/ }));
    await user.type(screen.getByRole("textbox", { name: /^Nombres/ }), "Laurita");

    fail = true;
    await queryClient.invalidateQueries({ queryKey: ["members"] });

    expect(await screen.findByText("No pudimos actualizar la ficha; se muestran los últimos datos cargados. Recarga la página en un momento.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /^Nombres/ })).toHaveValue("Laurita");
  });

  it("TS LOW-3: 'No hay cambios para guardar.' se quita al editar", async () => {
    const { user } = await openEdit();

    await user.click(save());
    expect(await screen.findByText("No hay cambios para guardar.")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: /^Nombres/ }), "a");

    expect(screen.queryByText("No hay cambios para guardar.")).not.toBeInTheDocument();
  });

  it("LOW-3 de seguridad: un :id sin forma de UUID da 'Socio no encontrado' sin pedir nada", async () => {
    const { mock } = renderMemberDetail("/socios/no-es-un-id/editar");

    expect(await screen.findByRole("heading", { level: 1, name: "Socio no encontrado" })).toBeInTheDocument();
    expect(mock.calls).toHaveLength(0);
  });
});

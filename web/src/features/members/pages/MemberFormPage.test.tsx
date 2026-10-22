// S2-F6 · US-069 (front): /socios/nuevo (Socio_Form.html).
// - Validación en el cliente con las reglas de MemberCreate (B7): nombres y apellidos, documento
//   de 3 a 30 caracteres, fecha de nacimiento no futura, correo con forma, teléfono con al menos
//   7 dígitos y contacto de emergencia con nombre y teléfono si se llena.
// - M-4: la casilla "El socio autorizó el tratamiento de datos" envía `data_consent: true`; el
//   cliente nunca envía `data_consent_at`. M-5: no hay campo de notas.
// - Errores del api bajo su campo (422, incluido L-3: un documento que se normaliza a vacío);
//   409 con "Ver socio existente" a /socios/{existing_id} (S2-D34); 429 con la espera.
// - 201: vuelve a /socios con "Socio registrado" y, si falta la autorización, lo avisa.
// - Nada del formulario se guarda en localStorage ni en sessionStorage.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { setViewportWidth, type RecordedCall } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { apiError, EXISTING_MEMBER_ID, memberDetail, renderMembers } from "../../../test/members";

type Harness = ReturnType<typeof renderMembers>;

const nombres = () => screen.getByRole("textbox", { name: /^Nombres/ });
const apellidos = () => screen.getByRole("textbox", { name: /^Apellidos/ });
const documento = () => screen.getByRole("textbox", { name: /^Número de documento/ });
const telefono = () => screen.getByRole("textbox", { name: /^Teléfono \(WhatsApp\)/ });
const correo = () => screen.getByRole("textbox", { name: /^Correo/ });
const fecha = () => screen.getByLabelText(/^Fecha de nacimiento/);
const contactoNombre = () => screen.getByRole("textbox", { name: /^Nombre del contacto/ });
const contactoTelefono = () => screen.getByRole("textbox", { name: /^Teléfono del contacto/ });
const parentesco = () => screen.getByRole("textbox", { name: /^Parentesco/ });
const autorizacion = () => screen.getByRole("checkbox", { name: "El socio autorizó el tratamiento de datos" });
const guardar = () => screen.getByRole("button", { name: "Guardar" });

/** El texto de error asociado a un control por aria-describedby. */
function errorOf(control: HTMLElement): string {
  const ids = control.getAttribute("aria-describedby")?.split(" ") ?? [];
  return ids
    .map((id) => document.getElementById(id))
    .filter((node): node is HTMLElement => node !== null && node.id.endsWith("-error"))
    .map((node) => node.textContent)
    .join(" ");
}

async function fillRequired(user: Harness["user"], document = "1020304417"): Promise<void> {
  await user.type(nombres(), "Laura");
  await user.type(apellidos(), "Gómez");
  await user.type(documento(), document);
}

const posts = (mock: Harness["mock"]): RecordedCall[] => mock.callsTo("POST /members");

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

describe("MemberFormPage · estructura (Socio_Form.html)", () => {
  it("muestra las migas, el título y las cuatro secciones del formulario", () => {
    renderMembers("/socios/nuevo");

    expect(screen.getByRole("heading", { level: 1, name: "Nuevo socio" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Socios" })).toHaveAttribute("href", "/socios");
    for (const legend of ["1 · Identificación", "2 · Contacto", "3 · Contacto de emergencia", "4 · Autorización de datos (Ley 1581)"]) {
      expect(screen.getByRole("group", { name: legend })).toBeInTheDocument();
    }
    expect(nombres()).toHaveAttribute("aria-required", "true");
    expect(apellidos()).toHaveAttribute("aria-required", "true");
    expect(documento()).toHaveAttribute("aria-required", "true");
    expect(telefono()).toHaveAttribute("type", "tel");
    expect(correo()).toHaveAttribute("type", "email");
    expect(fecha()).toHaveAttribute("type", "date");
    expect(contactoNombre()).toBeInTheDocument();
    expect(contactoTelefono()).toBeInTheDocument();
    expect(parentesco()).toBeInTheDocument();
  });

  it("el tipo de documento ofrece CC, CE, TI y Pasaporte, con CC por defecto", () => {
    renderMembers("/socios/nuevo");

    const select = screen.getByRole("combobox", { name: /^Tipo de documento/ });
    expect(within(select).getAllByRole("option").map((o) => [o.getAttribute("value"), o.textContent])).toEqual([
      ["CC", "CC"],
      ["CE", "CE"],
      ["TI", "TI"],
      ["PA", "Pasaporte"],
    ]);
    expect(select).toHaveValue("CC");
  });

  it("el sexo es opcional: Sin indicar, Femenino, Masculino u Otro", () => {
    renderMembers("/socios/nuevo");

    const select = screen.getByRole("combobox", { name: /^Sexo/ });
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Sin indicar", "Femenino", "Masculino", "Otro"]);
    expect(select).toHaveValue("");
  });

  it("la casilla de autorización empieza sin marcar (M-4) y no hay campo de notas (M-5)", () => {
    renderMembers("/socios/nuevo");

    expect(autorizacion()).not.toBeChecked();
    expect(screen.queryByRole("textbox", { name: /Notas|Observaciones/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/No escribas datos sensibles en Notas/)).not.toBeInTheDocument();
  });

  it("Cancelar vuelve a la lista y Guardar envía el formulario", () => {
    renderMembers("/socios/nuevo");

    expect(screen.getByRole("link", { name: "Cancelar" })).toHaveAttribute("href", "/socios");
    expect(guardar()).toHaveAttribute("type", "submit");
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderMembers("/socios/nuevo");

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("MemberFormPage · validación en el cliente", () => {
  it("vacío: marca nombres, apellidos y documento, lleva el foco al primero y no llama al api", async () => {
    const { mock, user } = renderMembers("/socios/nuevo");

    await user.click(guardar());

    await waitFor(() => {
      expect(errorOf(nombres())).toBe("Escribe el nombre del socio.");
    });
    expect(errorOf(apellidos())).toBe("Escribe el apellido del socio.");
    expect(errorOf(documento())).toBe("Escribe el número de documento.");
    expect(nombres()).toHaveAttribute("aria-invalid", "true");
    expect(nombres()).toHaveFocus();
    expect(posts(mock)).toHaveLength(0);
  });

  it("espacios en blanco no cuentan como nombre", async () => {
    const { user } = renderMembers("/socios/nuevo");

    await user.type(nombres(), "   ");
    await user.click(guardar());

    await waitFor(() => {
      expect(errorOf(nombres())).toBe("Escribe el nombre del socio.");
    });
  });

  it.each([
    ["12", "corto"],
    ["1".repeat(31), "largo"],
  ])("un documento %s (%s) pide entre 3 y 30 caracteres", async (value) => {
    const { mock, user } = renderMembers("/socios/nuevo");

    await fillRequired(user, value);
    await user.click(guardar());

    await waitFor(() => {
      expect(errorOf(documento())).toBe("El documento debe tener entre 3 y 30 caracteres.");
    });
    expect(posts(mock)).toHaveLength(0);
  });

  it("una fecha de nacimiento futura se rechaza", async () => {
    const { mock, user } = renderMembers("/socios/nuevo");

    await fillRequired(user);
    fireEvent.change(fecha(), { target: { value: "2999-01-01" } });
    await user.click(guardar());

    await waitFor(() => {
      expect(errorOf(fecha())).toBe("La fecha de nacimiento no puede ser futura.");
    });
    expect(posts(mock)).toHaveLength(0);
  });

  it("un correo sin forma de correo se rechaza", async () => {
    const { mock, user } = renderMembers("/socios/nuevo");

    await fillRequired(user);
    await user.type(correo(), "laura@");
    await user.click(guardar());

    await waitFor(() => {
      expect(errorOf(correo())).toBe("Escribe un correo válido, por ejemplo ana@correo.com.");
    });
    expect(posts(mock)).toHaveLength(0);
  });

  it("un teléfono con menos de 7 dígitos se rechaza", async () => {
    const { mock, user } = renderMembers("/socios/nuevo");

    await fillRequired(user);
    await user.type(telefono(), "300-12");
    await user.click(guardar());

    await waitFor(() => {
      expect(errorOf(telefono())).toBe("El teléfono debe tener al menos 7 dígitos.");
    });
    expect(posts(mock)).toHaveLength(0);
  });

  it("el contacto de emergencia pide nombre y teléfono cuando se llena una parte", async () => {
    const { mock, user } = renderMembers("/socios/nuevo");

    await fillRequired(user);
    await user.type(parentesco(), "Madre");
    await user.click(guardar());

    await waitFor(() => {
      expect(errorOf(contactoNombre())).toBe("Escribe el nombre del contacto de emergencia.");
    });
    expect(errorOf(contactoTelefono())).toBe("Escribe el teléfono del contacto de emergencia.");
    expect(posts(mock)).toHaveLength(0);
  });
});

describe("MemberFormPage · envío", () => {
  it("con todo lleno envía MemberCreate con data_consent: true, sin notas ni data_consent_at", async () => {
    const { mock, router, user } = renderMembers("/socios/nuevo");

    await fillRequired(user);
    await user.selectOptions(screen.getByRole("combobox", { name: /^Sexo/ }), "Femenino");
    await user.selectOptions(screen.getByRole("combobox", { name: /^Tipo de documento/ }), "CE");
    fireEvent.change(fecha(), { target: { value: "1991-04-17" } });
    await user.type(telefono(), " 300 123 4567 ");
    await user.type(correo(), "laura@correo.co");
    await user.type(contactoNombre(), "Marta Gómez");
    await user.type(contactoTelefono(), "3109876543");
    await user.type(parentesco(), "Madre");
    await user.click(autorizacion());
    await user.click(guardar());

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/socios");
    });
    expect(posts(mock)).toHaveLength(1);
    expect(posts(mock)[0]?.body).toEqual({
      first_name: "Laura",
      last_name: "Gómez",
      sex: "f",
      document_type: "CE",
      document: "1020304417",
      birth_date: "1991-04-17",
      phone: "300 123 4567",
      email: "laura@correo.co",
      emergency_contact: { name: "Marta Gómez", phone: "3109876543", relationship: "Madre" },
      data_consent: true,
    });
    expect(posts(mock)[0]?.body).not.toHaveProperty("notes");
    expect(posts(mock)[0]?.body).not.toHaveProperty("data_consent_at");
  });

  it("con lo mínimo omite los opcionales y envía data_consent: false", async () => {
    const { mock, user } = renderMembers("/socios/nuevo", { handlers: { "POST /members": memberDetail(["data_consent_missing"]) } });

    await fillRequired(user);
    await user.click(guardar());

    await waitFor(() => {
      expect(posts(mock)).toHaveLength(1);
    });
    expect(posts(mock)[0]?.body).toEqual({ first_name: "Laura", last_name: "Gómez", document_type: "CC", document: "1020304417", data_consent: false });
  });

  it("el 201 vuelve a /socios con el aviso 'Socio registrado'", async () => {
    const { router, user } = renderMembers("/socios/nuevo");

    await fillRequired(user);
    await user.click(autorizacion());
    await user.click(guardar());

    const notice = await screen.findByText(/Socio registrado/);
    expect(notice).toHaveTextContent("Socio registrado: Laura Gómez.");
    expect(router.state.location.pathname).toBe("/socios");
    expect(screen.queryByText(/Falta la autorización de tratamiento de datos/)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: /Socios/ })).toBeInTheDocument();
  });

  it("si la respuesta trae data_consent_missing, avisa que falta la autorización", async () => {
    const { user } = renderMembers("/socios/nuevo", { handlers: { "POST /members": memberDetail(["data_consent_missing"]) } });

    await fillRequired(user);
    await user.click(guardar());

    expect(await screen.findByText(/Falta la autorización de tratamiento de datos/)).toBeInTheDocument();
    expect(screen.getByText(/Socio registrado/)).toBeInTheDocument();
  });

  it("mientras guarda el botón dice 'Guardando…', queda deshabilitado y no envía dos veces", async () => {
    const { mock, user } = renderMembers("/socios/nuevo", { handlers: { "POST /members": () => new Promise(() => undefined) } });

    await fillRequired(user);
    await user.click(guardar());

    const busy = await screen.findByRole("button", { name: "Guardando…" });
    expect(busy).toBeDisabled();
    await user.click(busy);
    fireEvent.submit(busy.closest("form") as HTMLFormElement);
    await waitFor(() => {
      expect(posts(mock)).toHaveLength(1);
    });
  });
});

describe("MemberFormPage · errores del api", () => {
  it("L-3: un documento que el api normaliza a vacío ('...') queda bajo su campo con foco", async () => {
    const { user } = renderMembers("/socios/nuevo", { handlers: { "POST /members": apiError(422, "validation_error", { field: "document" }) } });

    await fillRequired(user, "...");
    await user.click(guardar());

    await waitFor(() => {
      expect(errorOf(documento())).toBe("El documento no tiene letras ni números válidos. Revísalo e intenta de nuevo.");
    });
    expect(documento()).toHaveFocus();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it.each([
    ["phone", telefono, "El teléfono no tiene suficientes dígitos. Revísalo e intenta de nuevo."],
    ["email", correo, "El servidor no aceptó este correo. Revísalo e intenta de nuevo."],
    ["birth_date", fecha, "La fecha de nacimiento no puede ser futura."],
    ["emergency_contact.phone", contactoTelefono, "Revisa este dato e intenta de nuevo."],
    ["emergency_contact", contactoNombre, "Revisa este dato e intenta de nuevo."],
    ["emergency_contact.relationship", parentesco, "Revisa este dato e intenta de nuevo."],
    ["sex", () => screen.getByRole("combobox", { name: /^Sexo/ }), "Elige una opción de la lista."],
    ["document_type", () => screen.getByRole("combobox", { name: /^Tipo de documento/ }), "Elige el tipo de documento."],
  ])("un 422 de %s queda bajo su campo", async (field, control, message) => {
    const { user } = renderMembers("/socios/nuevo", { handlers: { "POST /members": apiError(422, "validation_error", { field }) } });

    await fillRequired(user);
    await user.click(guardar());

    await waitFor(() => {
      expect(errorOf(control())).toBe(message);
    });
  });

  it("un 422 sin campo conocido se explica como error general", async () => {
    const { user } = renderMembers("/socios/nuevo", { handlers: { "POST /members": apiError(422, "validation_error", { field: "notes" }) } });

    await fillRequired(user);
    await user.click(guardar());

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos registrar el socio. Revisa los datos e intenta de nuevo.");
  });

  it("409: el documento duplicado enlaza al socio existente sin poner el documento en la URL", async () => {
    const { router, user } = renderMembers("/socios/nuevo", {
      handlers: { "POST /members": apiError(409, "member_document_duplicated", { field: "document", existing_id: EXISTING_MEMBER_ID }) },
    });

    await fillRequired(user);
    await user.click(guardar());

    await waitFor(() => {
      expect(errorOf(documento())).toContain("Ya existe un socio con este documento.");
    });
    const link = screen.getByRole("link", { name: "Ver socio existente" });
    expect(link).toHaveAttribute("href", `/socios/${EXISTING_MEMBER_ID}`);
    await user.click(link);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/socios/${EXISTING_MEMBER_ID}`);
    });
    expect(router.state.location.search).toBe("");
    expect(screen.getByRole("heading", { level: 1, name: "Ficha del socio" })).toBeInTheDocument();
  });

  it("409 sin existing_id: el error queda bajo el documento sin enlace", async () => {
    const { user } = renderMembers("/socios/nuevo", { handlers: { "POST /members": apiError(409, "member_document_duplicated", { field: "document" }) } });

    await fillRequired(user);
    await user.click(guardar());

    await waitFor(() => {
      expect(errorOf(documento())).toBe("Ya existe un socio con este documento.");
    });
    expect(screen.queryByRole("link", { name: "Ver socio existente" })).not.toBeInTheDocument();
  });

  it("429: dice cuánto esperar según Retry-After", async () => {
    const { user } = renderMembers("/socios/nuevo", { handlers: { "POST /members": apiError(429, "rate_limited", {}, { "Retry-After": "30" }) } });

    await fillRequired(user);
    await user.click(guardar());

    expect(await screen.findByRole("alert")).toHaveTextContent("Registraste muchos socios seguidos. Espera 30 segundos e intenta de nuevo.");
  });

  it("revisión M1: el aviso general recibe el foco para que se vea tras pulsar Guardar al final", async () => {
    const { user } = renderMembers("/socios/nuevo", { handlers: { "POST /members": apiError(500, "internal") } });

    await fillRequired(user);
    await user.click(guardar());

    const alert = await screen.findByRole("alert");
    await waitFor(() => {
      expect(alert).toHaveFocus();
    });
  });

  it("429 sin Retry-After pide esperar un momento", async () => {
    const { user } = renderMembers("/socios/nuevo", { handlers: { "POST /members": apiError(429, "rate_limited") } });

    await fillRequired(user);
    await user.click(guardar());

    expect(await screen.findByRole("alert")).toHaveTextContent("Registraste muchos socios seguidos. Espera un momento e intenta de nuevo.");
  });

  it.each([
    [403, "forbidden", "No tienes permiso para registrar socios. Si lo necesitas, pídeselo a un administrador."],
    [500, "internal", "No pudimos registrar el socio. Intenta de nuevo en un momento."],
    [400, "member_error", "No pudimos registrar el socio. Revisa los datos e intenta de nuevo."],
  ])("un %i se explica como error general y conserva lo escrito", async (status, code, message) => {
    const { router, user } = renderMembers("/socios/nuevo", { handlers: { "POST /members": apiError(status, code) } });

    await fillRequired(user);
    await user.click(guardar());

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(documento()).toHaveValue("1020304417");
    expect(router.state.location.pathname).toBe("/socios/nuevo");
  });

  it("sin conexión lo dice con el mensaje de red", async () => {
    const { user } = renderMembers("/socios/nuevo", { handlers: { "POST /members": () => Promise.reject(new TypeError("Failed to fetch")) } });

    await fillRequired(user);
    await user.click(guardar());

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos conectar con el servidor. Intenta de nuevo.");
  });

  it("un 201 con forma inesperada es un error, no un alta", async () => {
    const { router, user } = renderMembers("/socios/nuevo", { handlers: { "POST /members": { status: 201, body: { id: 7 } } } });

    await fillRequired(user);
    await user.click(guardar());

    expect(await screen.findByRole("alert")).toHaveTextContent("La respuesta del servidor no es válida. Recarga la página e intenta de nuevo.");
    expect(router.state.location.pathname).toBe("/socios/nuevo");
  });

  it("corregir y volver a guardar limpia el error general", async () => {
    let fail = true;
    const { user } = renderMembers("/socios/nuevo", { handlers: { "POST /members": () => (fail ? apiError(500, "internal") : memberDetail()) } });

    await fillRequired(user);
    await user.click(guardar());
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    fail = false;
    await user.click(guardar());

    expect(await screen.findByText(/Socio registrado/)).toBeInTheDocument();
  });
});

describe("MemberFormPage · privacidad", () => {
  it("nada del formulario queda en localStorage ni en sessionStorage", async () => {
    const { user } = renderMembers("/socios/nuevo", { handlers: { "POST /members": apiError(500, "internal") } });

    await fillRequired(user);
    await user.type(telefono(), "3001234567");
    await user.type(correo(), "laura@correo.co");
    await user.click(guardar());
    await screen.findByRole("alert");

    const stored = [localStorage, sessionStorage].flatMap((storage) =>
      Array.from({ length: storage.length }, (_, i) => {
        const key = storage.key(i) ?? "";
        return `${key}=${storage.getItem(key) ?? ""}`;
      }),
    );
    for (const value of ["1020304417", "3001234567", "laura@correo.co", "Laura", "Gómez"]) {
      expect(stored.join("\n")).not.toContain(value);
    }
  });
});

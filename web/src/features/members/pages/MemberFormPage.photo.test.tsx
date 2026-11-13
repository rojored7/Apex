// S6-F4 · US-148 y US-149 (front): foto y autorización en /socios/nuevo y /socios/:id/editar, en claro y oscuro.
// - Al crear: POST /members → subir la foto → subir el documento firmado (kind=consent). Cada fallo de
//   subida deja el socio creado, lo dice («El socio quedó creado sin foto») y conserva el id (enlaces a
//   la ficha y a la edición); no se repite el POST /members.
// - Al editar: la foto nueva reemplaza a la vigente; sin otros cambios no hay PATCH, solo la subida.
// - Un archivo inválido (tipo o más de 5 MB) avisa en el campo y no pierde lo escrito en el formulario.
// - El 422 de data_consent_at se muestra bajo la casilla de autorización.
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { axe } from "vitest-axe";
import { apiError as detailError, DETAIL_PATH, MEMBER_ID, memberDetailBody, ok } from "../../../test/memberDetail";
import { apiError, memberDetail, NEW_MEMBER_ID, renderMembers } from "../../../test/members";
import { renderMemberDetail } from "../../../test/memberDetail";
import { setViewportWidth, type RecordedCall } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";

const ATTACH = `/members/${NEW_MEMBER_ID}/attachments`;
const EDIT_ATTACH = `${DETAIL_PATH}/attachments`;
const EDIT = `/socios/${MEMBER_ID}/editar`;
const OK_UPLOAD = { status: 201, body: { id: "bbbb0001-0000-4000-8000-000000000001", kind: "photo", mime: "image/png", size_bytes: 1, sensitive: false } };

const fileOf = (type: string, size = 10, name = "archivo"): File => {
  const file = new File(["x"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
};

const kindOf = (call: RecordedCall): string | null => new URL(call.url, "http://apex.test").searchParams.get("kind");
const fotoInput = () => screen.getByLabelText(/^Foto del socio/);
const documentoInput = () => screen.getByLabelText(/^Documento firmado/);

async function fillRequired(user: ReturnType<typeof renderMembers>["user"]): Promise<void> {
  await user.type(screen.getByRole("textbox", { name: /^Nombres/ }), "Laura");
  await user.type(screen.getByRole("textbox", { name: /^Apellidos/ }), "Gómez");
  await user.type(screen.getByRole("textbox", { name: /^Número de documento/ }), "1020304417");
}

let created: string[];

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
  created = [];
  // vi.stubGlobal("URL"): vi.unstubAllGlobals() lo restaura. Se conserva la clase real (el mock del api y el
  // router hacen new URL) y se le suman los dos métodos de blob:.
  class StubURL extends URL {
    static override createObjectURL = vi.fn(() => {
      created.push("blob:p");
      return "blob:p";
    });
    static override revokeObjectURL = vi.fn();
  }
  vi.stubGlobal("URL", StubURL);
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

describe.each([
  ["claro", null],
  ["oscuro", "dark"],
] as const)("MemberFormPage · alta con foto y autorización (%s)", (_name, theme) => {
  beforeEach(() => {
    if (theme) document.documentElement.setAttribute("data-theme", theme);
  });

  it("muestra el campo de foto (opcional) y el del documento firmado, sin archivos elegidos", () => {
    renderMembers("/socios/nuevo");

    expect(fotoInput()).toHaveAttribute("type", "file");
    expect(documentoInput()).toHaveAttribute("type", "file");
    expect(screen.getByText("JPEG o PNG, hasta 5 MB.")).toBeInTheDocument();
  });

  it("sin archivos no sube nada y vuelve a la lista", async () => {
    const { mock, user, router } = renderMembers("/socios/nuevo", { handlers: { [`POST ${ATTACH}`]: OK_UPLOAD } });
    await fillRequired(user);

    await user.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/socios");
    });
    expect(mock.callsTo(`POST ${ATTACH}`)).toHaveLength(0);
  });

  it("guarda al socio y DESPUÉS sube la foto como kind=photo con el File crudo", async () => {
    const { mock, user } = renderMembers("/socios/nuevo", { handlers: { [`POST ${ATTACH}`]: OK_UPLOAD } });
    const foto = fileOf("image/png", 100, "foto.png");
    await fillRequired(user);
    fireEvent.change(fotoInput(), { target: { files: [foto] } });
    expect(await screen.findByRole("img", { name: "Vista previa de la foto" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => {
      expect(mock.callsTo(`POST ${ATTACH}`)).toHaveLength(1);
    });
    const upload = mock.callsTo(`POST ${ATTACH}`)[0] as RecordedCall;
    expect(upload.rawBody).toBe(foto);
    expect(kindOf(upload)).toBe("photo");
    expect(upload.headers.get("Content-Type")).toBe("image/png");
    const order = mock.calls.map((c) => `${c.method} ${c.path}`).filter((key) => key === "POST /members" || key === `POST ${ATTACH}`);
    expect(order).toEqual(["POST /members", `POST ${ATTACH}`]);
    // El cuerpo JSON del alta no lleva archivos.
    expect(JSON.stringify(mock.callsTo("POST /members")[0]?.body)).not.toMatch(/photo|consent_file/);
  });

  it("foto y documento firmado: primero kind=photo y luego kind=consent", async () => {
    const { mock, user } = renderMembers("/socios/nuevo", { handlers: { [`POST ${ATTACH}`]: OK_UPLOAD } });
    await fillRequired(user);
    fireEvent.change(fotoInput(), { target: { files: [fileOf("image/jpeg")] } });
    fireEvent.change(documentoInput(), { target: { files: [fileOf("application/pdf")] } });

    await user.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => {
      expect(mock.callsTo(`POST ${ATTACH}`)).toHaveLength(2);
    });
    expect(mock.callsTo(`POST ${ATTACH}`).map(kindOf)).toEqual(["photo", "consent"]);
  });

  it("si la foto no sube: «El socio quedó creado sin foto», conserva el id (enlaces) y no repite el alta", async () => {
    const { mock, user, router } = renderMembers("/socios/nuevo", { handlers: { [`POST ${ATTACH}`]: apiError(422, "unsupported_type") } });
    await fillRequired(user);
    fireEvent.change(fotoInput(), { target: { files: [fileOf("image/png")] } });

    await user.click(screen.getByRole("button", { name: "Guardar" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("El socio quedó creado sin foto. La foto debe ser JPEG o PNG. Elige otra imagen.");
    expect(screen.getByRole("link", { name: "Ir a la ficha" })).toHaveAttribute("href", `/socios/${NEW_MEMBER_ID}`);
    expect(screen.getByRole("link", { name: "Subir el archivo desde la edición" })).toHaveAttribute("href", `/socios/${NEW_MEMBER_ID}/editar`);
    expect(router.state.location.pathname).toBe("/socios/nuevo");
    expect(mock.callsTo("POST /members")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Guardar" })).not.toBeInTheDocument();
  });

  it("la foto falla pero el documento sí sube: avisa solo de la foto", async () => {
    let calls = 0;
    const { mock, user } = renderMembers("/socios/nuevo", {
      handlers: { [`POST ${ATTACH}`]: () => (++calls === 1 ? apiError(413, "file_too_large") : OK_UPLOAD) },
    });
    await fillRequired(user);
    fireEvent.change(fotoInput(), { target: { files: [fileOf("image/png")] } });
    fireEvent.change(documentoInput(), { target: { files: [fileOf("application/pdf")] } });

    await user.click(screen.getByRole("button", { name: "Guardar" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("El socio quedó creado sin foto.");
    expect(alert).not.toHaveTextContent("documento firmado");
    expect(mock.callsTo(`POST ${ATTACH}`)).toHaveLength(2);
  });

  it("un 503 de la subida muestra el mensaje del api", async () => {
    const { user } = renderMembers("/socios/nuevo", { handlers: { [`POST ${ATTACH}`]: apiError(503, "crypto_unavailable") } });
    await fillRequired(user);
    fireEvent.change(documentoInput(), { target: { files: [fileOf("application/pdf")] } });

    await user.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("El socio quedó creado sin el documento firmado. Mensaje del api.");
  });

  it("una foto de más de 5 MB avisa «La foto supera 5 MB» en el campo y NO pierde el formulario", async () => {
    const { mock, user } = renderMembers("/socios/nuevo");
    await fillRequired(user);

    fireEvent.change(fotoInput(), { target: { files: [fileOf("image/png", 5 * 1024 * 1024 + 1)] } });

    expect(await screen.findByText(/^La foto supera 5 MB/)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /^Nombres/ })).toHaveValue("Laura");
    expect(screen.getByRole("textbox", { name: /^Número de documento/ })).toHaveValue("1020304417");
    expect(mock.callsTo("POST /members")).toHaveLength(0);
  });

  it("el 422 de data_consent_at se muestra bajo la casilla de autorización y lleva el foco", async () => {
    const { user } = renderMembers("/socios/nuevo", { handlers: { "POST /members": apiError(422, "validation_error", { field: "data_consent_at" }) } });
    await fillRequired(user);

    await user.click(screen.getByRole("button", { name: "Guardar" }));

    const checkbox = screen.getByRole("checkbox", { name: "El socio autorizó el tratamiento de datos" });
    await waitFor(() => {
      expect(checkbox).toHaveAttribute("aria-invalid", "true");
    });
    expect(screen.getByText(/^Falta la autorización de datos/)).toBeInTheDocument();
    expect(checkbox).toHaveFocus();
  });

  it("al marcar la autorización muestra la fecha «ahora» y la versión de solo lectura, y no las envía", async () => {
    const { mock, user } = renderMembers("/socios/nuevo", {
      handlers: {
        "GET /settings/privacy": { status: 200, body: { key: "privacy", value: { policy_version: "2026-10", policy_text: null, retention_years: 5, consent_required_from: null }, version: 1, updated_at: null, updated_by: null } },
        "POST /members": memberDetail(),
      },
    });
    await fillRequired(user);

    await user.click(screen.getByRole("checkbox", { name: "El socio autorizó el tratamiento de datos" }));
    expect(await screen.findByDisplayValue("2026-10")).toHaveAttribute("readonly");
    expect(screen.getByLabelText("Fecha de aceptación")).toHaveAttribute("readonly");
    await user.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => {
      expect(mock.callsTo("POST /members")).toHaveLength(1);
    });
    const body = mock.callsTo("POST /members")[0]?.body as Record<string, unknown>;
    expect(body.data_consent).toBe(true);
    expect(Object.keys(body)).not.toContain("data_consent_at");
    expect(Object.keys(body)).not.toContain("data_consent_version");
  });

  it("no tiene violaciones de accesibilidad con los dos campos de archivo", async () => {
    const { container } = renderMembers("/socios/nuevo");
    fireEvent.change(fotoInput(), { target: { files: [fileOf("image/png")] } });

    expect(await axe(container)).toHaveNoViolations();
  });

  it("nada del archivo queda en localStorage ni sessionStorage", async () => {
    const { user, router } = renderMembers("/socios/nuevo", { handlers: { [`POST ${ATTACH}`]: OK_UPLOAD } });
    await fillRequired(user);
    fireEvent.change(fotoInput(), { target: { files: [fileOf("image/png")] } });
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/socios");
    });

    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});

describe.each([
  ["claro", null],
  ["oscuro", "dark"],
] as const)("MemberFormPage en edición · foto y documento (%s)", (_name, theme) => {
  beforeEach(() => {
    if (theme) document.documentElement.setAttribute("data-theme", theme);
  });

  async function openEdit(handlers: Parameters<typeof renderMemberDetail>[1] = {}) {
    const harness = renderMemberDetail(EDIT, handlers);
    await screen.findByRole("heading", { level: 1, name: "Editar socio" });
    return harness;
  }

  it("con foto vigente la muestra y avisa que la nueva la reemplaza", async () => {
    await openEdit({
      handlers: {
        [`GET ${DETAIL_PATH}`]: ok(memberDetailBody({ photo_attachment_id: "bbbb0001-0000-4000-8000-000000000001" })),
        "GET /attachments/bbbb0001-0000-4000-8000-000000000001": { status: 200, file: { content: "img", contentType: "image/png" } },
      },
    });

    expect(screen.getByText(/reemplaza a la foto actual/)).toBeInTheDocument();
  });

  it("reemplaza la foto: sin otros cambios no hay PATCH, solo POST kind=photo, y vuelve a la ficha", async () => {
    const { mock, user, router } = await openEdit({ handlers: { [`POST ${EDIT_ATTACH}`]: OK_UPLOAD } });
    const nueva = fileOf("image/jpeg", 50, "nueva.jpg");

    fireEvent.change(fotoInput(), { target: { files: [nueva] } });
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/socios/${MEMBER_ID}`);
    });
    expect(mock.callsTo(`PATCH ${DETAIL_PATH}`)).toHaveLength(0);
    const upload = mock.callsTo(`POST ${EDIT_ATTACH}`)[0] as RecordedCall;
    expect(upload.rawBody).toBe(nueva);
    expect(kindOf(upload)).toBe("photo");
    expect(screen.queryByText("No hay cambios para guardar.")).not.toBeInTheDocument();
  });

  it("cambios y foto: primero el PATCH y después la subida", async () => {
    const { mock, user } = await openEdit({
      handlers: { [`PATCH ${DETAIL_PATH}`]: ok(memberDetailBody({ first_name: "Laura Sofía" })), [`POST ${EDIT_ATTACH}`]: OK_UPLOAD },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /^Nombres/ }), { target: { value: "Laura Sofía" } });
    fireEvent.change(fotoInput(), { target: { files: [fileOf("image/png")] } });

    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => {
      expect(mock.callsTo(`POST ${EDIT_ATTACH}`)).toHaveLength(1);
    });
    const order = mock.calls.map((c) => `${c.method} ${c.path}`).filter((key) => key.startsWith("PATCH") || key.startsWith("POST"));
    expect(order).toEqual([`PATCH ${DETAIL_PATH}`, `POST ${EDIT_ATTACH}`]);
  });

  it("la autorización ya registrada se muestra como texto y aún permite subir el documento firmado (kind=consent)", async () => {
    const { mock, user } = await openEdit({ handlers: { [`POST ${EDIT_ATTACH}`]: OK_UPLOAD } });

    expect(screen.getByText(/^Autorización registrada el/)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    fireEvent.change(documentoInput(), { target: { files: [fileOf("application/pdf")] } });
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => {
      expect(mock.callsTo(`POST ${EDIT_ATTACH}`)).toHaveLength(1);
    });
    expect(kindOf(mock.callsTo(`POST ${EDIT_ATTACH}`)[0] as RecordedCall)).toBe("consent");
  });

  it("si la subida falla: «Los cambios se guardaron, pero la foto no se subió» y se queda en la pantalla", async () => {
    const { user, router } = await openEdit({ handlers: { [`POST ${EDIT_ATTACH}`]: detailError(413, "file_too_large") } });
    fireEvent.change(fotoInput(), { target: { files: [fileOf("image/png")] } });

    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Los cambios se guardaron, pero la foto no se subió. La foto supera 5 MB. Elige una de menos de 5 MB.");
    expect(screen.getByRole("link", { name: "Ir a la ficha" })).toHaveAttribute("href", `/socios/${MEMBER_ID}`);
    expect(router.state.location.pathname).toBe(EDIT);
  });

  it("PATCH ok y subida fallida: el segundo «Guardar» NO repite el PATCH y sí reintenta la subida", async () => {
    let attempts = 0;
    const { mock, user } = await openEdit({
      handlers: {
        [`PATCH ${DETAIL_PATH}`]: ok(memberDetailBody({ first_name: "Laura Sofía" })),
        [`POST ${EDIT_ATTACH}`]: () => (++attempts === 1 ? detailError(503, "crypto_unavailable") : OK_UPLOAD),
      },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /^Nombres/ }), { target: { value: "Laura Sofía" } });
    fireEvent.change(fotoInput(), { target: { files: [fileOf("image/png")] } });

    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => {
      expect(mock.callsTo(`POST ${EDIT_ATTACH}`)).toHaveLength(2);
    });
    expect(mock.callsTo(`PATCH ${DETAIL_PATH}`)).toHaveLength(1);
  });

  it("el 422 de data_consent_at del PATCH se muestra bajo la casilla (autorización pendiente)", async () => {
    const { user } = await openEdit({
      handlers: {
        [`GET ${DETAIL_PATH}`]: ok(memberDetailBody({ data_consent_at: null, data_consent_version: null, warnings: ["data_consent_missing"] })),
        [`PATCH ${DETAIL_PATH}`]: detailError(422, "validation_error", { field: "data_consent_at" }),
      },
    });

    await user.click(screen.getByRole("checkbox", { name: "Registrar autorización" }));
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(await screen.findByText(/^Falta la autorización de datos/)).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = await openEdit();

    expect(await axe(container)).toHaveNoViolations();
  });
});

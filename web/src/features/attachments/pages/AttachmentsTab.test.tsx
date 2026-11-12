// S6-F3 · US-150 (front): pestaña Adjuntos de la ficha (/socios/:id/adjuntos), hija de /socios/:id
// (S3-D65) con GET /members/{id}/attachments.
// - Tabla con tipo, fecha de Bogotá, tamaño legible (KB y MB con coma decimal), quién subió (el nombre
//   si el contrato lo trae, el id corto si no) y "Descargar".
// - "Descargar" baja el archivo con api.blob y lo entrega con un enlace `a[download]` (nunca
//   window.open ni blob: en una pestaña; L-2). El PDF no se abre.
// - Con rol coach no aparece "Descargar" en `consent` ni `other` (M-6); si el api igual responde 403,
//   el mensaje se muestra.
// - Estados: carga, vacío con camino siguiente, error con Reintentar, 404, 403, 429; paginación por offset.
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { ATTACHMENTS_PATH, attachment, attachments, attachmentsReply, CONSENT_ID, fileReply, MEMBER_ID, OTHER_ID, PHOTO_ID, renderAttachmentsTab } from "../../../test/attachments";
import { DELETED_TAB_MEMBER, listCallsTo } from "../../../test/memberTabs";
import { signInAs, signOutForTests } from "../../../test/session";
import { ATTACHMENT_MESSAGES, ATTACHMENTS_EMPTY, ATTACHMENTS_LOADING } from "./AttachmentsTab";

const apiError = (status: number, code: string, message = "x", headers?: Record<string, string>) => ({
  status,
  body: { error: { code, message } },
  ...(headers ? { headers } : {}),
});

const clicks: { download: string; href: string }[] = [];

beforeEach(() => {
  clicks.length = 0;
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:apex/adjunto"), revokeObjectURL: vi.fn() }));
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    clicks.push({ download: this.download, href: this.href });
  });
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const table = (): Promise<HTMLElement> => screen.findByRole("table", { name: "Adjuntos del socio" });
const rows = (): HTMLElement[] => within(screen.getByRole("table", { name: "Adjuntos del socio" })).getAllByRole("row").slice(1);
const downloadButton = (name: RegExp): HTMLElement => screen.getByRole("button", { name });

describe("AttachmentsTab · tabla", () => {
  it("pide la primera página de 25 y pinta tipo, fecha de Bogotá, tamaño y quién subió en el orden del api", async () => {
    const { mock } = renderAttachmentsTab();
    await table();

    expect(within(screen.getByRole("table")).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Tipo", "Fecha", "Tamaño", "Subido por", "Acción"]);
    const [params] = listCallsTo(mock, ATTACHMENTS_PATH);
    expect(params?.get("limit")).toBe("25");
    expect(params?.get("offset")).toBe("0");
    const [other, consent, photo] = rows();
    expect(other).toHaveTextContent("Otro documento");
    expect(other).toHaveTextContent("1 oct 2026, 10:00 a. m.");
    expect(other).toHaveTextContent("5 MB");
    expect(consent).toHaveTextContent("Autorización de datos");
    expect(consent).toHaveTextContent("12 mar 2026, 11:00 a. m.");
    expect(consent).toHaveTextContent("1,5 MB");
    expect(photo).toHaveTextContent("Foto de perfil");
    expect(photo).toHaveTextContent("220 KB");
    expect(photo).toHaveTextContent("Usuario a0a0a0a0");
  });

  it("marca como cifrados los adjuntos sensibles y no la foto", async () => {
    renderAttachmentsTab();
    await table();
    const [other, consent, photo] = rows();

    expect(other).toHaveTextContent("Cifrado");
    expect(consent).toHaveTextContent("Cifrado");
    expect(photo).not.toHaveTextContent("Cifrado");
  });

  it("si el contrato trae el nombre de quien subió, lo muestra en lugar del id corto", async () => {
    const named = { ...attachment(), uploaded_by_name: "ana" };
    renderAttachmentsTab({ handlers: { [`GET ${ATTACHMENTS_PATH}`]: attachmentsReply([named]) } });
    await table();

    expect(rows()[0]).toHaveTextContent("ana");
    expect(rows()[0]).not.toHaveTextContent("a0a0a0a0");
  });

  it("pagina por offset en el servidor", async () => {
    const { mock, user } = renderAttachmentsTab({ handlers: { [`GET ${ATTACHMENTS_PATH}`]: attachmentsReply(attachments(), 60) } });
    await table();
    await user.click(screen.getByRole("button", { name: /Siguiente/ }));

    await waitFor(() => {
      expect(listCallsTo(mock, ATTACHMENTS_PATH).some((p) => p.get("offset") === "25")).toBe(true);
    });
    expect(screen.getByTestId("location").textContent).toContain("offset=25");
  });
});

describe("AttachmentsTab · descarga", () => {
  it("'Descargar' baja el PDF con api.blob y lo entrega con a[download] sin abrirlo (L-2)", async () => {
    const open = vi.spyOn(window, "open");
    const { mock, user } = renderAttachmentsTab({ handlers: { [`GET /attachments/${CONSENT_ID}`]: fileReply(CONSENT_ID, "application/pdf", "pdf", "%PDF-1.4") } });
    await table();
    await user.click(downloadButton(/^Descargar Autorización de datos/));

    await waitFor(() => {
      expect(clicks).toHaveLength(1);
    });
    expect(mock.callsTo(`GET /attachments/${CONSENT_ID}`)).toHaveLength(1);
    expect(clicks[0]).toEqual({ download: "adjunto-bbbb0002.pdf", href: "blob:apex/adjunto" });
    expect(open).not.toHaveBeenCalled();
    expect(document.querySelector("a[target]")).toBeNull();
    expect(document.querySelector('a[href^="blob:"]')).toBeNull();
  });

  it("descarga también la foto (JPEG) con su nombre del api", async () => {
    const { user } = renderAttachmentsTab({ handlers: { [`GET /attachments/${PHOTO_ID}`]: fileReply(PHOTO_ID, "image/jpeg", "jpg") } });
    await table();
    await user.click(downloadButton(/^Descargar Foto de perfil/));

    await waitFor(() => {
      expect(clicks[0]?.download).toBe("adjunto-bbbb0001.jpg");
    });
  });

  it("mientras baja, el botón queda ocupado y se libera al terminar", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const { user } = renderAttachmentsTab({
      handlers: {
        [`GET /attachments/${OTHER_ID}`]: async () => {
          await gate;
          return { status: 200, file: { content: "x", contentType: "application/pdf", filename: "adjunto-bbbb0003.pdf" } };
        },
      },
    });
    await table();
    await user.click(downloadButton(/^Descargar Otro documento/));

    await waitFor(() => {
      expect(downloadButton(/^Descargar Otro documento/)).toBeDisabled();
    });
    expect(screen.getByText("Preparando la descarga…")).toBeInTheDocument();
    await act(async () => {
      release();
      await gate;
    });
    await waitFor(() => {
      expect(downloadButton(/^Descargar Otro documento/)).toBeEnabled();
    });
  });

  it.each([
    [403, "forbidden", ATTACHMENT_MESSAGES.forbidden],
    [404, "not_found", ATTACHMENT_MESSAGES.notFound],
    [429, "rate_limited", "Hiciste muchas descargas seguidas. Espera 30 segundos e intenta de nuevo."],
    [500, "internal", "No pudimos preparar la descarga. Intenta de nuevo en un momento."],
  ])("un %s al descargar dice qué pasó y qué hacer", async (status, code, message) => {
    const headers = status === 429 ? { "Retry-After": "30" } : undefined;
    const { user } = renderAttachmentsTab({ handlers: { [`GET /attachments/${CONSENT_ID}`]: apiError(status, code, "x", headers) } });
    await table();
    await user.click(downloadButton(/^Descargar Autorización de datos/));

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(clicks).toHaveLength(0);
  });

  it("un 503 crypto_unavailable muestra el mensaje del api", async () => {
    const { user } = renderAttachmentsTab({
      handlers: { [`GET /attachments/${CONSENT_ID}`]: apiError(503, "crypto_unavailable", "El custodio de llaves no está disponible. Intenta en unos minutos.", { "Retry-After": "30" }) },
    });
    await table();
    await user.click(downloadButton(/^Descargar Autorización de datos/));

    expect(await screen.findByText("El custodio de llaves no está disponible. Intenta en unos minutos.")).toBeInTheDocument();
  });

  it("no guarda nada en localStorage ni sessionStorage", async () => {
    const { user } = renderAttachmentsTab({ handlers: { [`GET /attachments/${CONSENT_ID}`]: fileReply(CONSENT_ID, "application/pdf", "pdf") } });
    await table();
    await user.click(downloadButton(/^Descargar Autorización de datos/));
    await waitFor(() => {
      expect(clicks).toHaveLength(1);
    });

    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});

describe("AttachmentsTab · rol coach (M-6)", () => {
  beforeEach(() => {
    signOutForTests();
    signInAs("coach");
  });

  it("solo ve 'Descargar' en la foto; en la autorización y en otro documento dice 'Solo administradores'", async () => {
    renderAttachmentsTab();
    await table();
    const [other, consent, photo] = rows();

    expect(within(photo as HTMLElement).getByRole("button", { name: /^Descargar Foto de perfil/ })).toBeInTheDocument();
    for (const row of [other, consent]) {
      expect(within(row as HTMLElement).queryByRole("button", { name: /Descargar/ })).not.toBeInTheDocument();
      expect(row).toHaveTextContent("Solo administradores");
    }
  });
});

describe("AttachmentsTab · estados", () => {
  it("mientras llega la lista dice 'Cargando los adjuntos…'", () => {
    renderAttachmentsTab({ handlers: { [`GET ${ATTACHMENTS_PATH}`]: () => new Promise(() => undefined) } });

    expect(screen.getByRole("status")).toHaveTextContent(ATTACHMENTS_LOADING);
  });

  it("vacío dice 'Este socio no tiene adjuntos' y ofrece Editar socio", async () => {
    renderAttachmentsTab({ handlers: { [`GET ${ATTACHMENTS_PATH}`]: attachmentsReply([]) } });

    expect(await screen.findByText(ATTACHMENTS_EMPTY)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Editar socio" })).toHaveAttribute("href", `/socios/${MEMBER_ID}/editar`);
  });

  it("vacío en un socio dado de baja no ofrece Editar socio", async () => {
    renderAttachmentsTab({ member: DELETED_TAB_MEMBER, handlers: { [`GET ${ATTACHMENTS_PATH}`]: attachmentsReply([]) } });

    expect(await screen.findByText(ATTACHMENTS_EMPTY)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Editar socio" })).not.toBeInTheDocument();
  });

  it("un error del servidor se explica y 'Reintentar' vuelve a pedir la lista", async () => {
    let calls = 0;
    const { mock, user } = renderAttachmentsTab({
      handlers: {
        [`GET ${ATTACHMENTS_PATH}`]: (call) => {
          calls += 1;
          return calls === 1 ? apiError(500, "internal") : attachmentsReply(attachments())(call);
        },
      },
    });

    expect(await screen.findByText(ATTACHMENT_MESSAGES.listFailed)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    await table();
    expect(mock.callsTo(`GET ${ATTACHMENTS_PATH}`)).toHaveLength(2);
  });

  it.each([
    [404, "not_found", ATTACHMENT_MESSAGES.memberNotFound],
    [403, "forbidden", ATTACHMENT_MESSAGES.listForbidden],
  ])("un %s al listar dice qué pasó y qué hacer", async (status, code, message) => {
    renderAttachmentsTab({ handlers: { [`GET ${ATTACHMENTS_PATH}`]: apiError(status, code) } });

    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it("un 429 al listar pide esperar", async () => {
    renderAttachmentsTab({ handlers: { [`GET ${ATTACHMENTS_PATH}`]: apiError(429, "rate_limited", "x", { "Retry-After": "20" }) } });

    expect(await screen.findByText(/Espera 20 segundos/)).toBeInTheDocument();
  });
});

describe("AttachmentsTab · diseño", () => {
  it.each([
    ["claro", null],
    ["oscuro", "dark"],
  ])("sin violaciones de accesibilidad en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    const { container } = renderAttachmentsTab();
    await table();

    expect(await axe(container)).toHaveNoViolations();
    delete document.documentElement.dataset.theme;
  });
});

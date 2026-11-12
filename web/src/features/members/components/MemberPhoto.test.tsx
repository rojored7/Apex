// S6-F3 · US-148 (front): miniatura de la foto del socio en el encabezado de la ficha y en la lista.
// - Con `photo_attachment_id`: <img> con alt fijo ("Foto del socio", nunca el nombre) y un blob: en
//   memoria (useMemberPhoto).
// - Sin foto, cargando o con error: un marcador decorativo (aria-hidden), sin <img> ni petición.
// - Dos tamaños: sm (lista) y lg (encabezado). Claro y oscuro con axe; solo tokens.
import { readFileSync } from "node:fs";
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { axe } from "vitest-axe";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { MemberPhoto, PHOTO_ALT, type MemberPhotoProps } from "./MemberPhoto";

const SOURCES = [readFileSync("src/features/members/components/MemberPhoto.tsx", "utf8"), readFileSync("src/features/members/components/MemberPhoto.module.css", "utf8")].join(" ");
const PHOTO_ID = "bbbb0001-0000-4000-8000-000000000001";
const jpeg: MockHandler = { status: 200, file: { content: "jpeg", contentType: "image/jpeg", filename: "adjunto-bbbb0001.jpg" } };

function renderPhoto(props: MemberPhotoProps, handlers: Record<string, MockHandler> = { [`GET /attachments/${PHOTO_ID}`]: jpeg }) {
  const mock = mockApi(handlers);
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <MemberPhoto {...props} />
    </QueryClientProvider>,
  );
  return { mock, ...view };
}

beforeEach(() => {
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:apex/foto"), revokeObjectURL: vi.fn() }));
});

afterEach(() => {
  cleanup();
  delete document.documentElement.dataset.theme;
  vi.unstubAllGlobals();
});

describe("MemberPhoto", () => {
  it("con foto pinta la imagen con el alt fijo y el blob: en memoria", async () => {
    renderPhoto({ photoAttachmentId: PHOTO_ID, size: "lg" });

    const image = await screen.findByRole("img", { name: PHOTO_ALT });
    expect(image).toHaveAttribute("src", "blob:apex/foto");
    expect(PHOTO_ALT).toBe("Foto del socio");
  });

  it("sin foto muestra el marcador y no pide nada", () => {
    const { mock } = renderPhoto({ photoAttachmentId: null, size: "sm" });

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByTestId("member-photo-placeholder")).toHaveAttribute("aria-hidden", "true");
    expect(mock.calls).toHaveLength(0);
  });

  it("mientras baja la foto muestra el marcador", () => {
    renderPhoto({ photoAttachmentId: PHOTO_ID, size: "sm" }, { [`GET /attachments/${PHOTO_ID}`]: () => new Promise(() => undefined) });

    expect(screen.getByTestId("member-photo-placeholder")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("si la foto falla (404) vuelve al marcador y no rompe la pantalla", async () => {
    const { mock } = renderPhoto({ photoAttachmentId: PHOTO_ID, size: "sm" }, { [`GET /attachments/${PHOTO_ID}`]: { status: 404, body: { error: { code: "not_found", message: "x" } } } });

    await waitFor(() => {
      expect(mock.callsTo(`GET /attachments/${PHOTO_ID}`)).toHaveLength(1);
    });
    expect(screen.getByTestId("member-photo-placeholder")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("el tamaño llega como atributo para el CSS", () => {
    renderPhoto({ photoAttachmentId: null, size: "lg" });

    expect(screen.getByTestId("member-photo")).toHaveAttribute("data-size", "lg");
  });

  it.each([
    ["claro", null],
    ["oscuro", "dark"],
  ])("sin violaciones de accesibilidad en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    const { container } = renderPhoto({ photoAttachmentId: PHOTO_ID, size: "lg" });
    await screen.findByRole("img", { name: PHOTO_ALT });

    expect(await axe(container)).toHaveNoViolations();
  });

  it("el CSS solo usa tokens: ni colores ni fuentes literales", () => {
    expect(SOURCES).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(SOURCES).not.toMatch(/\brgba?\(/);
    expect(SOURCES).not.toMatch(/font-family\s*:\s*(?!var\()/);
  });
});

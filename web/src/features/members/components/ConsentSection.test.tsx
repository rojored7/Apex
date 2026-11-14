// S6-F4 · US-149 (front): la sección «4 · Autorización de datos» del formulario del socio.
// - La casilla existente (nunca marcada de entrada); con ella marcada, la fecha de aceptación «ahora
//   en Bogotá» (solo lectura) y la versión vigente (solo lectura) de GET /settings/privacy o
//   «versión no registrada»; ninguna de las dos se envía: las fija el servidor.
// - Archivo opcional del documento firmado (PDF, JPEG o PNG, 5 MB) que el formulario sube como
//   kind=consent tras guardar. El error del campo (por ejemplo el 422 de data_consent_at) se muestra
//   bajo la casilla.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { axe } from "vitest-axe";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { ConsentSection, type ConsentSectionProps } from "./ConsentSection";

const privacy = (policy_version: string | null): MockHandler => ({
  status: 200,
  body: { key: "privacy", value: { policy_version, policy_text: null, retention_years: 5, consent_required_from: null }, version: 1, updated_at: null, updated_by: null },
});

const fileOf = (type: string, size = 10, name = "firmado"): File => {
  const file = new File(["x"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
};

function Harness({ onFile, extra }: { onFile: (file: File | null) => void; extra: Partial<ConsentSectionProps> }) {
  const { register, control } = useForm({ defaultValues: { data_consent: false } });
  const [file, setFile] = useState<File | null>(null);
  return (
    <ConsentSection
      checkbox={register("data_consent")}
      accepted={useWatch({ control, name: "data_consent" })}
      registeredText={null}
      checkboxLabel="El socio autorizó el tratamiento de datos"
      checkboxHint="Márcala solo si el socio leyó y aceptó la política."
      file={file}
      onFileChange={(next) => {
        setFile(next);
        onFile(next);
      }}
      {...extra}
    />
  );
}

function setup(handlers: Record<string, MockHandler> = { "GET /settings/privacy": privacy("2026-10") }, extra: Partial<ConsentSectionProps> = {}) {
  const mock = mockApi(handlers);
  const onFile = vi.fn<(file: File | null) => void>();
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <Harness onFile={onFile} extra={extra} />
    </QueryClientProvider>,
  );
  return { mock, onFile, user: userEvent.setup(), ...view };
}

const checkbox = () => screen.getByRole("checkbox", { name: "El socio autorizó el tratamiento de datos" });
const fileInput = () => screen.getByLabelText(/^Documento firmado/);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-22T03:30:00Z")); // 21 oct 2026, 10:30 p. m. en Bogotá
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-theme");
});

describe("ConsentSection", () => {
  it("es un grupo «4 · Autorización de datos (Ley 1581)» con la casilla sin marcar y su ayuda", () => {
    setup();

    const group = screen.getByRole("group", { name: "4 · Autorización de datos (Ley 1581)" });
    expect(within(group).getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByText(/Márcala solo si el socio leyó/)).toBeInTheDocument();
  });

  it("sin marcar no pide la política al api; al marcar sí, y con la autorización ya registrada nunca", async () => {
    const first = setup();
    expect(first.mock.callsTo("GET /settings/privacy")).toHaveLength(0);
    fireEvent.click(checkbox());
    await screen.findByDisplayValue("2026-10");
    expect(first.mock.callsTo("GET /settings/privacy")).toHaveLength(1);
    cleanup();

    const registered = setup(undefined, { registeredText: "Autorización registrada" });
    expect(registered.mock.callsTo("GET /settings/privacy")).toHaveLength(0);
  });

  it("sin marcar no muestra fecha ni versión", () => {
    setup();

    expect(screen.queryByLabelText("Fecha de aceptación")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Versión de la política")).not.toBeInTheDocument();
  });

  it("al marcar muestra la fecha de aceptación «ahora» en hora de Bogotá, de solo lectura", () => {
    setup();

    fireEvent.click(checkbox());

    const date = screen.getByLabelText("Fecha de aceptación");
    expect(date).toHaveValue("21 oct 2026, 10:30 p. m.");
    expect(date).toHaveAttribute("readonly");
  });

  it("la fecha queda fija mientras siga marcada y se toma de nuevo al volver a marcar (revisión V11, LOW 6)", () => {
    setup();

    fireEvent.click(checkbox());
    vi.setSystemTime(new Date("2026-10-22T04:00:00Z"));
    expect(screen.getByLabelText("Fecha de aceptación")).toHaveValue("21 oct 2026, 10:30 p. m.");

    fireEvent.click(checkbox());
    fireEvent.click(checkbox());
    expect(screen.getByLabelText("Fecha de aceptación")).toHaveValue("21 oct 2026, 11:00 p. m.");
  });

  it("un archivo rechazado se borra del control (revisión V11, LOW 10)", () => {
    setup();
    const writes: string[] = [];
    Object.defineProperty(fileInput(), "value", {
      configurable: true,
      get: () => "",
      set: (next: string) => {
        writes.push(next);
      },
    });

    fireEvent.change(fileInput(), { target: { files: [fileOf("image/gif")] } });

    expect(writes).toEqual([""]);
  });

  it("muestra la versión vigente de la política de solo lectura", async () => {
    setup();

    fireEvent.click(checkbox());

    const version = await screen.findByDisplayValue("2026-10");
    expect(version).toHaveAttribute("readonly");
    expect(screen.getByLabelText("Versión de la política")).toBe(version);
  });

  it("sin política publicada dice «versión no registrada»", async () => {
    setup({ "GET /settings/privacy": privacy(null) });

    fireEvent.click(checkbox());

    expect(await screen.findByDisplayValue("versión no registrada")).toBeInTheDocument();
  });

  it("si la versión no se puede leer (por ejemplo, coach) lo dice sin romper", async () => {
    setup({ "GET /settings/privacy": { status: 403, body: { error: { code: "forbidden", message: "x" } } } });

    fireEvent.click(checkbox());

    expect(await screen.findByDisplayValue("Se registra la versión vigente al guardar")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("con la autorización ya registrada muestra su texto y no la casilla", () => {
    setup({ "GET /settings/privacy": privacy("2026-10") }, { registeredText: "Autorización registrada el 12 mar 2026 · versión 2026-03" });

    expect(screen.getByText("Autorización registrada el 12 mar 2026 · versión 2026-03")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(fileInput()).toBeInTheDocument();
  });

  it("el archivo del documento firmado es opcional y ofrece PDF, JPEG y PNG", () => {
    setup();

    expect(fileInput()).toHaveAttribute("type", "file");
    expect(fileInput()).toHaveAttribute("accept", "application/pdf,image/jpeg,image/png");
    expect(screen.getByText(/PDF, JPEG o PNG, hasta 5 MB\. Se sube al guardar/)).toBeInTheDocument();
  });

  it("un PDF válido se entrega al formulario", () => {
    const { onFile } = setup();
    const pdf = fileOf("application/pdf");

    fireEvent.change(fileInput(), { target: { files: [pdf] } });

    expect(onFile).toHaveBeenLastCalledWith(pdf);
  });

  it("un archivo de más de 5 MB o de otro tipo se rechaza con su aviso y no se entrega", () => {
    const { onFile } = setup();

    fireEvent.change(fileInput(), { target: { files: [fileOf("application/pdf", 5 * 1024 * 1024 + 1)] } });
    expect(screen.getByText("El documento supera 5 MB. Elige uno de menos de 5 MB.")).toBeInTheDocument();
    expect(onFile).toHaveBeenLastCalledWith(null);

    fireEvent.change(fileInput(), { target: { files: [fileOf("application/zip")] } });
    expect(screen.getByText("El documento debe ser PDF, JPEG o PNG. Elige otro archivo.")).toBeInTheDocument();
  });

  it("muestra bajo la casilla el error del campo data_consent (el 422 de data_consent_at)", () => {
    setup(undefined, { checkboxError: "Falta la autorización de datos. Márcala o pide al administrador que revise la política." });

    const error = screen.getByText(/^Falta la autorización de datos/);
    expect(checkbox()).toHaveAttribute("aria-invalid", "true");
    expect(checkbox().getAttribute("aria-describedby")).toContain(error.id);
  });

  it("«Quitar documento» devuelve el archivo a null", async () => {
    const { onFile, user } = setup();
    fireEvent.change(fileInput(), { target: { files: [fileOf("application/pdf")] } });

    vi.useRealTimers();
    await user.click(screen.getByRole("button", { name: "Quitar documento" }));

    expect(onFile).toHaveBeenLastCalledWith(null);
  });

  it.each([null, "dark"])("no tiene violaciones de accesibilidad (tema %s)", async (theme) => {
    vi.useRealTimers();
    if (theme) document.documentElement.setAttribute("data-theme", theme);
    const { container } = setup();
    fireEvent.click(checkbox());
    await screen.findByDisplayValue("2026-10");

    expect(await axe(container)).toHaveNoViolations();
  });
});

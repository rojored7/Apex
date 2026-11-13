// S6-F4 · US-148 (front): el campo de foto del formulario del socio.
// - DESIGN-GAP: Socio_Form.html no trae el campo de foto; se agrega arriba de "1 · Identificación"
//   con el control de archivo estándar y la vista previa circular de la ficha.
// - Vista previa en memoria (blob: revocado al cambiar y al desmontar); valida tipo (JPEG, PNG) y
//   5 MB exactos en el cliente con el mensaje de la pantalla y SIN perder el resto del formulario:
//   un archivo inválido no se entrega al formulario (onChange(null)); el control queda usable.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { mockApi, testQueryClient } from "../../../test/server";
import { PhotoField, type PhotoFieldProps } from "./PhotoField";

const OK = 5 * 1024 * 1024;
const fileOf = (type: string, size = 10, name = "foto"): File => {
  const file = new File(["x"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
};

let created: string[];
let revoked: string[];

beforeEach(() => {
  created = [];
  revoked = [];
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => {
      const url = `blob:preview-${String(created.length + 1)}`;
      created.push(url);
      return url;
    }),
    revokeObjectURL: vi.fn((url: string) => {
      revoked.push(url);
    }),
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-theme");
});

function setup(props: Partial<PhotoFieldProps> = {}) {
  const onChange = vi.fn<(file: File | null) => void>();
  mockApi({});
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <PhotoField value={null} onChange={onChange} {...props} />
    </QueryClientProvider>,
  );
  return { onChange, user: userEvent.setup(), ...view };
}

const input = (): HTMLInputElement => screen.getByLabelText(/^Foto del socio/);

describe("PhotoField", () => {
  it("tiene etiqueta, es opcional y solo ofrece JPEG y PNG", () => {
    setup();

    expect(input()).toHaveAttribute("type", "file");
    expect(input()).toHaveAttribute("accept", "image/jpeg,image/png");
    expect(input()).not.toHaveAttribute("aria-required");
    expect(screen.getByText(/JPEG o PNG, hasta 5 MB/)).toBeInTheDocument();
  });

  it("sin foto muestra el marcador y ninguna vista previa", () => {
    setup();

    expect(screen.getByTestId("photo-field-placeholder")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Vista previa de la foto" })).not.toBeInTheDocument();
  });

  it("al elegir una foto válida la entrega al formulario", async () => {
    const { onChange, user } = setup();
    const file = fileOf("image/png", OK);

    await user.upload(input(), file);

    expect(onChange).toHaveBeenCalledWith(file);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("con una foto en el valor muestra la vista previa en memoria y la revoca al desmontar", () => {
    const { unmount } = setup({ value: fileOf("image/jpeg") });

    expect(screen.getByRole("img", { name: "Vista previa de la foto" })).toHaveAttribute("src", "blob:preview-1");
    unmount();
    expect(revoked).toContain("blob:preview-1");
  });

  it("al cambiar de foto revoca la vista previa anterior", () => {
    const { rerender } = setup({ value: fileOf("image/jpeg", 10, "a") });
    rerender(
      <QueryClientProvider client={testQueryClient()}>
        <PhotoField value={fileOf("image/png", 10, "b")} onChange={vi.fn()} />
      </QueryClientProvider>,
    );

    expect(revoked).toContain("blob:preview-1");
    expect(screen.getByRole("img", { name: "Vista previa de la foto" })).toHaveAttribute("src", "blob:preview-2");
  });

  it("5.242.881 bytes: avisa «La foto supera 5 MB», no entrega el archivo y deja el control usable", async () => {
    const { onChange } = setup();

    fireEvent.change(input(), { target: { files: [fileOf("image/png", OK + 1)] } });

    expect(await screen.findByText(/^La foto supera 5 MB/)).toBeInTheDocument();
    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(input()).toHaveAttribute("aria-invalid", "true");
    expect(input()).toBeEnabled();
  });

  it("5.242.880 bytes pasa", () => {
    const { onChange } = setup();
    const file = fileOf("image/jpeg", OK);

    fireEvent.change(input(), { target: { files: [file] } });

    expect(onChange).toHaveBeenLastCalledWith(file);
  });

  it.each(["application/pdf", "image/gif", "image/webp"])("un %s se rechaza pidiendo JPEG o PNG", (type) => {
    const { onChange } = setup();

    fireEvent.change(input(), { target: { files: [fileOf(type)] } });

    expect(screen.getByText("La foto debe ser JPEG o PNG. Elige otra imagen.")).toBeInTheDocument();
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("elegir una foto válida después de una inválida limpia el aviso", () => {
    const { onChange } = setup();

    fireEvent.change(input(), { target: { files: [fileOf("image/gif")] } });
    fireEvent.change(input(), { target: { files: [fileOf("image/png")] } });

    expect(screen.queryByText(/JPEG o PNG\. Elige/)).not.toBeInTheDocument();
    expect(onChange).toHaveBeenCalledTimes(2);
  });

  it("muestra el error que viene del formulario (por ejemplo el de Zod al guardar)", () => {
    setup({ error: "La foto debe ser JPEG o PNG. Elige otra imagen." });

    expect(screen.getByText("La foto debe ser JPEG o PNG. Elige otra imagen.")).toBeInTheDocument();
  });

  it("«Quitar foto» aparece con una foto elegida y la devuelve a null", async () => {
    const { onChange, user } = setup({ value: fileOf("image/png") });

    await user.click(screen.getByRole("button", { name: "Quitar foto" }));

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("al editar, sin foto nueva, muestra la foto vigente y avisa que la nueva la reemplaza", () => {
    setup({ currentPhotoId: "bbbb0001-0000-4000-8000-000000000001" });

    expect(screen.getByTestId("member-photo")).toBeInTheDocument();
    expect(screen.getByText(/reemplaza a la foto actual/)).toBeInTheDocument();
  });

  it("no guarda nada en localStorage ni sessionStorage", async () => {
    const { user } = setup();
    await user.upload(input(), fileOf("image/png"));

    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it.each([null, "dark"])("no tiene violaciones de accesibilidad (tema %s)", async (theme) => {
    if (theme) document.documentElement.setAttribute("data-theme", theme);
    const { container } = setup({ value: fileOf("image/png") });

    expect(await axe(container)).toHaveNoViolations();
  });
});

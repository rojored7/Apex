import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { axe } from "vitest-axe";
import { Field } from "./Field";

describe("Field", () => {
  it("asocia la etiqueta con el control", () => {
    render(<Field label="Documento" name="document" />);
    const input = screen.getByLabelText("Documento");

    expect(input.tagName).toBe("INPUT");
    expect(input).toHaveAttribute("name", "document");
    expect(input).toHaveAttribute("aria-invalid", "false");
    expect(input).toHaveClass("control", "md");
  });

  it("enlaza la ayuda por aria-describedby", () => {
    render(<Field label="Documento" name="document" hint="Sin puntos ni espacios" />);
    const input = screen.getByLabelText("Documento");
    const hint = screen.getByText("Sin puntos ni espacios");

    expect(input).toHaveAttribute("aria-describedby", hint.id);
  });

  it("con error marca aria-invalid y apunta al mensaje", () => {
    render(<Field label="Documento" name="document" hint="Sin puntos" error="Ya existe un socio con este documento." />);
    const input = screen.getByLabelText("Documento");
    const message = screen.getByText("Ya existe un socio con este documento.");
    const hint = screen.getByText("Sin puntos");

    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input.getAttribute("aria-describedby")?.split(" ")).toEqual([hint.id, message.id]);
    expect(input).toHaveClass("invalid");
  });

  it("errorAction con ruta interna renderiza un enlace", () => {
    render(
      <Field
        label="Documento"
        name="document"
        error="Ya existe un socio con este documento."
        errorAction={{ href: "/socios/123", text: "Ver socio" }}
      />,
    );

    expect(screen.getByRole("link", { name: "Ver socio" })).toHaveAttribute("href", "/socios/123");
  });

  it("S2-F4a: con onNavigate el clic navega dentro de la SPA en lugar de recargar", async () => {
    const onNavigate = vi.fn();
    render(<Field label="Correo" name="email" error="Ya existe." errorAction={{ href: "/sistema/usuarios?usuario=1", text: "Ver", onNavigate }} />);
    const link = screen.getByRole("link", { name: "Ver" });
    const click = new MouseEvent("click", { bubbles: true, cancelable: true });

    link.dispatchEvent(click);

    expect(click.defaultPrevented).toBe(true);
    expect(onNavigate).toHaveBeenCalledWith("/sistema/usuarios?usuario=1");
    await userEvent.setup().click(link);
    expect(onNavigate).toHaveBeenCalledTimes(2);
  });

  it("sin onNavigate el clic sigue el enlace normal", () => {
    render(<Field label="Correo" name="email" error="Ya existe." errorAction={{ href: "/x", text: "Ver" }} />);
    const click = new MouseEvent("click", { bubbles: true, cancelable: true });

    screen.getByRole("link", { name: "Ver" }).dispatchEvent(click);

    expect(click.defaultPrevented).toBe(false);
  });

  it.each(["https://malo.example/x", "//malo.example/x", "javascript:alert(1)", "/\\malo.example"])(
    "errorAction con %s no renderiza enlace",
    (href) => {
      render(<Field label="Documento" name="document" error="Duplicado." errorAction={{ href, text: "Ver socio" }} />);

      expect(screen.queryByRole("link")).not.toBeInTheDocument();
      expect(screen.getByText("Duplicado.")).toBeInTheDocument();
    },
  );

  it("errorAction sin error no se muestra", () => {
    render(<Field label="Documento" name="document" errorAction={{ href: "/socios/1", text: "Ver socio" }} />);

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("required muestra la marca y pone aria-required", () => {
    render(<Field label="Nombre" name="first_name" required />);
    const input = screen.getByLabelText(/Nombre/);

    expect(input).toHaveAttribute("aria-required", "true");
    expect(screen.getByText("*")).toHaveAttribute("aria-hidden", "true");
  });

  it("tamaño lg aplica la clase del control de gimnasio", () => {
    render(<Field label="Buscar" name="q" size="lg" />);

    expect(screen.getByLabelText("Buscar")).toHaveClass("control", "lg");
  });

  it("acepta un control propio por children con los atributos de accesibilidad", () => {
    render(
      <Field label="Plan" name="plan" error="Elige un plan.">
        {(control) => (
          <select {...control}>
            <option value="">Elige</option>
          </select>
        )}
      </Field>,
    );
    const select = screen.getByLabelText("Plan");

    expect(select.tagName).toBe("SELECT");
    expect(select).toHaveAttribute("name", "plan");
    expect(select).toHaveAttribute("aria-invalid", "true");
    expect(select).toHaveAttribute("aria-describedby", screen.getByText("Elige un plan.").id);
  });

  it("se integra con register de react-hook-form", async () => {
    const onSubmit = vi.fn();
    function Form() {
      const { register, handleSubmit } = useForm<{ document: string }>({ defaultValues: { document: "" } });
      return (
        <form
          onSubmit={(event) => {
            void handleSubmit((values) => {
              onSubmit(values);
            })(event);
          }}
        >
          <Field label="Documento" {...register("document")} />
          <button type="submit">Guardar</button>
        </form>
      );
    }
    render(<Form />);

    await userEvent.type(screen.getByLabelText("Documento"), "1020304050");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(onSubmit).toHaveBeenCalledWith({ document: "1020304050" });
  });

  it("recibe el foco con el teclado", async () => {
    render(<Field label="Documento" name="document" />);

    await userEvent.tab();

    expect(screen.getByLabelText("Documento")).toHaveFocus();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = render(
      <form>
        <Field label="Documento" name="document" hint="Sin puntos" required />
        <Field label="Correo" name="email" error="Escribe un correo válido." errorAction={{ href: "/socios/1", text: "Ver socio" }} />
      </form>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { Button, type ButtonSize, type ButtonVariant } from "./Button";

describe("Button", () => {
  it.each<ButtonVariant>(["primary", "secondary", "danger", "ghost"])("renderiza la variante %s", (variant) => {
    render(<Button variant={variant}>Guardar</Button>);

    expect(screen.getByRole("button", { name: "Guardar" })).toHaveClass("button", variant);
  });

  it.each<ButtonSize>(["md", "lg"])("renderiza el tamaño %s", (size) => {
    render(<Button size={size}>Guardar</Button>);

    expect(screen.getByRole("button", { name: "Guardar" })).toHaveClass(size);
  });

  it("es primary, md y type=button por defecto", () => {
    render(<Button>Guardar</Button>);
    const button = screen.getByRole("button", { name: "Guardar" });

    expect(button).toHaveAttribute("type", "button");
    expect(button).toHaveClass("primary", "md");
    expect(button).not.toHaveAttribute("aria-busy");
  });

  it("respeta type=submit y una clase adicional", () => {
    render(
      <Button type="submit" className="extra">
        Enviar
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Enviar" });

    expect(button).toHaveAttribute("type", "submit");
    expect(button).toHaveClass("button", "extra");
  });

  it("llama onClick al hacer clic", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Guardar</Button>);

    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("con loading marca aria-busy, se deshabilita y no llama onClick", async () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Guardar
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Guardar" });

    await userEvent.click(button);

    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toBeDisabled();
    expect(button).toHaveClass("loading");
    expect(onClick).not.toHaveBeenCalled();
  });

  it("deshabilitado no llama onClick", async () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Guardar
      </Button>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(onClick).not.toHaveBeenCalled();
  });

  it("recibe el foco con el teclado", async () => {
    render(<Button>Guardar</Button>);

    await userEvent.tab();

    expect(screen.getByRole("button", { name: "Guardar" })).toHaveFocus();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = render(
      <div>
        <Button>Guardar</Button>
        <Button variant="danger" loading>
          Anular
        </Button>
      </div>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});

// S2-F2: página de mensaje con un único h1, el texto y un enlace de salida opcional.
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { MessagePage } from "./MessagePage";

describe("MessagePage", () => {
  it("pinta título, mensaje y enlace", () => {
    render(
      <MemoryRouter>
        <MessagePage title="Sin permiso" message="Pídele acceso a un administrador." linkLabel="Ir al inicio" linkTo="/" />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Sin permiso" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Sin permiso" })).toBeInTheDocument();
    expect(screen.getByText("Pídele acceso a un administrador.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir al inicio" })).toHaveAttribute("href", "/");
  });

  it("H1 (revisión del Sprint 2): con alert el mensaje se anuncia y children pone la acción", () => {
    render(
      <MemoryRouter>
        <MessagePage title="Algo salió mal" message="No pudimos abrir esta pantalla." alert>
          <button type="button">Recargar</button>
        </MessagePage>
      </MemoryRouter>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("No pudimos abrir esta pantalla.");
    expect(screen.getByRole("button", { name: "Recargar" })).toBeInTheDocument();
  });

  it("sin alert el mensaje no es una alerta", () => {
    render(
      <MemoryRouter>
        <MessagePage title="No encontrada" message="Revisa el enlace." />
      </MemoryRouter>,
    );

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("sin enlace no pinta ninguno", () => {
    render(
      <MemoryRouter>
        <MessagePage title="Sin permiso" message="Vuelve más tarde." />
      </MemoryRouter>,
    );

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("es accesible", async () => {
    const { container } = render(
      <MemoryRouter>
        <MessagePage title="No encontrada" message="La dirección no existe." linkLabel="Ir al inicio" linkTo="/" />
      </MemoryRouter>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});

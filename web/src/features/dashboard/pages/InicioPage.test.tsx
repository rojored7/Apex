// S2-D25: Inicio mínima hasta GET /dashboard (Sprint 3): saludo con el correo y accesos a
// Socios y, para admin, Planes, Usuarios y Configuración.
import { screen, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { renderWithProviders } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import InicioPage from "./InicioPage";

afterEach(() => {
  signOutForTests();
});

describe("InicioPage", () => {
  it("saluda con el correo y da al admin los accesos del Sprint 2", () => {
    signInAs("admin");
    renderWithProviders(<InicioPage />, { role: "admin" });

    expect(screen.getByRole("heading", { level: 1, name: "Hola, admin@apex.test" })).toBeInTheDocument();
    const accesos = screen.getByRole("navigation", { name: "Accesos rápidos" });
    expect(within(accesos).getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      ["Socios", "/socios"],
      ["Planes", "/planes"],
      ["Usuarios y roles", "/sistema/usuarios"],
      ["Configuración", "/sistema/configuracion"],
    ]);
  });

  it("el coach solo ve Socios", () => {
    signInAs("coach");
    renderWithProviders(<InicioPage />, { role: "coach" });

    const accesos = screen.getByRole("navigation", { name: "Accesos rápidos" });
    expect(within(accesos).getAllByRole("link").map((a) => a.textContent)).toEqual(["Socios"]);
  });

  it("explica que el tablero llega después", () => {
    signInAs("coach");
    renderWithProviders(<InicioPage />, { role: "coach" });

    expect(screen.getByText(/El tablero con socios al día, vencimientos e ingresos llega en la próxima versión\./)).toBeInTheDocument();
  });

  it("es accesible", async () => {
    signInAs("admin");
    const { container } = renderWithProviders(<InicioPage />, { role: "admin" });

    expect(await axe(container)).toHaveNoViolations();
  });
});

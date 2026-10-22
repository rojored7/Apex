// US-067 T5, US-053 T5 y S2-F2: páginas de respaldo con un único h1, un camino de salida
// según el rol y sin violaciones de axe.
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { RoleProvider, type Role } from "../core/auth";
import { NoPermissionPage } from "../core/auth/NoPermissionPage";
import { NotFound } from "./NotFound";
import { PendingPage } from "./PendingPage";
import { RouteLoading } from "./RouteLoading";

function withRole(role: Role | null, ui: ReactElement) {
  return render(
    <RoleProvider value={role}>
      <MemoryRouter>{ui}</MemoryRouter>
    </RoleProvider>,
  );
}

describe("NotFound", () => {
  it.each<[Role | null, string]>([
    ["admin", "/"],
    ["coach", "/"],
    ["member", "/mi"],
    [null, "/login"],
  ])("con %s enlaza a %s", (role, href) => {
    withRole(role, <NotFound />);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "No encontrada" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir al inicio" })).toHaveAttribute("href", href);
  });

  it("es accesible", async () => {
    const { container } = withRole("coach", <NotFound />);
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("NoPermissionPage", () => {
  it("dice Sin permiso con un enlace al inicio del rol", () => {
    withRole("coach", <NoPermissionPage />);

    expect(screen.getByRole("heading", { level: 1, name: "Sin permiso" })).toBeInTheDocument();
    expect(screen.getByText("Tu rol no tiene acceso a esta pantalla. Si la necesitas, pídesela a un administrador.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir al inicio" })).toHaveAttribute("href", "/");
  });

  it("es accesible", async () => {
    const { container } = withRole("coach", <NoPermissionPage />);
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("RouteLoading", () => {
  it("anuncia la carga con role=status", () => {
    render(<RouteLoading />);

    expect(screen.getByRole("status")).toHaveTextContent("Cargando…");
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
  });
});

describe("PendingPage", () => {
  it("muestra el título de la pantalla y que llega pronto", () => {
    withRole("admin", <PendingPage title="Socios" />);

    expect(screen.getByRole("heading", { level: 1, name: "Socios" })).toBeInTheDocument();
    expect(screen.getByText("Esta pantalla estará disponible pronto.")).toBeInTheDocument();
  });

  it("es accesible", async () => {
    const { container } = withRole("admin", <PendingPage title="Planes" />);
    expect(await axe(container)).toHaveNoViolations();
  });
});

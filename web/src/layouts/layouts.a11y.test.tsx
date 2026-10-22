// US-061 y US-062 (criterio 6): axe sin violaciones en los cuatro layouts con contenido de
// ejemplo. El contraste lo verifica Playwright con estilos reales (kit.spec.ts); jsdom no
// calcula colores, así que aquí se desactiva solo esa regla.
import { render } from "@testing-library/react";
import { axe } from "vitest-axe";
import { MemoryRouter } from "react-router";
import { FEATURES } from "../config/features";
import { setViewportWidth } from "../test/server";
import { GymLayout } from "./GymLayout";
import { buildNavItems } from "./nav";
import { PanelLayout } from "./PanelLayout";
import { PortalLayout } from "./PortalLayout";
import { TvLayout } from "./TvLayout";

const OPTIONS = { rules: { "color-contrast": { enabled: false } } };

afterEach(() => {
  delete document.documentElement.dataset.theme;
  vi.unstubAllGlobals();
});

describe("layouts accesibles", () => {
  it("PanelLayout en escritorio", async () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/socios"]}>
        <PanelLayout
          user={{ email: "ana@apex.test", roleLabel: "Admin" }}
          gymName="Box Norte"
          navGroups={buildNavItems("admin", new Set(FEATURES))}
          onLogout={vi.fn()}
          onChangePassword={vi.fn()}
        >
          <h1>Socios</h1>
        </PanelLayout>
      </MemoryRouter>,
    );

    expect(await axe(container, OPTIONS)).toHaveNoViolations();
  });

  it("PanelLayout en celular", async () => {
    setViewportWidth(390);
    const { container } = render(
      <MemoryRouter>
        <PanelLayout user={{ email: "ana@apex.test", roleLabel: "Coach" }} navGroups={buildNavItems("coach", new Set(FEATURES))}>
          <h1>Inicio</h1>
        </PanelLayout>
      </MemoryRouter>,
    );

    expect(await axe(container, OPTIONS)).toHaveNoViolations();
  });

  it("PortalLayout", async () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/mi"]}>
        <PortalLayout gymName="Box Norte">
          <h1>Hola, Laura</h1>
        </PortalLayout>
      </MemoryRouter>,
    );

    expect(await axe(container, OPTIONS)).toHaveNoViolations();
  });

  it("GymLayout", async () => {
    const { container } = render(
      <MemoryRouter>
        <GymLayout title="Check-in" exitTo="/clases">
          <button type="button">Llegó</button>
        </GymLayout>
      </MemoryRouter>,
    );

    expect(await axe(container, OPTIONS)).toHaveNoViolations();
  });

  it("TvLayout", async () => {
    const { container } = render(
      <TvLayout>
        <h1>Helen</h1>
      </TvLayout>,
    );

    expect(await axe(container, OPTIONS)).toHaveNoViolations();
  });
});

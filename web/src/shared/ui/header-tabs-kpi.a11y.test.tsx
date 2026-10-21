// US-064 T5: axe sobre PageHeader, Tabs y KpiCard en sus estados.
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { KpiCard } from "./KpiCard";
import { PageHeader } from "./PageHeader";
import { Tabs } from "./Tabs";

function inRouter(ui: ReactElement) {
  return render(
    <MemoryRouter>
      <main>{ui}</main>
    </MemoryRouter>,
  );
}

describe("accesibilidad de encabezado, pestañas y KPI", () => {
  it("PageHeader con migas, total y menú abierto", async () => {
    const { container, getByRole } = inRouter(
      <PageHeader
        title="Laura Gómez"
        total="Socia desde 2026"
        breadcrumbs={[{ label: "Socios", href: "/socios" }, { label: "Laura Gómez" }]}
        actions={[
          { id: "a", label: "Renovar", variant: "primary", href: "/x" },
          { id: "b", label: "Registrar pago", onClick: () => undefined },
          { id: "c", label: "Editar", href: "/y" },
          { id: "d", label: "Dar de baja", tone: "danger", onClick: () => undefined },
        ]}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();

    await userEvent.click(getByRole("button", { name: "Más acciones" }));
    expect(await axe(container)).toHaveNoViolations();
  });

  it("Tabs con una pestaña no disponible", async () => {
    const { container } = inRouter(
      <Tabs
        label="Secciones"
        tabs={[
          { id: "datos", label: "Datos" },
          { id: "asistencia", label: "Asistencia", disabledUntil: "v0.4" },
          { id: "historial", label: "Historial" },
        ]}
      >
        {(active) => <p>{active}</p>}
      </Tabs>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it.each([
    ["con valor y enlace", <KpiCard key="a" label="Por vencer" value={12} kind="count" href="/m" note="3 hoy" attention />],
    ["sin valor", <KpiCard key="b" label="Por avisar" value={null} kind="count" availableIn="v0.2" />],
    ["cargando", <KpiCard key="c" label="Ingresos" value={0} kind="money" isLoading />],
    ["con error", <KpiCard key="d" label="Ingresos" value={null} kind="money" error onRetry={() => undefined} />],
  ])("KpiCard %s", async (_estado, card) => {
    const { container } = inRouter(card);

    expect(await axe(container)).toHaveNoViolations();
  });
});

// US-064 T2 y T4: pestañas accesibles con la pestaña activa en la URL.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { Tabs, type TabItem } from "./Tabs";

const TABS: TabItem[] = [
  { id: "datos", label: "Datos" },
  { id: "membresias", label: "Membresías" },
  { id: "pagos", label: "Pagos" },
  { id: "asistencia", label: "Asistencia", disabledUntil: "v0.4" },
  { id: "historial", label: "Historial" },
];

function Location() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

function renderQuery(initial = "/socios/1") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Tabs label="Secciones del socio" tabs={TABS}>
        {(active) => <p>{`Panel ${active}`}</p>}
      </Tabs>
      <Location />
    </MemoryRouter>,
  );
}

describe("Tabs", () => {
  it("usa tablist, tab y tabpanel enlazados", () => {
    renderQuery();

    expect(screen.getByRole("tablist", { name: "Secciones del socio" })).toBeInTheDocument();
    const datos = screen.getByRole("tab", { name: "Datos" });
    expect(datos).toHaveAttribute("aria-selected", "true");
    expect(datos).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tab", { name: "Pagos" })).toHaveAttribute("tabindex", "-1");
    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveAttribute("aria-labelledby", datos.id);
    expect(datos).toHaveAttribute("aria-controls", panel.id);
    expect(panel).toHaveTextContent("Panel datos");
  });

  it("lee la pestaña activa de ?tab= al cargar (sobrevive a recargar)", () => {
    renderQuery("/socios/1?tab=pagos&q=x");

    expect(screen.getByRole("tab", { name: "Pagos" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Panel pagos");
  });

  it("flecha derecha desde Membresías activa Pagos y la URL lo refleja, conservando otros parámetros", async () => {
    const user = userEvent.setup();
    renderQuery("/socios/1?tab=membresias&q=x");

    await user.click(screen.getByRole("tab", { name: "Membresías" }));
    await user.keyboard("{ArrowRight}");

    const pagos = screen.getByRole("tab", { name: "Pagos" });
    expect(pagos).toHaveFocus();
    expect(pagos).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("location")).toHaveTextContent("/socios/1?tab=pagos&q=x");
  });

  it("las flechas saltan la pestaña no disponible y dan la vuelta", async () => {
    const user = userEvent.setup();
    renderQuery("/socios/1?tab=pagos");

    await user.click(screen.getByRole("tab", { name: "Pagos" }));
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Historial" })).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Datos" })).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("tab", { name: "Historial" })).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("tab", { name: "Pagos" })).toHaveFocus();
  });

  it("Inicio y Fin van a la primera y a la última disponibles", async () => {
    const user = userEvent.setup();
    renderQuery("/socios/1?tab=pagos");

    await user.click(screen.getByRole("tab", { name: "Pagos" }));
    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Historial" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: "Datos" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Enter}");
    expect(screen.getByRole("tab", { name: "Datos" })).toHaveAttribute("aria-selected", "true");
  });

  it("una pestaña no disponible anuncia su versión, se ve deshabilitada y no cambia la activa", async () => {
    const user = userEvent.setup();
    renderQuery();
    const asistencia = screen.getByRole("tab", { name: /Asistencia/ });

    expect(asistencia).toHaveAttribute("aria-disabled", "true");
    expect(asistencia).toHaveTextContent("Disponible en v0.4");
    await user.click(asistencia);

    expect(asistencia).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("tab", { name: "Datos" })).toHaveAttribute("aria-selected", "true");
  });

  it("una pestaña desconocida o no disponible en la URL cae en la primera disponible", () => {
    renderQuery("/socios/1?tab=asistencia");
    expect(screen.getByRole("tab", { name: "Datos" })).toHaveAttribute("aria-selected", "true");
  });

  it("en modo segmento la pestaña activa es el último segmento de la ruta", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/config/notificaciones"]}>
        <Routes>
          <Route
            path="/config/*"
            element={
              <Tabs
                label="Configuración"
                urlMode="segment"
                basePath="/config"
                tabs={[
                  { id: "general", label: "General" },
                  { id: "notificaciones", label: "Notificaciones" },
                ]}
              >
                {(active) => <p>{active}</p>}
              </Tabs>
            }
          />
        </Routes>
        <Location />
      </MemoryRouter>,
    );

    expect(screen.getByRole("tab", { name: "Notificaciones" })).toHaveAttribute("aria-selected", "true");
    await user.click(screen.getByRole("tab", { name: "General" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/config/general");
    expect(screen.getByRole("tab", { name: "General" })).toHaveAttribute("aria-selected", "true");
  });
});

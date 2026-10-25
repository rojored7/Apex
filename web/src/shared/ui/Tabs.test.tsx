// US-064 T2 y T4: pestañas accesibles con la pestaña activa en la URL.
// S3-F1 (E14): en modo segmento, `indexId` es la pestaña que vive en la ruta base (hija índice).
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

  it("cambiar de pestaña vuelve a la primera página de su lista", async () => {
    const user = userEvent.setup();
    renderQuery("/socios/1?tab=pagos&offset=50");

    await user.click(screen.getByRole("tab", { name: "Membresías" }));

    expect(screen.getByTestId("location")).toHaveTextContent("/socios/1?tab=membresias");
    expect(screen.getByTestId("location")).not.toHaveTextContent("offset");
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

  // S3-F1 (E14): la pestaña índice vive en la ruta del padre (la hija índice "Datos" de la ficha).
  function renderIndexTabs(initial: string) {
    return render(
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route
            path="/socios/:id/*"
            element={
              <Tabs
                label="Secciones del socio"
                urlMode="segment"
                basePath="/socios/1"
                indexId="datos"
                tabs={[
                  { id: "datos", label: "Datos" },
                  { id: "membresias", label: "Membresías" },
                  { id: "historial", label: "Historial", disabledUntil: "v0.1" },
                ]}
              >
                {(active) => <p>{`Panel ${active}`}</p>}
              </Tabs>
            }
          />
        </Routes>
        <Location />
      </MemoryRouter>,
    );
  }

  it("en modo segmento con indexId, la ruta base activa la pestaña índice y pulsarla vuelve a la base sin segmento", async () => {
    const user = userEvent.setup();
    renderIndexTabs("/socios/1/membresias?x=1");

    expect(screen.getByRole("tab", { name: "Membresías" })).toHaveAttribute("aria-selected", "true");
    await user.click(screen.getByRole("tab", { name: "Datos" }));

    expect(screen.getByTestId("location").textContent).toBe("/socios/1?x=1");
    expect(screen.getByRole("tab", { name: "Datos" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Panel datos");
  });

  it("con indexId y la ruta base, la índice es la activa aunque no sea la primera de la lista", () => {
    render(
      <MemoryRouter initialEntries={["/socios/1"]}>
        <Tabs
          label="Secciones"
          urlMode="segment"
          basePath="/socios/1"
          indexId="datos"
          tabs={[
            { id: "resumen", label: "Resumen" },
            { id: "datos", label: "Datos" },
          ]}
        >
          {(active) => <p>{`Panel ${active}`}</p>}
        </Tabs>
      </MemoryRouter>,
    );

    expect(screen.getByRole("tab", { name: "Datos" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Panel datos");
  });

  it("con indexId, las flechas también llevan a la índice por la ruta base", async () => {
    const user = userEvent.setup();
    renderIndexTabs("/socios/1/membresias");

    screen.getByRole("tab", { name: "Membresías" }).focus();
    await user.keyboard("{ArrowLeft}");

    expect(screen.getByTestId("location").textContent).toBe("/socios/1");
  });

  it("S3-F7: en modo segmento, cambiar de pestaña vuelve a la primera página de su lista y conserva lo demás", async () => {
    const user = userEvent.setup();
    renderIndexTabs("/socios/1/membresias?offset=25&limit=50&pago=nuevo");

    await user.click(screen.getByRole("tab", { name: "Datos" }));

    expect(screen.getByTestId("location").textContent).toBe("/socios/1?limit=50&pago=nuevo");
  });

  it("revisión S3-F7 (M3): una pestaña con disabledNote se ve deshabilitada con ese texto, sin versión, y las flechas la saltan", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/socios/1"]}>
        <Tabs
          label="Secciones"
          tabs={[
            { id: "datos", label: "Datos" },
            { id: "pagos", label: "Pagos", disabledNote: "No disponible" },
            { id: "notas", label: "Notas" },
          ]}
        >
          {(active) => <p>{`Panel ${active}`}</p>}
        </Tabs>
      </MemoryRouter>,
    );
    const pagos = screen.getByRole("tab", { name: /^Pagos/ });

    expect(pagos).toHaveAttribute("aria-disabled", "true");
    expect(pagos).toHaveTextContent("No disponible");
    expect(pagos).not.toHaveTextContent("Disponible en");
    screen.getByRole("tab", { name: "Datos" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Notas" })).toHaveAttribute("aria-selected", "true");
  });
});

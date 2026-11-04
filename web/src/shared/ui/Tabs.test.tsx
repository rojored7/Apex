// US-064 T2 y T4: pestañas accesibles con la pestaña activa en la URL.
// S3-F1 (E14): en modo segmento, `indexId` es la pestaña que vive en la ruta base (hija índice).
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
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

// S4B-F1 (S4B-D51; deuda de S4A-F2): la barra de la ficha tiene nueve pestañas y, a 1440 px con
// Historial activa, "Membresías" quedaba recortada. jsdom no maqueta: la geometría se simula con
// getBoundingClientRect (cada pestaña de TAB_WIDTH px, en fila, desplazada por `scrollLeft`) y
// scrollIntoView mueve ese desplazamiento como lo haría el navegador con `nearest`.
const NINE_TABS: TabItem[] = [
  { id: "datos", label: "Datos" },
  { id: "membresias", label: "Membresías" },
  { id: "pagos", label: "Pagos" },
  { id: "asistencia", label: "Asistencia", disabledUntil: "v0.4" },
  { id: "resultados", label: "Resultados", disabledUntil: "v0.5" },
  { id: "atleta", label: "Atleta", disabledUntil: "v0.6" },
  { id: "avisos", label: "Avisos", disabledUntil: "v0.2" },
  { id: "adjuntos", label: "Adjuntos", disabledUntil: "v0.3" },
  { id: "historial", label: "Historial" },
];
// vitest corre con cwd = web/; el CSS se lee como texto (import ?raw lo procesa como módulo CSS).
const tabsCss = readFileSync(resolve(process.cwd(), "src/shared/ui/Tabs.module.css"), "utf8");
const tokensCss = readFileSync(resolve(process.cwd(), "src/core/styles/tokens.css"), "utf8");
const TAB_WIDTH = 120;
const NEAREST = { inline: "nearest", block: "nearest" } as const;

interface Box {
  left: number;
  right: number;
}

describe("Tabs · nueve pestañas con Historial activa (1440 px)", () => {
  const originalScroll = Object.getOwnPropertyDescriptor(Element.prototype, "scrollIntoView");
  let scrollLeft = 0;
  let barWidth = 0;
  let scrollIntoView: ReturnType<typeof vi.fn>;

  function rectOf(element: HTMLElement): DOMRect {
    let left = 0;
    let width = 0;
    if (element.getAttribute("role") === "tablist") {
      width = barWidth;
    } else if (element.getAttribute("role") === "tab") {
      width = TAB_WIDTH;
      left = Array.from(element.parentElement?.children ?? []).indexOf(element) * TAB_WIDTH - scrollLeft;
    }
    return { x: left, y: 0, top: 0, bottom: 44, left, right: left + width, width, height: 44, toJSON: () => ({}) };
  }

  beforeEach(() => {
    scrollLeft = 0;
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function mockRect(this: HTMLElement): DOMRect {
      return rectOf(this);
    });
    // Lo que hace `nearest`: no mueve nada si la caja cabe; si no, la lleva al borde más cercano.
    scrollIntoView = vi.fn(function scrollIntoViewMock(this: HTMLElement) {
      const box = rectOf(this);
      if (box.left < 0) scrollLeft += box.left;
      else if (box.right > barWidth) scrollLeft += box.right - barWidth;
    });
    Object.defineProperty(Element.prototype, "scrollIntoView", { configurable: true, writable: true, value: scrollIntoView });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    if (originalScroll) Object.defineProperty(Element.prototype, "scrollIntoView", originalScroll);
    else Reflect.deleteProperty(Element.prototype, "scrollIntoView");
  });

  function renderNine(initial: string) {
    return render(
      <MemoryRouter initialEntries={[initial]}>
        <Tabs label="Secciones del socio" tabs={NINE_TABS}>
          {(active) => <p>{`Panel ${active}`}</p>}
        </Tabs>
      </MemoryRouter>,
    );
  }

  const boxes = (): { bar: Box; tabs: Box[] } => ({
    bar: rectOf(screen.getByRole("tablist", { name: "Secciones del socio" })),
    tabs: screen.getAllByRole("tab").map(rectOf),
  });
  const inside = (tab: Box, bar: Box): boolean => tab.left >= bar.left && tab.right <= bar.right;

  it("pinta las nueve pestañas, Historial activa y las cinco futuras deshabilitadas", () => {
    barWidth = 1200;
    renderNine("/socios/1?tab=historial");

    expect(screen.getAllByRole("tab")).toHaveLength(9);
    expect(screen.getByRole("tab", { name: "Historial" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Panel historial");
    expect(screen.getAllByRole("tab").filter((tab) => tab.getAttribute("aria-disabled") === "true")).toHaveLength(5);
  });

  it("si las nueve caben en la barra, todas quedan dentro y no se desplaza nada", () => {
    barWidth = 9 * TAB_WIDTH + 120;
    renderNine("/socios/1?tab=historial");

    const { bar, tabs } = boxes();
    expect(tabs).toHaveLength(9);
    expect(tabs.every((tab) => inside(tab, bar))).toBe(true);
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("si la activa (Historial) no cabe, la lleva a la vista con scrollIntoView nearest y queda dentro de la barra", () => {
    barWidth = 5 * TAB_WIDTH;
    renderNine("/socios/1?tab=historial");

    expect(scrollIntoView).toHaveBeenCalledTimes(1);
    expect(scrollIntoView).toHaveBeenCalledWith(NEAREST);
    expect(scrollIntoView.mock.contexts[0]).toBe(screen.getByRole("tab", { name: "Historial" }));
    const { bar, tabs } = boxes();
    expect(inside(tabs[8] as Box, bar)).toBe(true);
  });

  it("si la activa ya cabe (Datos, la primera), no llama a scrollIntoView aunque otras queden fuera", () => {
    barWidth = 5 * TAB_WIDTH;
    renderNine("/socios/1?tab=datos");

    const { bar, tabs } = boxes();
    expect(inside(tabs[0] as Box, bar)).toBe(true);
    expect(inside(tabs[8] as Box, bar)).toBe(false);
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("al pasar con End a Historial en una barra corta la lleva a la vista, y con Home regresa a Datos", async () => {
    const user = userEvent.setup();
    barWidth = 5 * TAB_WIDTH;
    renderNine("/socios/1?tab=datos");
    await user.click(screen.getByRole("tab", { name: "Datos" }));

    await user.keyboard("{End}");

    expect(screen.getByRole("tab", { name: "Historial" })).toHaveAttribute("aria-selected", "true");
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
    expect(scrollIntoView.mock.contexts[0]).toBe(screen.getByRole("tab", { name: "Historial" }));
    expect(scrollIntoView).toHaveBeenLastCalledWith(NEAREST);

    await user.keyboard("{Home}");

    expect(screen.getByRole("tab", { name: "Datos" })).toHaveAttribute("aria-selected", "true");
    const { bar, tabs } = boxes();
    expect(inside(tabs[0] as Box, bar)).toBe(true);
  });

  it("sin scrollIntoView en el entorno (jsdom antiguo) no lanza", () => {
    Reflect.deleteProperty(Element.prototype, "scrollIntoView");
    barWidth = 5 * TAB_WIDTH;

    expect(() => renderNine("/socios/1?tab=historial")).not.toThrow();
    expect(within(screen.getByRole("tablist")).getAllByRole("tab")).toHaveLength(9);
  });
});

describe("Tabs.module.css · sin medidas literales", () => {
  const css = tabsCss.replace(/\/\*[\s\S]*?\*\//g, "");
  const tokens = tokensCss;
  const LAYOUT = /^(width|min-width|max-width|flex-basis|flex|padding(-[a-z]+)?|gap|column-gap|font-size|inline-size|min-inline-size|max-inline-size)$/;

  const declarations = Array.from(css.matchAll(/([a-z-]+)\s*:\s*([^;{}]+);/g), (m) => ({ property: m[1] ?? "", value: (m[2] ?? "").trim() }));

  it("el ancho, el relleno y la separación de las pestañas no llevan px, rem, em, vw ni ch literales", () => {
    const literal = declarations.filter((d) => LAYOUT.test(d.property) && /-?\d*\.?\d+(px|rem|em|vw|ch|%)(?![a-z])/.test(d.value));

    expect(literal).toEqual([]);
  });

  it("toda variable que usa existe en tokens.css", () => {
    const used = new Set(Array.from(css.matchAll(/var\((--[a-z0-9-]+)/g), (m) => m[1] ?? ""));
    const missing = Array.from(used).filter((name) => !new RegExp(`${name}\\s*:`).test(tokens));

    expect(used.size).toBeGreaterThan(0);
    expect(missing).toEqual([]);
  });
});

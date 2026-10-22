// @vitest-environment node
// US-068 T7 (criterio 6): los 16 componentes del kit de DESIGN.md existen en src/shared/ui,
// cada uno con su prueba, salen del barril y están en el catálogo (dev/Catalog.tsx).
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const UI = fileURLToPath(new URL("../src/shared/ui/", import.meta.url));
const CATALOG = fileURLToPath(new URL("../src/dev/Catalog.tsx", import.meta.url));

/** Los 16 nombres de CLAUDE.md ("Front: diseño aprobado", regla 5) y DESIGN.md. */
const KIT = [
  "TopBar",
  "SideNav",
  "PageHeader",
  "Button",
  "StatusTag",
  "FilterBar",
  "DataTable",
  "Pagination",
  "Chips",
  "Tabs",
  "KpiCard",
  "SidePanel",
  "ConfirmModal",
  "Field",
  "MaskedValue",
  "HistoryAside",
] as const;

describe("inventario del kit", () => {
  it("son exactamente 16 nombres sin repetir", () => {
    expect(new Set(KIT).size).toBe(16);
  });

  it.each(KIT)("%s tiene componente, CSS Module y prueba", (name) => {
    expect(existsSync(`${UI}${name}.tsx`), `${name}.tsx`).toBe(true);
    expect(existsSync(`${UI}${name}.module.css`), `${name}.module.css`).toBe(true);
    expect(existsSync(`${UI}${name}.test.tsx`), `${name}.test.tsx`).toBe(true);
  });

  it("el barril src/shared/ui/index.ts exporta los 16", () => {
    const barrel = readFileSync(`${UI}index.ts`, "utf8");
    for (const name of KIT) expect(barrel, name).toMatch(new RegExp(`export \\{ ${name} \\} from "\\./${name}"`));
  });

  it("el catálogo muestra los 16 y los cuatro layouts", () => {
    const catalog = readFileSync(CATALOG, "utf8");
    for (const name of KIT) expect(catalog, name).toMatch(new RegExp(`<${name}[\\s>/]`));
    for (const view of ["panel", "portal", "gym", "tv"]) expect(catalog).toContain(`?vista=${view}`);
  });
});

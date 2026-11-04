// @vitest-environment node
// S4B-F1 (S4B-D51; deuda de V10/V11 del Sprint 4A, "Dueño: front, regla de lint explícita en 4B"):
// sessionStorage solo se usa en src/pages/RouteError.tsx (la marca de tiempo de la única recarga
// por chunk, sin datos del usuario ni tokens). Como web/eslint.config.js está protegido por el hook
// config-protection, la regla vive en tests/lint/restricted-config.ts (como las de fetch e Intl) y
// esta prueba la aplica a fuentes falsas y a RouteError.tsx real. La lista blanca es un solo
// archivo exacto; los archivos de prueba (*.test.*) quedan fuera de la regla porque simulan el
// almacenamiento.
import { readFileSync } from "node:fs";
import { lintSnippet, WEB_ROOT } from "./restricted-config";

const ALLOWED = "src/pages/RouteError.tsx";
const BARE = 'export const read = () => sessionStorage.getItem("clave");\n';
const WINDOW = 'export const read = () => window.sessionStorage.getItem("clave");\n';
const GLOBAL_THIS = 'export const write = () => globalThis.sessionStorage.setItem("clave", "1");\n';

describe("sessionStorage solo desde src/pages/RouteError.tsx", () => {
  it("rechaza sessionStorage a secas en un archivo nuevo de src (fuente falsa)", async () => {
    expect(await lintSnippet(BARE, "src/features/x/NuevoArchivo.ts")).toContain("no-restricted-globals");
  });

  it("rechaza window.sessionStorage en un componente nuevo", async () => {
    expect(await lintSnippet(WINDOW, "src/shared/ui/Nuevo.tsx")).toContain("no-restricted-properties");
  });

  it("rechaza globalThis.sessionStorage en un hook nuevo", async () => {
    expect(await lintSnippet(GLOBAL_THIS, "src/shared/data/useNuevo.ts")).toContain("no-restricted-properties");
  });

  it("rechaza sessionStorage dentro de src/core (ni siquiera el cliente de la API ni el de la sesión lo usan)", async () => {
    expect(await lintSnippet(BARE, "src/core/auth/session.ts")).toContain("no-restricted-globals");
    expect(await lintSnippet(WINDOW, "src/core/api/client.ts")).toContain("no-restricted-properties");
  });

  it("rechaza sessionStorage en un archivo de nombre parecido al de la lista blanca", async () => {
    expect(await lintSnippet(BARE, "src/pages/RouteError2.tsx")).toContain("no-restricted-globals");
    expect(await lintSnippet(BARE, "src/features/x/pages/RouteError.tsx")).toContain("no-restricted-globals");
  });

  it("acepta sessionStorage solo en src/pages/RouteError.tsx (lista blanca exacta)", async () => {
    expect(await lintSnippet(BARE, ALLOWED)).toEqual([]);
    expect(await lintSnippet(WINDOW, ALLOWED)).toEqual([]);
    expect(await lintSnippet(GLOBAL_THIS, ALLOWED)).toEqual([]);
  });

  it("el RouteError.tsx real cumple la regla y la misma fuente en otra ruta la incumple", async () => {
    const source = readFileSync(`${WEB_ROOT}${ALLOWED}`, "utf8");

    // La lista blanca no sobra: el archivo real sí usa sessionStorage.
    expect(source).toContain("sessionStorage.getItem");
    expect(await lintSnippet(source, ALLOWED)).toEqual([]);
    expect(await lintSnippet(source, "src/pages/Copia.tsx")).toContain("no-restricted-globals");
  });

  it("los archivos de prueba de src pueden simular sessionStorage", async () => {
    expect(await lintSnippet(BARE, "src/core/auth/session.test.ts")).toEqual([]);
    expect(await lintSnippet(WINDOW, "src/features/x/pages/NuevaPagina.test.tsx")).toEqual([]);
  });

  it("rechaza el acceso calculado a window (window[k]) que esquivaría la regla", async () => {
    const code = 'const k = ["session", "Storage"].join("");\nexport const read = () => window[k];\n';
    expect(await lintSnippet(code, "src/features/x/Nuevo.ts")).toContain("no-restricted-syntax");
  });

  it("límite aceptado: un alias de window (const w = window; w.sessionStorage) no se detecta sin análisis de flujo", async () => {
    // Documenta el comportamiento actual, no una garantía: ESLint por sí solo no sigue alias. Se cubre
    // con revisión de código y con la lista blanca de un solo archivo.
    const code = "const w = window;\nexport const read = () => w.sessionStorage;\n";
    expect(await lintSnippet(code, "src/features/x/Alias.ts")).toEqual([]);
  });

  it("no sustituye las demás reglas: fetch sigue prohibido en el mismo archivo", async () => {
    const rules = await lintSnippet('export const a = () => fetch("/x");\n', ALLOWED);
    expect(rules).toContain("no-restricted-globals");
  });
});

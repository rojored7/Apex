// @vitest-environment node
// Revisión del Sprint 2 (M5 y L1 de TypeScript): fronteras que se rompieron una vez y no deben
// volver a romperse.
// - Ninguna feature importa de otra feature: lo que comparten vive en core/ o shared/.
// - INVALID_RESPONSE_MESSAGE y las constantes HTTP_* solo se definen en src/core/api.
// - Nadie redefine el atajo `fieldError`/`errorOf` para Field: Field acepta `error` indefinido.
// - Ninguna pantalla pasa `localQuery: false` a useListParams (S2-D41: `q` nunca en la URL).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../../src/", import.meta.url));
const FEATURES = join(SRC, "features");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return walk(path);
    return /\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}

const FILES = walk(SRC);
const SOURCE_FILES = FILES.filter((file) => !/\.test\.(ts|tsx)$/.test(file) && !file.endsWith(`${sep}types.ts`));
const rel = (file: string): string => relative(SRC, file).split(sep).join("/");
const read = (file: string): string => readFileSync(file, "utf8");

/** Nombre de la feature de un archivo bajo src/features, o null. */
function featureOf(file: string): string | null {
  const inside = relative(FEATURES, file);
  if (inside.startsWith("..")) return null;
  return inside.split(sep)[0] ?? null;
}

const IMPORT = /(?:import|export)\s[^"']*?from\s+["']([^"']+)["']|import\(\s*["']([^"']+)["']\s*\)/g;

function relativeImports(file: string): string[] {
  const specs: string[] = [];
  for (const match of read(file).matchAll(IMPORT)) {
    const spec = match[1] ?? match[2];
    if (spec?.startsWith(".")) specs.push(resolve(dirname(file), spec));
  }
  return specs;
}

describe("fronteras del front (revisión del Sprint 2)", () => {
  it("ninguna feature importa de otra feature", () => {
    const crossings = FILES.flatMap((file) => {
      const own = featureOf(file);
      if (own === null) return [];
      return relativeImports(file)
        .filter((target) => {
          const other = featureOf(target);
          return other !== null && other !== own;
        })
        .map((target) => `${rel(file)} -> ${relative(SRC, target).split(sep).join("/")}`);
    });

    expect(crossings).toEqual([]);
  });

  it("INVALID_RESPONSE_MESSAGE solo se define en src/core/api", () => {
    const defined = SOURCE_FILES.filter((file) => /\bINVALID_RESPONSE_MESSAGE\s*=/.test(read(file))).map(rel);

    expect(defined).toEqual(["core/api/response.ts"]);
  });

  it("las constantes HTTP_* solo se definen en src/core/api", () => {
    const outside = SOURCE_FILES.filter((file) => !rel(file).startsWith("core/api/") && /\bconst\s+HTTP_[A-Z_]+\s*=/.test(read(file))).map(rel);

    expect(outside).toEqual([]);
    expect(read(join(SRC, "core/api/status.ts"))).toMatch(/export const HTTP_TOO_MANY = 429;/);
  });

  it("nadie redefine un atajo de error para Field (fieldError, errorOf)", () => {
    const copies = SOURCE_FILES.filter((file) => /\bconst\s+(fieldError|errorOf)\s*=\s*(<[^>]*>)?\(|function\s+(fieldError|errorOf)\s*[<(]/.test(read(file))).map(rel);

    expect(copies).toEqual([]);
  });

  it("ninguna pantalla pasa localQuery: false a useListParams (S2-D41)", () => {
    const offenders = SOURCE_FILES.filter((file) => /localQuery\s*:\s*false/.test(read(file))).map(rel);

    expect(offenders).toEqual([]);
  });
});

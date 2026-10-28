// @vitest-environment node
// Fase 4 del Sprint 3 (M6, S3-D52): toda mutación de las features y de shared pasa por
// useSensitiveMutation (core/api), que fija `gcTime: 0` y `reset()` al terminar. Un `useMutation`
// directo solo se admite dentro de las funciones de la lista blanca, cada una con su razón: no llevan
// valores sensibles, o leen el estado de la mutación a propósito y la reinician al cerrar.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../../src/", import.meta.url));

/** "archivo#función" que puede llamar a useMutation directamente, con su razón. */
const ALLOWED: Readonly<Record<string, string>> = {
  // Solo el id del socio: no hay valor sensible en el cuerpo ni en la respuesta enmascarada.
  "features/members/api.ts#useDeactivateMember": "solo el id",
  "features/members/api.ts#useReactivateMember": "solo el id; la respuesta es la ficha enmascarada (N-01)",
  // Nombre, tipo, precio y duración de un plan: datos del gimnasio, no personales.
  "features/plans/api.ts#useCreatePlan": "datos del plan, no personales",
  // El conflicto de versión (409) se lee de `mutation.error` y "Recargar" llama a reset() (S2-F5).
  "features/system/api.ts#useSettingsSection": "configuración del gimnasio; el 409 se lee del estado de la mutación",
  // El enlace de activación se muestra desde `create.data` y el panel llama a reset() al cerrar (S2-F4a).
  "features/system/api.ts#useCreateUser": "gcTime 0; el enlace se lee de data y el panel hace reset() al cerrar",
  // Cuentas del equipo por id; el reenvío muestra el enlace desde `data` y LinkModal hace reset() al cerrar (L-7).
  "features/system/api.ts#useUserMutation": "id de la cuenta; el enlace reenviado se lee de data y se reinicia al cerrar (L-7)",
};

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return walk(path);
    return /\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}

const FILES = [...walk(join(SRC, "features")), ...walk(join(SRC, "shared"))];
const rel = (file: string): string => relative(SRC, file).split(sep).join("/");

const CALL = /\buseMutation\s*[<(]/g;
const FUNCTION = /(?:export\s+)?function\s+(\w+)/g;

/** El nombre de la última función declarada antes de `index`, o "?". */
function enclosingFunction(source: string, index: number): string {
  let name = "?";
  for (const match of source.slice(0, index).matchAll(FUNCTION)) name = match[1] ?? "?";
  return name;
}

/** "archivo#función" de cada llamada directa a useMutation. */
function directMutations(): string[] {
  return FILES.flatMap((file) => {
    const source = readFileSync(file, "utf8");
    return [...source.matchAll(CALL)].map((match) => `${rel(file)}#${enclosingFunction(source, match.index)}`);
  });
}

describe("mutaciones con valores sensibles (S3-D52)", () => {
  it("toda llamada directa a useMutation está en la lista blanca", () => {
    const offenders = directMutations().filter((site) => !(site in ALLOWED));

    expect(offenders).toEqual([]);
  });

  it("la lista blanca no tiene entradas muertas", () => {
    const sites = new Set(directMutations());

    expect(Object.keys(ALLOWED).filter((site) => !sites.has(site))).toEqual([]);
  });

  it("useSensitiveMutation fija gcTime 0 y reset() al terminar", () => {
    const hook = readFileSync(join(SRC, "core/api/useSensitiveMutation.ts"), "utf8");

    expect(hook).toMatch(/gcTime:\s*0/);
    expect(hook).toMatch(/onSettled:\s*\(\)\s*=>\s*\{\s*resetRef\.current\(\);/);
  });

  it("las seis mutaciones de S3-D52 usan useSensitiveMutation", () => {
    const uses = (file: string, name: string): boolean => {
      const source = readFileSync(join(SRC, file), "utf8");
      const start = source.indexOf(`function ${name}(`);
      const next = source.indexOf("\nexport function ", start + 1);
      return start >= 0 && source.slice(start, next < 0 ? undefined : next).includes("useSensitiveMutation");
    };

    expect(
      [
        ["features/members/api.ts", "useUpdateMember"],
        ["features/memberships/api.ts", "useSellMembership"],
        ["features/memberships/api.ts", "useFreezeMembership"],
        ["features/memberships/api.ts", "useCancelMembership"],
        ["features/payments/api.ts", "useRegisterPayment"],
        ["features/payments/api.ts", "useVoidPayment"],
      ].filter(([file, name]) => !uses(file ?? "", name ?? "")),
    ).toEqual([]);
  });
});

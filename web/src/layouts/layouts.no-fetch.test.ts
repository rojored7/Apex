// US-062 T1 (criterio 7): ningún layout pide datos. Los archivos de src/layouts/ no
// importan el cliente del api ni TanStack Query; reciben su contenido como hijos o props.
const SOURCES = import.meta.glob<string>(["./**/*.{ts,tsx}", "!./**/*.test.{ts,tsx}"], {
  query: "?raw",
  import: "default",
  eager: true,
});

const FORBIDDEN = [/from\s+["'][^"']*core\/api[^"']*["']/, /from\s+["']@tanstack\/react-query["']/, /\bimport\(\s*["'][^"']*core\/api/];

describe("layouts sin peticiones", () => {
  it("encuentra los layouts", () => {
    expect(Object.keys(SOURCES)).toEqual(
      expect.arrayContaining(["./PanelLayout.tsx", "./PortalLayout.tsx", "./GymLayout.tsx", "./TvLayout.tsx", "./nav.ts"]),
    );
  });

  it.each(Object.entries(SOURCES))("%s no importa core/api ni @tanstack/react-query", (_file, source) => {
    for (const pattern of FORBIDDEN) expect(source).not.toMatch(pattern);
  });

  it("el control detecta un import prohibido", () => {
    expect('import { api } from "../core/api/client";').toMatch(FORBIDDEN[0] as RegExp);
    expect('import { useQuery } from "@tanstack/react-query";').toMatch(FORBIDDEN[1] as RegExp);
  });
});

// @vitest-environment node
// Corrección de V10 L-D (y Fase 4 L9): los helpers del stack crean cuentas y socios por el api; se
// niegan a correr si E2E_BASE_URL no apunta a localhost o 127.0.0.1, antes de crear nada.
import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { exigirStackLocal } from "../e2e/helpers/stack";

describe("exigirStackLocal (V10 L-D)", () => {
  it.each(["http://localhost:8180", "http://127.0.0.1:8180/", "https://localhost", "http://localhost"])("acepta %s", (url) => {
    expect(() => {
      exigirStackLocal(url);
    }).not.toThrow();
  });

  it.each([undefined, "", "https://apex.gimnasio.co", "http://localhost.evil.co", "http://10.0.0.5:8180", "no es una url", "http://127.0.0.1.nip.io"])("rechaza %s con un error claro", (url) => {
    expect(() => {
      exigirStackLocal(url);
    }).toThrow(/E2E_BASE_URL.*localhost o 127\.0\.0\.1/);
  });

  it("el login de los helpers (la puerta de todo lo que crea) llama a la guarda primero", () => {
    const source = readFileSync(new URL("../e2e/helpers/stack.ts", import.meta.url), "utf8");
    const login = source.slice(source.indexOf("async function login("));

    expect(login.split("\n").slice(0, 3).join("\n")).toMatch(/exigirStackLocal\(process\.env\.E2E_BASE_URL\);/);
    // La contraseña del coach creado no se puede adivinar por la hora (Fase 4 L9).
    expect(source).toContain("const password = `Coach-${crypto.randomUUID()}-e2e!`;");
  });

  it("toda spec que crea un coach lo borra al terminar (borrarUsuario en un finally)", () => {
    const dir = new URL("../e2e/stack/", import.meta.url);
    const specs = readdirSync(dir).filter((name) => name.endsWith(".spec.ts"));
    const offenders = specs.filter((name) => {
      const source = readFileSync(new URL(name, dir), "utf8");
      return source.includes("crearCoach(") && !/finally \{[^}]*borrarUsuario\(/s.test(source);
    });

    expect(specs.filter((name) => readFileSync(new URL(name, dir), "utf8").includes("crearCoach(")).length).toBeGreaterThan(0);
    expect(offenders).toEqual([]);
  });
});

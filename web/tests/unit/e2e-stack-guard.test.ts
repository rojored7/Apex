// @vitest-environment node
// Corrección de V10 L-D (y Fase 4 L9): los helpers del stack crean cuentas y socios por el api; se
// niegan a correr si E2E_BASE_URL no apunta a localhost o 127.0.0.1, antes de crear nada.
import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { Page } from "@playwright/test";
import { exigirStackLocal, loginComo, nombrePlanE2E, type CoachCreado } from "../e2e/helpers/stack";

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

  it("el login envía solo email y password aunque reciba un CoachCreado con id (LoginIn tiene extra=forbid)", async () => {
    const enviados: unknown[] = [];
    const page = {
      request: {
        post: (_url: string, options: { data: unknown }) => {
          enviados.push(options.data);
          return Promise.resolve({ ok: () => true, status: () => 200, json: () => Promise.resolve({ access_token: "t", must_change_password: false }) });
        },
      },
    } as unknown as Page;
    const coach: CoachCreado = { id: "00000000-0000-0000-0000-000000000002", email: "coach-x@apex.test", password: "p" };
    const anterior = process.env.E2E_BASE_URL;
    process.env.E2E_BASE_URL = "http://localhost:8180";
    try {
      await loginComo(page, coach);
    } finally {
      if (anterior === undefined) delete process.env.E2E_BASE_URL;
      else process.env.E2E_BASE_URL = anterior;
    }

    expect(enviados).toEqual([{ email: "coach-x@apex.test", password: "p" }]);
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

  it("toda spec que crea una cuenta desde la pantalla la borra en un finally y no deriva su contraseña de la hora", () => {
    // users-manage.spec.ts prueba justamente la baja por la pantalla y su cuenta nunca se activa.
    const BORRA_POR_LA_PANTALLA = new Set(["users-manage.spec.ts"]);
    const dir = new URL("../e2e/stack/", import.meta.url);
    const specs = readdirSync(dir).filter((name) => name.endsWith(".spec.ts") && !BORRA_POR_LA_PANTALLA.has(name));
    const conAlta = specs.filter((name) => readFileSync(new URL(name, dir), "utf8").includes('name: "Crear usuario"'));
    const offenders = conAlta.filter((name) => {
      const source = readFileSync(new URL(name, dir), "utf8");
      return !/finally \{[^}]*borrarUsuario\(/s.test(source) || /PASSWORD = `[^`]*\$\{RUN\}/.test(source);
    });

    expect(conAlta).toContain("users-activation.spec.ts");
    expect(offenders).toEqual([]);
  });
});

describe("nombrePlanE2E (validación final del Sprint 3)", () => {
  it("el plan más nuevo ordena antes que los de corridas anteriores y que los nombres con letra", () => {
    const antes = nombrePlanE2E(1_793_000_000_000);
    const despues = nombrePlanE2E(1_793_000_000_001);

    expect([antes, despues, "E2E-tope-1", "Mensual mvsl6sf5"].sort()).toEqual([despues, antes, "E2E-tope-1", "Mensual mvsl6sf5"]);
    expect(despues).toMatch(/^0 E2E [0-9a-z]{9}$/);
  });
});

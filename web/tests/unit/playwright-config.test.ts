// @vitest-environment node
// S2-W0-1 (US-068 DevOps): Playwright tiene dos proyectos. `preview` corre contra
// `vite preview` (lo arranca webServer); `stack` corre contra el stack de Compose en
// E2E_BASE_URL y, cuando esa variable existe, no se arranca ningún webServer.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { PlaywrightTestConfig } from "@playwright/test";
import { afterEach, describe, expect, it, vi } from "vitest";
import { THEMES, VIEWPORTS, captureName } from "../e2e/helpers/stack";

const ORIGINAL = process.env.E2E_BASE_URL;

async function loadConfig(baseUrl: string | undefined): Promise<PlaywrightTestConfig> {
  vi.resetModules();
  if (baseUrl === undefined) delete process.env.E2E_BASE_URL;
  else process.env.E2E_BASE_URL = baseUrl;
  const mod = await import("../../playwright.config");
  return mod.default;
}

function project(config: PlaywrightTestConfig, name: string) {
  const found = config.projects?.find((p) => p.name === name);
  if (found === undefined) throw new Error(`sin proyecto ${name}`);
  return found;
}

afterEach(() => {
  if (ORIGINAL === undefined) delete process.env.E2E_BASE_URL;
  else process.env.E2E_BASE_URL = ORIGINAL;
});

describe("playwright.config.ts (S2-W0-1)", () => {
  it("declara exactamente los proyectos preview y stack", async () => {
    const config = await loadConfig(undefined);
    expect(config.projects?.map((p) => p.name)).toEqual(["preview", "stack"]);
  });

  it("sin E2E_BASE_URL arranca vite preview y ambos proyectos usan su URL", async () => {
    const config = await loadConfig(undefined);
    expect(config.webServer).toMatchObject({ port: 4173 });
    expect(project(config, "preview").use?.baseURL).toBe("http://localhost:4173");
    expect(project(config, "stack").use?.baseURL).toBe("http://localhost:4173");
  });

  it("con E2E_BASE_URL no arranca webServer y stack apunta al stack", async () => {
    const config = await loadConfig("http://localhost:8180/");
    expect(config.webServer).toBeUndefined();
    expect(project(config, "stack").use?.baseURL).toBe("http://localhost:8180");
  });

  it("preview ignora las specs del stack y stack solo corre las suyas", async () => {
    const config = await loadConfig(undefined);
    expect(project(config, "preview").testIgnore).toEqual(["stack/**", "helpers/**"]);
    expect(project(config, "stack").testMatch).toBe("stack/**/*.spec.ts");
  });

  it("los scripts de npm separan los dos proyectos", () => {
    const pkg = JSON.parse(readFileSync(join(import.meta.dirname, "..", "..", "package.json"), "utf8")) as {
      scripts: Record<string, string>;
    };
    expect(pkg.scripts.e2e).toBe("playwright test --project=preview");
    expect(pkg.scripts["e2e:stack"]).toBe("playwright test --project=stack");
  });

  it("las capturas cubren 320, 768, 1024 y 1440 px en claro y oscuro", () => {
    expect(VIEWPORTS).toEqual([320, 768, 1024, 1440]);
    expect(THEMES).toEqual(["light", "dark"]);
    expect(captureName("inicio", "dark", 320)).toBe("test-results/captures/inicio-dark-320.png");
  });
});

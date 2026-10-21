// @vitest-environment node
// US-059 T3 y T7: types.ts sale de docs/openapi.json con openapi-typescript y debe estar
// al día; Page<T> tiene la forma del contrato de listas; leer un campo que el contrato no
// tiene no compila (el @ts-expect-error hace fallar tsc si alguien lo quita).
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import { pageSchema, type Page } from "./page";
import type { components } from "./types";

type ErrorBody = components["schemas"]["ErrorBody"];

const WEB_ROOT = fileURLToPath(new URL("../../../", import.meta.url));
const read = (path: string): string => readFileSync(path, "utf8").replace(/\r\n/g, "\n");

describe("tipos generados desde docs/openapi.json", () => {
  it("types.ts está al día con el contrato versionado (npm run gen:api)", () => {
    const outDir = mkdtempSync(join(tmpdir(), "apex-openapi-"));
    try {
      const out = join(outDir, "types.ts");
      const cli = join(WEB_ROOT, "node_modules", "openapi-typescript", "bin", "cli.js");
      execFileSync(process.execPath, [cli, join(WEB_ROOT, "..", "docs", "openapi.json"), "-o", out], {
        cwd: WEB_ROOT,
        stdio: "pipe",
      });

      expect(read(join(WEB_ROOT, "src", "core", "api", "types.ts"))).toBe(read(out));
    } finally {
      rmSync(outDir, { recursive: true, force: true });
    }
  }, 60_000);

  it("el script gen:api apunta al contrato versionado", () => {
    const pkg = JSON.parse(read(join(WEB_ROOT, "package.json"))) as { scripts: Record<string, string> };

    expect(pkg.scripts["gen:api"]).toBe("openapi-typescript ../docs/openapi.json -o src/core/api/types.ts");
  });

  it("el envelope de error del contrato tiene code y message obligatorios", () => {
    expectTypeOf<ErrorBody["code"]>().toEqualTypeOf<string>();
    expectTypeOf<ErrorBody["message"]>().toEqualTypeOf<string>();
    expectTypeOf<ErrorBody>().toHaveProperty("existing_id");

    const body: ErrorBody = { code: "x", message: "y", field: null, existing_id: null };
    // @ts-expect-error -- "cedula" no existe en el contrato: tsc falla si se quita esta marca.
    expect(body.cedula).toBeUndefined();
  });

  it("Page<T> tiene items, total, limit y offset", () => {
    expectTypeOf<Page<ErrorBody>>().toEqualTypeOf<{ items: ErrorBody[]; total: number; limit: number; offset: number }>();
  });

  it("pageSchema valida la forma de una página y rechaza lo demás", () => {
    const schema = pageSchema(z.object({ id: z.string() }));

    expect(schema.parse({ items: [{ id: "1" }], total: 1, limit: 25, offset: 0 })).toEqual({
      items: [{ id: "1" }],
      total: 1,
      limit: 25,
      offset: 0,
    });
    expect(schema.safeParse({ items: [], total: -1, limit: 25, offset: 0 }).success).toBe(false);
    expect(schema.safeParse({ items: [{ id: 1 }], total: 1, limit: 25, offset: 0 }).success).toBe(false);
    expect(schema.safeParse({ items: [], total: 0, limit: 201, offset: 0 }).success).toBe(false);
    expect(schema.safeParse({ rows: [] }).success).toBe(false);
  });
});

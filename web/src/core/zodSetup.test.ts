// S3-D105: Zod 4 sin compilación con `new Function` (la CSP no permite eval).
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { z } from "zod";
import "./zodSetup";

const SRC = join(__dirname, "..");

describe("zodSetup", () => {
  it("deja Zod en modo jitless", () => {
    expect(z.config().jitless).toBe(true);
  });

  it("en modo jitless un objeto estricto sigue rechazando las claves de más", () => {
    const schema = z.object({ id: z.string() }).strict();

    expect(schema.safeParse({ id: "a" }).success).toBe(true);
    expect(schema.safeParse({ id: "a", extra: 1 }).error?.issues[0]?.code).toBe("unrecognized_keys");
  });

  // Revisión de S3-D105 (MEDIUM): la CSP depende del orden de evaluación de los módulos; si un
  // reordenador de imports mueve zodSetup, Zod volvería a probar `new Function` en el navegador.
  it.each(["main.tsx", "dev/catalogMain.tsx", "test/setup.ts"])("zodSetup es el primer import de %s", (entry) => {
    const firstImport = readFileSync(join(SRC, entry), "utf8")
      .split("\n")
      .find((line) => line.startsWith("import "));

    expect(firstImport).toMatch(/^import "(?:\.\.?\/)+(?:core\/)?zodSetup";$/);
  });
});

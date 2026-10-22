// @vitest-environment node
// Revisión del Sprint 2 (M5 general): la política del front es la del contrato del api.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import { PASSWORD_LIMITS } from "./passwordPolicy";

const OPENAPI = fileURLToPath(new URL("../../../../docs/openapi.json", import.meta.url));

const passwordField = z.object({ minLength: z.number().int(), maxLength: z.number().int() });
const contract = z.object({
  components: z.object({
    schemas: z.object({
      ChangePasswordIn: z.object({ properties: z.object({ new_password: passwordField }) }),
      ResetIn: z.object({ properties: z.object({ new_password: passwordField }) }),
    }),
  }),
});

const { schemas } = contract.parse(JSON.parse(readFileSync(OPENAPI, "utf8"))).components;

describe.each([
  ["ChangePasswordIn", schemas.ChangePasswordIn.properties.new_password],
  ["ResetIn", schemas.ResetIn.properties.new_password],
])("PASSWORD_LIMITS frente a %s.new_password de docs/openapi.json", (_name, field) => {
  it("el máximo es el del contrato", () => {
    expect(field.maxLength).toBe(PASSWORD_LIMITS.max);
  });

  it("el mínimo es el del contrato", () => {
    expect(field.minLength).toBe(PASSWORD_LIMITS.min);
  });
});

describe("PASSWORD_LIMITS", () => {
  it("es inmutable y respeta N-10 (al menos 12)", () => {
    expect(Object.isFrozen(PASSWORD_LIMITS)).toBe(true);
    expect(PASSWORD_LIMITS.min).toBeGreaterThanOrEqual(12);
    expect(PASSWORD_LIMITS.max).toBeGreaterThan(PASSWORD_LIMITS.min);
  });
});

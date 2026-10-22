// S2-F5 (blueprint, decisión 22, alternativa): adaptador propio de Zod para React Hook Form.
import type { ResolverOptions } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "./zodResolver";

const options = { fields: {}, shouldUseNativeValidation: false } as ResolverOptions<{ name: string }>;

describe("zodResolver", () => {
  const schema = z.object({
    name: z.string().trim().min(1, "Escribe el nombre.").max(5, "Máximo 5 caracteres."),
    code: z
      .string()
      .regex(/^\d+$/, "Solo dígitos.")
      .refine((v) => v.length === 3, "Tres dígitos."),
  });

  it("con datos válidos devuelve los valores que entrega el esquema y ningún error", async () => {
    const result = await zodResolver(schema)({ name: "  Box ", code: "123" }, undefined, options as never);

    expect(result).toEqual({ values: { name: "Box", code: "123" }, errors: {} });
  });

  it("con datos inválidos devuelve un error por campo, el primero que encuentra, y valores vacíos", async () => {
    const result = await zodResolver(schema)({ name: "", code: "ab" }, undefined, options as never);

    expect(result.values).toEqual({});
    expect(result.errors).toEqual({
      name: { type: "too_small", message: "Escribe el nombre." },
      code: { type: "invalid_string", message: "Solo dígitos." },
    });
  });

  it("anida los errores de rutas con varios niveles", async () => {
    const nested = z.object({ contact: z.object({ email: z.string().email("Correo inválido.") }) });

    const result = await zodResolver(nested)({ contact: { email: "x" } }, undefined, options as never);

    expect(result.errors).toEqual({ contact: { email: { type: "invalid_string", message: "Correo inválido." } } });
  });

  it("un error sin ruta queda en root", async () => {
    const whole = z.object({ a: z.string() }).refine(() => false, "Revisa el formulario.");

    const result = await zodResolver(whole)({ a: "x" }, undefined, options as never);

    expect(result.errors).toEqual({ root: { type: "custom", message: "Revisa el formulario." } });
  });
});

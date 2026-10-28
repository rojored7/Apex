// S3-D105: la migración a Zod 4 no cambia lo que se acepta. El formato de correo de los
// formularios es `.regex(z.regexes.email, …)` (el patrón de `z.email()`, en el mismo orden de
// checks que el `.email()` de Zod 3); aquí se compara con el patrón de Zod 3 copiado tal cual.
import { z } from "zod";
import { CUSTOM_ISSUE } from "./zodIssues";

/** `emailRegex` de zod@3.25.76 (types.js). */
const ZOD3_EMAIL = /^(?!\.)(?!.*\.\.)([A-Z0-9_'+\-.]*)[A-Z0-9_+-]@([A-Z0-9][A-Z0-9-]*\.)+[A-Z]{2,}$/i;

const EMAILS = [
  "ana@correo.com",
  "ANA.Perez@Correo.CO",
  "o'neil+box@apex.test",
  "a_b-c@sub.dominio.com.co",
  "ana@correo",
  ".ana@correo.com",
  "ana.@correo.com",
  "an..a@correo.com",
  "ana@-correo.com",
  "ana@correo..com",
  "ana@correo.c",
  "ana'@correo.com",
  "ana correo@correo.com",
  "ana@correo.com ",
  "ñandú@correo.com",
  "@correo.com",
  "ana@",
  "",
];

describe("migración a Zod 4 (S3-D105)", () => {
  it.each(EMAILS)("el patrón de correo de Zod 4 decide igual que el de Zod 3: %j", (email) => {
    expect(z.regexes.email.test(email)).toBe(ZOD3_EMAIL.test(email));
  });

  it("un aviso propio de superRefine lleva el código custom", () => {
    const schema = z.string().superRefine((_value, ctx) => {
      ctx.addIssue({ code: CUSTOM_ISSUE, message: "Revisa el valor." });
    });

    const result = schema.safeParse("x");

    expect(result.error?.issues).toEqual([expect.objectContaining({ code: "custom", message: "Revisa el valor.", path: [] })]);
  });

  it.each(["2026-10-21T20:30:00Z", "2026-10-21T20:30:00+00:00", "2026-10-21T20:30:00.123456-05:00"])(
    "z.iso.datetime({ offset: true }) acepta la fecha con zona que emite el api: %s",
    (value) => {
      expect(z.iso.datetime({ offset: true }).safeParse(value).success).toBe(true);
    },
  );
});

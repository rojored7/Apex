// S3-D105: código de los avisos propios de `superRefine` con Zod 4. Zod 4 pide el `code` en el
// tipo de `ctx.addIssue` y `z.ZodIssueCode` quedó obsoleto; este nombre evita repetir el literal
// en cada esquema (la prueba de errorCodes.test.ts no deja comparar ni armar `code` con literales).
import type { core } from "zod";

export const CUSTOM_ISSUE: core.$ZodIssueCustom["code"] = "custom";

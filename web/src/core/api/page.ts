// US-059 T7: contrato de listas { items, total, limit, offset } (regla de datos 6).
// DESIGN-GAP: docs/openapi.json todavía no publica ningún esquema de lista (no hay
// endpoints de negocio en el Sprint 1); Page<T> se declara aquí y pageSchema lo valida en
// tiempo de ejecución. Cuando exista el primer esquema de página se compara contra él.
import { z } from "zod";
import { MAX_LIMIT } from "./query";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

/** Esquema Zod de una página para validar la respuesta del api antes de usarla. */
export function pageSchema<T extends z.ZodType>(item: T): z.ZodType<Page<z.infer<T>>> {
  return z.object({
    items: z.array(item),
    total: z.number().int().nonnegative(),
    limit: z.number().int().min(1).max(MAX_LIMIT),
    offset: z.number().int().nonnegative(),
  });
}

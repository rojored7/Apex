// US-059 T5: query string y parámetros de lista (regla de datos 6, decisión D2).
export type QueryScalar = string | number | boolean;
export type QueryValue = QueryScalar | readonly QueryScalar[] | null | undefined;
export type QueryParams = Readonly<Record<string, QueryValue>>;

/** Máximo que acepta el api en `limit`. */
export const MAX_LIMIT = 200;
/** Tamaño de página por defecto. */
export const DEFAULT_LIMIT = 25;

const encodePair = (key: string, value: QueryScalar): string =>
  `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`;

/** `a=1&b=x&b=y`, sin `?`. Omite `undefined` y `null`; los arreglos repiten la clave. */
export function toQueryString(params: QueryParams): string {
  const pairs: string[] = [];
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    if (Array.isArray(value)) {
      for (const item of value as readonly QueryScalar[]) pairs.push(encodePair(key, item));
    } else {
      pairs.push(encodePair(key, value as QueryScalar));
    }
  }
  return pairs.join("&");
}

/**
 * `limit` leído de la URL: un entero de 1 a 200; cualquier otro valor vuelve a 25
 * (US-063 criterio 2).
 */
export function clampLimit(value: unknown): number {
  const n = typeof value === "number" ? value : typeof value === "string" && value.trim() !== "" ? Number(value) : NaN;
  return Number.isInteger(n) && n >= 1 && n <= MAX_LIMIT ? n : DEFAULT_LIMIT;
}

function capLimit(value: QueryValue): number {
  const n = typeof value === "number" ? Math.trunc(value) : NaN;
  if (!Number.isFinite(n) || n < 1) return DEFAULT_LIMIT;
  return Math.min(n, MAX_LIMIT);
}

function cleanOffset(value: QueryValue): number {
  const n = typeof value === "number" ? Math.trunc(value) : NaN;
  return Number.isFinite(n) && n > 0 ? n : 0;
}

/**
 * Parámetros de una lista listos para el cliente. `limit` nunca pasa de 200 (un pedido de
 * 500 se envía como 200), `offset` nunca es negativo y los filtros vacíos se descartan.
 */
export function listParams({ limit, offset, ...filters }: QueryParams): Record<string, string | string[]> {
  const out: Record<string, string | string[]> = {
    limit: String(capLimit(limit)),
    offset: String(cleanOffset(offset)),
  };
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === "") continue;
    out[key] = Array.isArray(value) ? (value as readonly QueryScalar[]).map(String) : String(value);
  }
  return out;
}

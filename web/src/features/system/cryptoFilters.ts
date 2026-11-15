// S6-F2 · US-143, US-144: los filtros de /sistema/llaves, de la URL al api.
// - Inventario: `purpose`, `state` y `provider` (listas cerradas del contrato; un valor ajeno no viaja).
// - Bitácora: `from` y `to` como días civiles de Bogotá ("AAAA-MM-DD", lo que se ve en el campo) y `verb`.
//   El rango viaja en UTC como `[from, to)` ("Hasta 20 oct" incluye todo el 20). La regla es la del api
//   (`check_instant_range` más el tope de 366 días de `inventory._check_ops_range`): piso 2020-01-01, techo
//   hoy, `from` no posterior a `to` y a lo sumo 366 días. Un rango inválido no viaja y se explica.
// - `offset` es múltiplo de `limit` (nunca se pide una página a medias). La búsqueda `q` vive en memoria.
import { clampLimit } from "../../core/api/query";
import { addDaysCivil, bogotaDayEndUtc, bogotaDayStartUtc, civilDaysBetween, todayBogota } from "../../core/i18n/format";
import { CRYPTO_VERBS, KEY_PROVIDERS, KEY_PURPOSES, KEY_STATES, type CryptoVerb, type KeyProvider, type KeyPurpose, type KeyState } from "./schemas";

export const KEYS_FILTERS = ["purpose", "state", "provider"] as const;
export type KeysFilter = (typeof KEYS_FILTERS)[number];
export const OPS_FILTERS = ["from", "to", "verb"] as const;
export type OpsFilter = (typeof OPS_FILTERS)[number];

/** Piso de un filtro de instantes del api (INSTANT_FLOOR). */
export const OPS_FLOOR = "2020-01-01";
/** Tope del rango de la bitácora (MAX_OPS_RANGE) en días. */
export const OPS_MAX_DAYS = 366;
/** Tope del `offset` que una página puede pedir. */
const MAX_OFFSET = 100_000;

export const OPS_RANGE_MESSAGE = `Revisa las fechas: van desde 2020 hasta hoy, «Desde» no puede ser posterior a «Hasta» y el rango admite como máximo ${String(OPS_MAX_DAYS)} días.`;

const asParams = (search: string | URLSearchParams): URLSearchParams => (typeof search === "string" ? new URLSearchParams(search) : search);
const pick = <T extends string>(value: string | null, allowed: readonly T[]): T | "" => allowed.find((item) => item === value) ?? "";
/** Una fecha civil real "AAAA-MM-DD", o "" si no lo es. */
const civilOrEmpty = (value: string | null): string => (value !== null && addDaysCivil(value, 0) === value ? value : "");

export interface KeysUrlFilters {
  purpose: KeyPurpose | "";
  state: KeyState | "";
  provider: KeyProvider | "";
}

export interface OpsUrlFilters {
  from: string;
  to: string;
  verb: CryptoVerb | "";
}

export function readKeysFilters(search: string | URLSearchParams): KeysUrlFilters {
  const url = asParams(search);
  return { purpose: pick(url.get("purpose"), KEY_PURPOSES), state: pick(url.get("state"), KEY_STATES), provider: pick(url.get("provider"), KEY_PROVIDERS) };
}

export function readOpsFilters(search: string | URLSearchParams): OpsUrlFilters {
  const url = asParams(search);
  return { from: civilOrEmpty(url.get("from")), to: civilOrEmpty(url.get("to")), verb: pick(url.get("verb"), CRYPTO_VERBS) };
}

function pageParams(url: URLSearchParams, q: string): URLSearchParams {
  const limit = clampLimit(url.get("limit"));
  const raw = url.get("offset");
  const value = raw !== null && /^\d+$/.test(raw) ? Math.min(Number(raw), MAX_OFFSET) : 0;
  const out = new URLSearchParams({ limit: String(limit), offset: String(Math.floor(value / limit) * limit) });
  const text = q.trim();
  if (text) out.set("q", text);
  return out;
}

/** Los parámetros de GET /crypto/keys: solo lo válido, con los nombres del api. */
export function toKeysApiParams(search: string | URLSearchParams, q = ""): URLSearchParams {
  const url = asParams(search);
  const filters = readKeysFilters(url);
  const out = pageParams(url, q);
  for (const name of KEYS_FILTERS) if (filters[name]) out.set(name, filters[name]);
  return out;
}

/** Todas las llaves de una vez (el inventario completo es corto) para las tarjetas de resumen. */
export const SUMMARY_PARAMS = new URLSearchParams({ limit: "200", offset: "0" });

/** Por qué el rango de fechas no puede viajar, o null si es válido o está incompleto. */
export function opsRangeProblem(filters: Pick<OpsUrlFilters, "from" | "to">, today: string = todayBogota()): string | null {
  const { from, to } = filters;
  if (from === "" && to === "") return null;
  const dates = [from, to].filter((day) => day !== "");
  if (dates.some((day) => day < OPS_FLOOR || day > today)) return OPS_RANGE_MESSAGE;
  if (from !== "" && to !== "") {
    const span = civilDaysBetween(from, to);
    if (span === null || span < 0 || span + 1 > OPS_MAX_DAYS) return OPS_RANGE_MESSAGE;
  }
  return null;
}

/** Los parámetros de GET /crypto/ops; un rango inválido (opsRangeProblem) no viaja. */
export function toOpsApiParams(search: string | URLSearchParams, q = "", today: string = todayBogota()): URLSearchParams {
  const url = asParams(search);
  const filters = readOpsFilters(url);
  const out = pageParams(url, q);
  if (filters.verb) out.set("verb", filters.verb);
  if (opsRangeProblem(filters, today) !== null) return out;
  const from = filters.from ? bogotaDayStartUtc(filters.from) : null;
  const to = filters.to ? bogotaDayEndUtc(filters.to) : null;
  if (from) out.set("from", from);
  if (to) out.set("to", to);
  return out;
}

/** Los parámetros de GET /crypto/jobs: solo la página. */
export function toJobsApiParams(search: string | URLSearchParams): URLSearchParams {
  return pageParams(asParams(search), "");
}

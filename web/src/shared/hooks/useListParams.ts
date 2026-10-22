// US-063 T3: q, filtros, limit, offset y sort viven en la URL (reglas web: la URL es el
// estado). Recargar conserva la vista y "atrás" restaura la anterior. Un limit fuera de
// 1..200 vuelve a 25, cambiar búsqueda, filtro, orden o tamaño vuelve offset a 0, y solo
// pasan al api las claves declaradas (T11: nada desconocido llega al servidor).
// S2-D41: con `localQuery` (por defecto desde la revisión del Sprint 2, L1) la búsqueda vive en
// memoria y nunca en la URL; con `localQuery` en falso la deja en la URL (solo pruebas del modo URL).
// La espera de 300 ms de la búsqueda la hace FilterBar; la cancelación de la petición
// anterior la hace la feature con el `signal` de TanStack Query.
import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { z } from "zod";
import { clampLimit, offsetToPage, pageToOffset } from "../lib/pagination";

export interface SortState {
  field: string;
  direction: "asc" | "desc";
}

/** Parámetros listos para el api y para la queryKey. */
export interface ListParams {
  limit: number;
  offset: number;
  q?: string;
  sort?: string;
  [filter: string]: string | number | string[] | undefined;
}

export interface ListParamsApi<F extends string> {
  /** Objeto estable mientras la URL no cambie. */
  params: ListParams;
  q: string;
  filters: Record<F, string[]>;
  sort: SortState | null;
  page: number;
  setQuery: (q: string) => void;
  setFilter: (name: F, value: string | readonly string[] | undefined) => void;
  setPage: (page: number) => void;
  setLimit: (limit: number) => void;
  setSort: (sort: SortState | null) => void;
  clear: () => void;
}

export interface ListParamsConfig<F extends string> {
  /** Filtros que acepta la lista; cualquier otra clave de la URL se ignora. */
  filters?: readonly F[];
  /** Campos por los que se puede ordenar; sin lista, cualquiera bien formado. */
  sorts?: readonly string[];
  /**
   * S2-D41 (M-8), por defecto `true`: la búsqueda vive en estado local y nunca en la URL (documento, teléfono o
   * correo no quedan en el historial ni en los logs). Un `q` que llegue en la URL se ignora.
   */
  localQuery?: boolean;
}

const offsetSchema = z.coerce.number().int().nonnegative().catch(0);
const sortSchema = z
  .string()
  .regex(/^-?[a-z][a-z0-9_]*$/)
  .nullable()
  .catch(null);

/** `campo` es ascendente y `-campo` descendente. */
export function parseSort(raw: string | null): SortState | null {
  const value = sortSchema.parse(raw);
  if (!value) return null;
  return value.startsWith("-") ? { field: value.slice(1), direction: "desc" } : { field: value, direction: "asc" };
}

export function serializeSort(sort: SortState): string {
  return sort.direction === "desc" ? `-${sort.field}` : sort.field;
}

interface ParsedState<F extends string> {
  params: ListParams;
  q: string;
  filters: Record<F, string[]>;
  sort: SortState | null;
  page: number;
}

function parseState<F extends string>(
  search: string,
  filterNames: readonly F[],
  sorts: readonly string[] | null,
  localQuery: string | null,
): ParsedState<F> {
  const url = new URLSearchParams(search);
  const limit = clampLimit(url.get("limit"));
  const offset = offsetSchema.parse(url.get("offset") ?? 0);
  const q = localQuery ?? url.get("q")?.trim() ?? "";
  const parsedSort = parseSort(url.get("sort"));
  const sort = parsedSort && (!sorts || sorts.includes(parsedSort.field)) ? parsedSort : null;

  const params: ListParams = { limit, offset };
  if (q) params.q = q;
  if (sort) params.sort = serializeSort(sort);
  const filters = {} as Record<F, string[]>;
  for (const name of filterNames) {
    const values = url.getAll(name).filter((v) => v !== "");
    filters[name] = values;
    if (values.length > 0) params[name] = values;
  }
  return { params, q, filters, sort, page: offsetToPage(offset, limit) };
}

export function useListParams<F extends string = never>({ filters = [], sorts, localQuery = true }: ListParamsConfig<F> = {}): ListParamsApi<F> {
  const [searchParams, setSearchParams] = useSearchParams();
  const search = searchParams.toString();
  const filtersKey = filters.join("\n");
  const sortsKey = sorts ? sorts.join("\n") : null;
  // S2-D41: con localQuery el texto buscado solo vive aquí (memoria de esta pantalla).
  const [localText, setLocalText] = useState("");
  const localValue = localQuery ? localText : null;

  const state = useMemo(
    () =>
      parseState(
        search,
        (filtersKey ? filtersKey.split("\n") : []) as F[],
        sortsKey === null ? null : sortsKey.split("\n"),
        localValue,
      ),
    [search, filtersKey, sortsKey, localValue],
  );

  const update = useCallback(
    (mutate: (next: URLSearchParams) => void) => {
      setSearchParams((previous) => {
        const next = new URLSearchParams(previous);
        mutate(next);
        return next;
      });
    },
    [setSearchParams],
  );

  const { limit } = state.params;

  const setQuery = useCallback(
    (q: string) => {
      if (localQuery) {
        setLocalText(q.trim());
        // Nueva búsqueda, primera página. Sin offset (ni un q viejo) no se navega: no se suma
        // una entrada al historial por cada búsqueda.
        const current = new URLSearchParams(search);
        if (current.has("offset") || current.has("q")) {
          update((next) => {
            next.delete("offset");
            next.delete("q");
          });
        }
        return;
      }
      update((next) => {
        const value = q.trim();
        if (value) next.set("q", value);
        else next.delete("q");
        next.delete("offset");
      });
    },
    [update, localQuery, search],
  );

  const setFilter = useCallback(
    (name: F, value: string | readonly string[] | undefined) => {
      update((next) => {
        next.delete(name);
        const values = value === undefined ? [] : typeof value === "string" ? [value] : value;
        for (const v of values) if (v !== "") next.append(name, v);
        next.delete("offset");
      });
    },
    [update],
  );

  const setPage = useCallback(
    (page: number) => {
      update((next) => {
        const offset = pageToOffset(page, limit);
        if (offset > 0) next.set("offset", String(offset));
        else next.delete("offset");
      });
    },
    [update, limit],
  );

  const setLimit = useCallback(
    (value: number) => {
      update((next) => {
        next.set("limit", String(clampLimit(value)));
        next.delete("offset");
      });
    },
    [update],
  );

  const setSort = useCallback(
    (sort: SortState | null) => {
      update((next) => {
        if (sort) next.set("sort", serializeSort(sort));
        else next.delete("sort");
        next.delete("offset");
      });
    },
    [update],
  );

  const clear = useCallback(() => {
    setLocalText("");
    update((next) => {
      for (const key of ["q", "sort", "offset", ...(filtersKey ? filtersKey.split("\n") : [])]) next.delete(key);
    });
  }, [update, filtersKey]);

  return { ...state, setQuery, setFilter, setPage, setLimit, setSort, clear };
}

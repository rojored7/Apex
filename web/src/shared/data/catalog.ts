// S9-F2 (E8, S9-D40): catálogo de movimientos y benchmarks compartido. `useMovements` y `useBenchmarks` salen de features/wods/api.ts
// (features/wods las importa de aquí); las dos de «opciones» alimentan el panel de récords del atleta: movimientos activos que se
// miden en kg y benchmarks con su tipo de marca. Las dos claves cuelgan de ["movements"] y ["benchmarks"]: las escrituras del
// catálogo (features/wods) refrescan también las opciones.
import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../../core/api/client";
import { pageSchema, type Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";

export const MOVEMENT_CATEGORIES = ["weightlifting", "gymnastics", "monostructural", "other"] as const;
export const MOVEMENT_UNITS = ["kg", "reps", "m", "cal", "s"] as const;
export const BENCHMARK_SCORE_TYPES = ["time", "rounds_reps", "reps", "load"] as const;
/** Tamaño de página de las opciones (el api topa en 200) y tope de páginas: más allá se avisa en pantalla. */
const OPTIONS_LIMIT = 200;
export const OPTIONS_MAX_PAGES = 5;
const KG_UNIT = "kg";

export const movementSchema = z.object({
  id: z.string().min(1),
  name: z.string(),
  category: z.enum(MOVEMENT_CATEGORIES),
  unit: z.enum(MOVEMENT_UNITS),
  is_active: z.boolean(),
  wod_count: z.number().int().nonnegative(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const benchmarkSchema = z.object({
  id: z.string().min(1),
  name: z.string(),
  description: z.string(),
  score_type: z.enum(BENCHMARK_SCORE_TYPES),
  wod_count: z.number().int().nonnegative(),
  created_at: z.string(),
  updated_at: z.string(),
});

const movementsPageSchema = pageSchema(movementSchema);
const benchmarksPageSchema = pageSchema(benchmarkSchema);

export type CatalogMovement = z.infer<typeof movementSchema>;
export type CatalogBenchmark = z.infer<typeof benchmarkSchema>;

export interface CatalogMovementsParams {
  limit: number;
  offset: number;
  q?: string;
  category?: CatalogMovement["category"];
  active?: boolean;
}

export interface CatalogBenchmarksParams {
  limit: number;
  offset: number;
  q?: string;
  score_type?: CatalogBenchmark["score_type"];
}

export interface MovementOption {
  value: string;
  label: string;
}

export interface BenchmarkOption {
  value: string;
  label: string;
  scoreType: CatalogBenchmark["score_type"];
}

export const MOVEMENTS_QUERY_KEY = ["movements"] as const;
export const BENCHMARKS_QUERY_KEY = ["benchmarks"] as const;

async function fetchMovements(params: CatalogMovementsParams, signal: AbortSignal): Promise<Page<CatalogMovement>> {
  return parseResponse(movementsPageSchema, await api.get<unknown>("/movements", { query: listParams({ ...params }), signal }));
}

async function fetchBenchmarks(params: CatalogBenchmarksParams, signal: AbortSignal): Promise<Page<CatalogBenchmark>> {
  return parseResponse(benchmarksPageSchema, await api.get<unknown>("/benchmarks", { query: listParams({ ...params }), signal }));
}

export function useMovements(params: CatalogMovementsParams, enabled = true): UseQueryResult<Page<CatalogMovement>> {
  return useQuery({
    queryKey: [...MOVEMENTS_QUERY_KEY, params],
    queryFn: ({ signal }) => fetchMovements(params, signal),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useBenchmarks(params: CatalogBenchmarksParams, enabled = true): UseQueryResult<Page<CatalogBenchmark>> {
  return useQuery({
    queryKey: [...BENCHMARKS_QUERY_KEY, params],
    queryFn: ({ signal }) => fetchBenchmarks(params, signal),
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** Las opciones de un select del catálogo: lo que necesita quien las pinta (sin exponer la consulta entera). */
export interface CatalogOptions<T> {
  data: readonly T[] | undefined;
  isLoading: boolean;
  isSuccess: boolean;
  isError: boolean;
  /** Hay más filas en el catálogo que las páginas pedidas (OPTIONS_MAX_PAGES): la lista de opciones quedó incompleta. */
  truncated: boolean;
  refetch: () => Promise<unknown>;
}

interface OptionsPage<R> {
  items: readonly R[];
  total: number;
}

interface CollectedOptions<R> {
  items: R[];
  truncated: boolean;
}

/** Pide páginas de 200 hasta cubrir `total` o llegar al tope de páginas. */
async function collectPages<R>(fetchPage: (offset: number) => Promise<OptionsPage<R>>): Promise<CollectedOptions<R>> {
  const items: R[] = [];
  let total = 0;
  for (let page = 0; page < OPTIONS_MAX_PAGES; page += 1) {
    const offset = page * OPTIONS_LIMIT;
    if (page > 0 && offset >= total) break;
    const result = await fetchPage(offset);
    total = result.total;
    items.push(...result.items);
  }
  return { items, truncated: total > OPTIONS_MAX_PAGES * OPTIONS_LIMIT };
}

function toOptions<O>(query: UseQueryResult<{ options: O[]; truncated: boolean }>): CatalogOptions<O> {
  return {
    data: query.data?.options,
    isLoading: query.isLoading,
    isSuccess: query.isSuccess,
    isError: query.isError,
    truncated: query.data?.truncated ?? false,
    refetch: () => query.refetch(),
  };
}

/** Movimientos activos que se miden en kg, en el orden del api, como opciones de un select. */
export function useKgMovementOptions(): CatalogOptions<MovementOption> {
  const query = useQuery({
    queryKey: [...MOVEMENTS_QUERY_KEY, "options-kg"],
    queryFn: async ({ signal }) => {
      const { items, truncated } = await collectPages((offset) => fetchMovements({ limit: OPTIONS_LIMIT, offset, active: true }, signal));
      return { options: items.filter((m) => m.is_active && m.unit === KG_UNIT).map((m): MovementOption => ({ value: m.id, label: m.name })), truncated };
    },
  });
  return toOptions<MovementOption>(query);
}

/** Benchmarks del catálogo, en el orden del api, con su tipo de marca. */
export function useBenchmarkOptions(): CatalogOptions<BenchmarkOption> {
  const query = useQuery({
    queryKey: [...BENCHMARKS_QUERY_KEY, "options"],
    queryFn: async ({ signal }) => {
      const { items, truncated } = await collectPages((offset) => fetchBenchmarks({ limit: OPTIONS_LIMIT, offset }, signal));
      return { options: items.map((b): BenchmarkOption => ({ value: b.id, label: b.name, scoreType: b.score_type })), truncated };
    },
  });
  return toOptions<BenchmarkOption>(query);
}

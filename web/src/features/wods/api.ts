// S8-F1 · US-165 y US-166 (front): datos del catálogo de movimientos y benchmarks (contrato de A1 y A2).
// - useMovements(params) y useBenchmarks(params): GET paginado con Zod; mientras llega la página nueva se ve la anterior.
// - useCreateMovement, useUpdateMovement(id), useCreateBenchmark y useUpdateBenchmark(id): al salir bien invalidan su lista.
//   Las escrituras pasan por useSensitiveMutation (gcTime 0).
import { keepPreviousData, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";
import { api } from "../../core/api/client";
import { pageSchema, type Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import { useSensitiveMutation } from "../../core/api/useSensitiveMutation";
import {
  benchmarkSchema,
  movementSchema,
  type BenchmarkCreateBody,
  type BenchmarkPatchBody,
  type BenchmarkScoreType,
  type MovementCategory,
  type MovementCreateBody,
  type MovementPatchBody,
} from "./schemas";
import type { z } from "zod";

export type MovementView = z.infer<typeof movementSchema>;
export type BenchmarkView = z.infer<typeof benchmarkSchema>;

const movementsPageSchema = pageSchema(movementSchema);
const benchmarksPageSchema = pageSchema(benchmarkSchema);

export const MOVEMENTS_QUERY_KEY = ["movements"] as const;
export const BENCHMARKS_QUERY_KEY = ["benchmarks"] as const;

export interface MovementsParams {
  limit: number;
  offset: number;
  q?: string;
  category?: MovementCategory;
  active?: boolean;
}

export interface BenchmarksParams {
  limit: number;
  offset: number;
  q?: string;
  score_type?: BenchmarkScoreType;
}

const movementPath = (id: string): string => `/movements/${encodeURIComponent(id)}`;
const benchmarkPath = (id: string): string => `/benchmarks/${encodeURIComponent(id)}`;

export function useMovements(params: MovementsParams, enabled = true): UseQueryResult<Page<MovementView>> {
  return useQuery({
    queryKey: [...MOVEMENTS_QUERY_KEY, params],
    queryFn: async ({ signal }) => parseResponse(movementsPageSchema, await api.get<unknown>("/movements", { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useBenchmarks(params: BenchmarksParams, enabled = true): UseQueryResult<Page<BenchmarkView>> {
  return useQuery({
    queryKey: [...BENCHMARKS_QUERY_KEY, params],
    queryFn: async ({ signal }) => parseResponse(benchmarksPageSchema, await api.get<unknown>("/benchmarks", { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
    enabled,
  });
}

export function useCreateMovement(): UseMutationResult<MovementView, Error, MovementCreateBody> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<MovementView, Error, MovementCreateBody>({
    mutationFn: async (body) => parseResponse(movementSchema, await api.post<unknown>("/movements", { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: MOVEMENTS_QUERY_KEY });
    },
  });
}

export function useUpdateMovement(id: string): UseMutationResult<MovementView, Error, MovementPatchBody> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<MovementView, Error, MovementPatchBody>({
    mutationFn: async (body) => parseResponse(movementSchema, await api.patch<unknown>(movementPath(id), { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: MOVEMENTS_QUERY_KEY });
    },
  });
}

export function useCreateBenchmark(): UseMutationResult<BenchmarkView, Error, BenchmarkCreateBody> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<BenchmarkView, Error, BenchmarkCreateBody>({
    mutationFn: async (body) => parseResponse(benchmarkSchema, await api.post<unknown>("/benchmarks", { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: BENCHMARKS_QUERY_KEY });
    },
  });
}

export function useUpdateBenchmark(id: string): UseMutationResult<BenchmarkView, Error, BenchmarkPatchBody> {
  const queryClient = useQueryClient();
  return useSensitiveMutation<BenchmarkView, Error, BenchmarkPatchBody>({
    mutationFn: async (body) => parseResponse(benchmarkSchema, await api.patch<unknown>(benchmarkPath(id), { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: BENCHMARKS_QUERY_KEY });
    },
  });
}

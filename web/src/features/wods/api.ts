// S8-F1 · US-165 y US-166 (front): datos del catálogo de movimientos y benchmarks (contrato de A1 y A2).
// - Las lecturas useMovements y useBenchmarks viven en shared/data/catalog.ts (S9-F2, E8); aquí quedan los tipos de los filtros y las escrituras.
// - useCreateMovement, useUpdateMovement(id), useCreateBenchmark y useUpdateBenchmark(id): al salir bien invalidan su lista.
//   Las escrituras pasan por useSensitiveMutation (gcTime 0).
import { useQueryClient, type UseMutationResult } from "@tanstack/react-query";
import { api } from "../../core/api/client";
import { parseResponse } from "../../core/api/response";
import { useSensitiveMutation } from "../../core/api/useSensitiveMutation";
import { BENCHMARKS_QUERY_KEY, MOVEMENTS_QUERY_KEY, type CatalogBenchmarksParams, type CatalogMovementsParams } from "../../shared/data/catalog";
import {
  benchmarkSchema,
  movementSchema,
  type BenchmarkCreateBody,
  type BenchmarkPatchBody,
  type MovementCreateBody,
  type MovementPatchBody,
} from "./schemas";
import type { z } from "zod";

export type MovementView = z.infer<typeof movementSchema>;
export type BenchmarkView = z.infer<typeof benchmarkSchema>;

export type MovementsParams = CatalogMovementsParams;
export type BenchmarksParams = CatalogBenchmarksParams;

const movementPath = (id: string): string => `/movements/${encodeURIComponent(id)}`;
const benchmarkPath = (id: string): string => `/benchmarks/${encodeURIComponent(id)}`;

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

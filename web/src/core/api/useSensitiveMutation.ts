// Fase 4 del Sprint 3 (M6): la garantía de S3-D52 (M-9) en un solo lugar. Antes cada hook repetía
// `gcTime: 0`, un `resetRef` y un efecto; un hook nuevo que lo olvidara dejaba un monto, un motivo o
// una contraseña en la caché de mutaciones.
// - `gcTime: 0`: la mutación terminada no se queda en la caché.
// - `reset()` en `onSettled`, salga bien o mal: el observador suelta `variables`, `data` y `error`.
//   `mutateAsync` sigue entregando el resultado (o el rechazo) a quien llama; los mensajes de error
//   salen de ese rechazo, nunca de `mutation.error`.
// - `tests/lint/sensitive-mutations.test.ts` exige que toda mutación de las features pase por aquí,
//   salvo una lista blanca explícita de las que no llevan valores sensibles o leen su estado a
//   propósito.
import { useMutation, type UseMutationOptions, type UseMutationResult } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

/** Las opciones de useMutation sin `gcTime` ni `onSettled`: los fija este hook. */
export type SensitiveMutationOptions<TData, TError, TVariables> = Omit<UseMutationOptions<TData, TError, TVariables>, "gcTime" | "onSettled">;

export function useSensitiveMutation<TData, TError = Error, TVariables = void>(
  options: SensitiveMutationOptions<TData, TError, TVariables>,
): UseMutationResult<TData, TError, TVariables> {
  // reset() de la propia mutación, para llamarlo al terminar. Se guarda en un efecto: un ref no se
  // escribe durante el render.
  const resetRef = useRef<() => void>(() => undefined);
  const mutation = useMutation<TData, TError, TVariables>({
    ...options,
    gcTime: 0,
    onSettled: () => {
      resetRef.current();
    },
  });
  const { reset } = mutation;
  useEffect(() => {
    resetRef.current = reset;
  }, [reset]);
  return mutation;
}

// S3-F4 · US-095 y US-097 (front): registrar y anular pagos.
// - useRegisterPayment(membershipId): POST /memberships/{id}/payments con PaymentIn → 201 PaymentOut.
// - useVoidPayment(): POST /payments/{id}/void con { reason } → 200 PaymentOut. Un 409 o un 404
//   dicen que lo que se ve quedó viejo (otra persona lo anuló): se relee ["payments"].
// - Las dos llevan un monto, una referencia o un motivo: `gcTime: 0` y `reset()` en `onSettled`
//   (S3-D52, M-9), así la caché de mutaciones no conserva `variables` después de responder. Al salir
//   bien invalidan pagos, el resumen de pagos, membresías, el resumen de membresías y socios (estado
//   en la lista), sin esperar las relecturas. Sin reintentos: una escritura nunca se repite sola.
// - usePayment(id): GET /payments/{id} (B8) con la clave ["payments", "detail", id], para el detalle
//   de S3-F6 y para releer un pago tras un 409.
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api } from "../../core/api/client";
import { isApiError } from "../../core/api/errors";
import { parseResponse } from "../../core/api/response";
import { HTTP_CONFLICT, HTTP_NOT_FOUND } from "../../core/api/status";
import { paymentDetailSchema, paymentOutSchema, type PaymentDetailView, type PaymentInBody, type PaymentOutView } from "./schemas";
export { PAYMENT_METHODS_QUERY_KEY, usePaymentMethods } from "../../shared/data/paymentMethods";

/** Lo que deja viejo registrar o anular un pago. */
export const PAYMENT_WRITE_INVALIDATES = [["payments"], ["payments-summary"], ["memberships"], ["memberships-summary"], ["members"]] as const;
export const PAYMENTS_QUERY_KEY = ["payments"] as const;

export interface RegisterPayment {
  /** Registra con este cuerpo; rechaza con el ApiError del api. */
  register: (body: PaymentInBody) => Promise<PaymentOutView>;
  isPending: boolean;
}

export interface VoidPaymentInput {
  id: string;
  /** Ya recortado (voidPaymentSchema). */
  reason: string;
}

export interface VoidPayment {
  voidPayment: (input: VoidPaymentInput) => Promise<PaymentOutView>;
  isPending: boolean;
}

export function paymentQueryKey(id: string): readonly ["payments", "detail", string] {
  return ["payments", "detail", id];
}

export function useRegisterPayment(membershipId: string | null): RegisterPayment {
  const queryClient = useQueryClient();
  const resetRef = useRef<() => void>(() => undefined);
  const mutation = useMutation<PaymentOutView, Error, PaymentInBody>({
    mutationFn: async (body) => {
      if (membershipId === null) throw new Error("useRegisterPayment: falta la membresía");
      return parseResponse(paymentOutSchema, await api.post<unknown>(`/memberships/${encodeURIComponent(membershipId)}/payments`, { body }));
    },
    gcTime: 0,
    onSuccess: () => {
      for (const queryKey of PAYMENT_WRITE_INVALIDATES) void queryClient.invalidateQueries({ queryKey });
    },
    onSettled: () => {
      resetRef.current();
    },
  });
  const { reset, mutateAsync, isPending } = mutation;
  // reset() de la propia mutación, para llamarlo al terminar: un ref no se escribe durante el render.
  useEffect(() => {
    resetRef.current = reset;
  }, [reset]);
  return { register: mutateAsync, isPending };
}

export function useVoidPayment(): VoidPayment {
  const queryClient = useQueryClient();
  const resetRef = useRef<() => void>(() => undefined);
  const mutation = useMutation<PaymentOutView, Error, VoidPaymentInput>({
    mutationFn: async ({ id, reason }) => parseResponse(paymentOutSchema, await api.post<unknown>(`/payments/${encodeURIComponent(id)}/void`, { body: { reason } })),
    gcTime: 0,
    onSuccess: () => {
      for (const queryKey of PAYMENT_WRITE_INVALIDATES) void queryClient.invalidateQueries({ queryKey });
    },
    onError: (error) => {
      if (isApiError(error) && (error.status === HTTP_CONFLICT || error.status === HTTP_NOT_FOUND)) void queryClient.invalidateQueries({ queryKey: PAYMENTS_QUERY_KEY });
    },
    onSettled: () => {
      resetRef.current();
    },
  });
  const { reset, mutateAsync, isPending } = mutation;
  useEffect(() => {
    resetRef.current = reset;
  }, [reset]);
  return { voidPayment: mutateAsync, isPending };
}

export function usePayment(id: string | null): UseQueryResult<PaymentDetailView> {
  return useQuery({
    queryKey: paymentQueryKey(id ?? ""),
    queryFn: async ({ signal }) => parseResponse(paymentDetailSchema, await api.get<unknown>(`/payments/${encodeURIComponent(id ?? "")}`, { signal })),
    enabled: id !== null,
  });
}

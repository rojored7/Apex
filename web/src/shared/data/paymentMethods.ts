// S3-F3 (S3-D65, condición 8): medios de pago con su etiqueta (US-056, D24, D25). Los usan la
// venta con primer pago (features/memberships) y, desde S3-F4, el registro de pagos.
// - usePaymentMethods(): GET /payments/methods → `{ items }` (D25: nunca un arreglo suelto), en el
//   orden del api. Cambia poco (lo edita el admin en Configuración): `staleTime` de 5 minutos.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../../core/api/client";
import { parseResponse } from "../../core/api/response";
import { paymentMethodCodeSchema } from "./schemas/payment";

export const PAYMENT_METHODS_STALE_MS = 5 * 60 * 1_000;

// Clave propia (no bajo ["payments"]): invalidar los pagos tras una venta no relee los medios.
export const PAYMENT_METHODS_QUERY_KEY = ["payment-methods"] as const;

export const paymentMethodSchema = z.object({
  code: paymentMethodCodeSchema,
  label: z.string().min(1),
  hint: z.string(),
});
export type PaymentMethodView = z.infer<typeof paymentMethodSchema>;

export const paymentMethodsSchema = z.object({ items: z.array(paymentMethodSchema) });

export function usePaymentMethods(): UseQueryResult<PaymentMethodView[]> {
  return useQuery({
    queryKey: PAYMENT_METHODS_QUERY_KEY,
    queryFn: async ({ signal }) => parseResponse(paymentMethodsSchema, await api.get<unknown>("/payments/methods", { signal })).items,
    staleTime: PAYMENT_METHODS_STALE_MS,
  });
}

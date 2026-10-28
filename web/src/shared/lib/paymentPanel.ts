// S3-F4 (S3-D65, condición 8): el panel "Registrar pago" se abre desde cualquier pantalla del panel
// con la URL, sin que una feature importe a otra. PanelShell lo monta una sola vez (E10) cuando la
// URL lo pide; las pantallas solo arman el enlace.
// - `?pago=<membresía>`: el panel con esa membresía elegida (Registrar saldo, Registrar pago nuevo).
// - `?pago=nuevo&socio=<socio>`: un pago nuevo para ese socio; `?pago=nuevo` sin socio, para buscarlo.
// - Los demás parámetros de la pantalla (filtros, página) se conservan al abrir y al cerrar. Cerrar un
//   pago nuevo quita también su `socio`; cerrar el de una membresía no toca un `socio` de la pantalla
//   (la venta usa `?socio=` para fijar el socio).
// - Un valor que no es un UUID se ignora: no abre nada (`pago`) o abre el panel sin socio (`socio`).
// - La precarga desde una anulación (valor y medio) viaja en el estado de la navegación, nunca en la
//   URL; se valida al leerla (un estado ajeno no precarga nada).
import { z } from "zod";
import { COP_MAX, COP_MIN } from "../data/schemas/money";
import { PAYMENT_METHOD_CODES, type PaymentMethodCode } from "../data/schemas/payment";
import { isUuid } from "./ids";

export const PAYMENT_PANEL_PARAM = "pago";
export const PAYMENT_PANEL_MEMBER_PARAM = "socio";
export const NEW_PAYMENT = "nuevo";


export type PaymentPanelTarget = { kind: "membership"; membershipId: string } | { kind: "new"; memberId: string | null };

/** Lo que pide quien abre el panel: una membresía, o un socio (o ninguno) para un pago nuevo. */
export type PaymentPanelRequest = { membershipId: string } | { memberId: string | null };

export interface PanelLocation {
  pathname: string;
  search: string;
}

export interface PaymentPrefill {
  amountCop: number;
  method: PaymentMethodCode;
}

export interface PaymentPanelState {
  paymentPrefill: PaymentPrefill;
}

const prefillStateSchema = z.object({
  paymentPrefill: z.object({
    amountCop: z.number().int().min(COP_MIN).max(COP_MAX),
    method: z.enum(PAYMENT_METHOD_CODES),
  }),
});

function hrefOf(pathname: string, params: URLSearchParams): string {
  const query = params.toString();
  return query === "" ? pathname : `${pathname}?${query}`;
}

/** El enlace que abre el panel sobre la pantalla actual, conservando sus demás parámetros. */
export function paymentPanelHref(location: PanelLocation, request: PaymentPanelRequest): string {
  const params = new URLSearchParams(location.search);
  if ("membershipId" in request) {
    // El `socio` de un pago nuevo abierto antes era del panel, no de la pantalla.
    if (params.get(PAYMENT_PANEL_PARAM) === NEW_PAYMENT) params.delete(PAYMENT_PANEL_MEMBER_PARAM);
    params.set(PAYMENT_PANEL_PARAM, request.membershipId);
    return hrefOf(location.pathname, params);
  }
  params.set(PAYMENT_PANEL_PARAM, NEW_PAYMENT);
  if (request.memberId === null) params.delete(PAYMENT_PANEL_MEMBER_PARAM);
  else params.set(PAYMENT_PANEL_MEMBER_PARAM, request.memberId);
  return hrefOf(location.pathname, params);
}

/** Qué panel pide la URL, o null si no pide ninguno. */
export function readPaymentPanel(search: string): PaymentPanelTarget | null {
  const params = new URLSearchParams(search);
  const value = params.get(PAYMENT_PANEL_PARAM);
  if (value === null) return null;
  if (value === NEW_PAYMENT) {
    const member = params.get(PAYMENT_PANEL_MEMBER_PARAM);
    return { kind: "new", memberId: member !== null && isUuid(member) ? member : null };
  }
  return isUuid(value) ? { kind: "membership", membershipId: value } : null;
}

/** La misma pantalla sin el panel. */
export function closePaymentPanelHref(location: PanelLocation): string {
  const params = new URLSearchParams(location.search);
  if (params.get(PAYMENT_PANEL_PARAM) === NEW_PAYMENT) params.delete(PAYMENT_PANEL_MEMBER_PARAM);
  params.delete(PAYMENT_PANEL_PARAM);
  return hrefOf(location.pathname, params);
}

/** El estado de la navegación que precarga el panel (valor y medio de un pago anulado). */
export function paymentPanelState(prefill: PaymentPrefill): PaymentPanelState {
  return { paymentPrefill: { amountCop: prefill.amountCop, method: prefill.method } };
}

/** La precarga del estado de la navegación, o null si no hay o no tiene la forma esperada. */
export function readPaymentPrefill(state: unknown): PaymentPrefill | null {
  const parsed = prefillStateSchema.safeParse(state);
  return parsed.success ? parsed.data.paymentPrefill : null;
}

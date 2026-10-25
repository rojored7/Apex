// S3-F3 (S3-D65): reglas de entrada de un pago que comparten la venta con primer pago
// (features/memberships) y el registro de pagos (features/payments, S3-F4). Ninguna feature
// importa de otra: lo común vive aquí.
// - Medios fijos (D24): cash, nequi y breb; las etiquetas salen de GET /payments/methods.
// - Referencia (D17, S3-D50, M-7): opcional, recortada, de 1 a 64 caracteres y con el patrón de
//   comprobante del api (`REFERENCE_PATTERN` de payments/rules.py): letras, números, espacio y
//   . _ / # -, empezando por letra o número. Así no cabe un correo ni un texto libre.
import { z } from "zod";
import type { components } from "../../../core/api/types";

export type PaymentInBody = components["schemas"]["PaymentIn"];
export type PaymentMethodCode = PaymentInBody["method"];

export const PAYMENT_METHOD_CODES = ["cash", "nequi", "breb"] as const satisfies readonly PaymentMethodCode[];

/** Medios en los que el diseño pide la referencia (Membresia_Vender.html: "Referencia (Nequi / Bre-B)"). */
export const METHODS_WITH_REFERENCE: ReadonlySet<PaymentMethodCode> = new Set<PaymentMethodCode>(["nequi", "breb"]);

export const REFERENCE_MAX = 64;
export const REFERENCE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9 ._/#-]{0,63}$/;

/** M-7 (S3-D50): aviso bajo la referencia y bajo cualquier motivo. */
export const SENSITIVE_TEXT_WARNING = "No escribas teléfonos, documentos ni datos de salud.";

export const REFERENCE_MESSAGES = {
  tooLong: `La referencia admite hasta ${String(REFERENCE_MAX)} caracteres.`,
  pattern: "Escribe solo el número de la transacción: letras, números, espacios y . _ / # -.",
} as const;

/** La referencia tal como se envía: recortada; vacía es `undefined`. */
export function cleanReference(value: string): string | undefined {
  const trimmed = value.trim();
  return trimmed === "" ? undefined : trimmed;
}

/** Mensaje de error de una referencia escrita en el formulario, o null si sirve (vacía sirve). */
export function referenceError(value: string): string | null {
  const reference = cleanReference(value);
  if (reference === undefined) return null;
  if (Array.from(reference).length > REFERENCE_MAX) return REFERENCE_MESSAGES.tooLong;
  return REFERENCE_PATTERN.test(reference) ? null : REFERENCE_MESSAGES.pattern;
}

export const paymentMethodCodeSchema = z.enum(PAYMENT_METHOD_CODES);

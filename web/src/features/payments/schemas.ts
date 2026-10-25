// S3-F3 · mínimo de features/payments (S3-F4 lo amplía con paymentRowSchema, paymentDetailSchema,
// registerPaymentSchema y voidPaymentSchema). Las reglas de entrada de un pago las comparte la
// venta con primer pago, así que viven en shared/data/schemas/payment.ts (S3-D65: ninguna feature
// importa de otra) y aquí se reexportan.
export {
  cleanReference,
  METHODS_WITH_REFERENCE,
  PAYMENT_METHOD_CODES,
  REFERENCE_MAX,
  REFERENCE_PATTERN,
  referenceError,
  SENSITIVE_TEXT_WARNING,
  type PaymentInBody,
  type PaymentMethodCode,
} from "../../shared/data/schemas/payment";
export { paymentMethodSchema, paymentMethodsSchema, type PaymentMethodView } from "../../shared/data/paymentMethods";

// S3-F3 · mínimo de features/payments (S3-F4 lo amplía con useRegisterPayment, useVoidPayment y
// usePayment). usePaymentMethods lo comparte la venta: vive en shared/data/paymentMethods.ts
// (S3-D65) y aquí se reexporta.
export { PAYMENT_METHODS_QUERY_KEY, usePaymentMethods } from "../../shared/data/paymentMethods";

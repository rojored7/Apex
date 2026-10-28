// Fase 4 del Sprint 3 (M4): el saldo de una membresía (Q5, S3-D41). Manda el servidor: el saldo sale
// de `agreed_price_cop - paid_cop` (B7) y el 409 `payment_exceeds_balance` confirma lo mismo bajo el
// candado. Un pago mayor al saldo se confirma y no deja saldo a favor. Lo usan la venta con primer
// pago (features/memberships) y el panel de pagos (features/payments); antes cada una tenía su copia.

/** Lo que falta para el precio; nunca negativo. */
export function balance(price: number, paid: number): number {
  return Math.max(price - paid, 0);
}

/** El saldo de una fila de membresía. */
export function balanceOf(membership: { agreed_price_cop: number; paid_cop: number }): number {
  return balance(membership.agreed_price_cop, membership.paid_cop);
}

/** ¿El pago supera el saldo (y hay que confirmarlo)? */
export function exceedsBalance(price: number, paid: number, amount: number): boolean {
  return amount > balance(price, paid);
}

/** Cuánto supera el pago al saldo, o 0. */
export function excessOver(price: number, paid: number, amount: number): number {
  return Math.max(amount - balance(price, paid), 0);
}

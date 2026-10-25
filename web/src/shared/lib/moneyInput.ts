// S3-F3: un monto en COP mientras se escribe ("120000" → "$ 120.000"). Nació en S2-F7 como
// `priceInputText` de features/plans/schemas.ts (revisión M1) y se mueve aquí porque también lo usa
// el valor recibido de la venta (features/memberships); plans lo reexporta. Se reformatea un entero
// bien escrito ("120000", "$ 1.200") o un dígito escrito o borrado sobre un monto ya formateado. Lo
// demás (una coma, un punto decimal como "1200.50", letras) queda como está y la validación lo
// explica: nunca se convierte un decimal en otro monto.
import { formatCop, parseCop } from "../../core/i18n/format";

/** Lo que se reformatea mientras se escribe: dígitos con separadores de miles y el "$". */
const MONEY_TYPING = /^[\d\s.$]*$/;
/** Más dígitos que esto no es un entero seguro y no tiene sentido como monto. */
const MONEY_MAX_DIGITS = 15;

const digitsOf = (text: string): string => text.replace(/\D/g, "");

/**
 * ¿Es un solo dígito escrito o un carácter borrado sobre un monto ya formateado (o vacío)? Así
 * "$ 120.0005" (se escribió un 5) y "$ 1.20" (se borró un 0) se reformatean, pero un punto
 * escrito a mano ("$ 1.200.") o un texto pegado no.
 */
function isDigitEdit(previous: string, raw: string): boolean {
  if (previous !== "" && parseCop(previous) === null) return false;
  if (raw.length === previous.length - 1) return true;
  return raw.length === previous.length + 1 && digitsOf(raw).length === digitsOf(previous).length + 1;
}

/** El monto como se muestra mientras se escribe: "120000" → "$ 120.000"; "" → "". */
export function moneyInputText(raw: string, previous = ""): string {
  if (!MONEY_TYPING.test(raw)) return raw;
  const digits = digitsOf(raw);
  if (digits === "") return "";
  if (digits.length > MONEY_MAX_DIGITS) return raw;
  if (parseCop(raw) === null && !isDigitEdit(previous, raw)) return raw;
  return formatCop(Number(digits));
}

// S3-F3 (S3-D65, condición 8): esquemas de dinero que comparten varias features (membresías,
// pagos). Dinero siempre entero en COP (regla de datos 1, RN-01), de 1 a 1.000.000.000 como
// `amount_cop` del api (`StrictInt`, `ge=1`, `le=MAX_AMOUNT_COP`, D17).
import { z } from "zod";

export const COP_MIN = 1;
export const COP_MAX = 1_000_000_000;

/** Monto entero en COP, de 1 a 1.000.000.000. */
export const copInt = z.number().int().min(COP_MIN).max(COP_MAX);

/** Un monto entero no negativo que devuelve el api (precio pactado, pagado, saldo). */
export const copAmount = z.number().int().nonnegative();

// S4A-F3 · US-108 a US-110 (front): la forma de GET /dashboard (DashboardOut y MovementOut de
// api/src/app/modules/dashboard/schemas.py), validada con Zod antes de usarla.
// - Los cinco conteos de membresías son enteros no negativos.
// - `income_month_cop` es entero o null: null para el coach, que no ve finanzas (S4A-D118).
// - Los futuros (asistencia, sesiones, avisos, sin consentimiento y WOD) son `nullable()`, no
//   `optional()` (S4A-D33): el api los manda siempre, en null hasta su versión. Una clave ausente es
//   una respuesta inválida, no un cero.
// - Revisión de seguridad de F3 (M1, M2, L5): los dos objetos son `.strict()` (una clave de más, como
//   `before` o `after` de la auditoría, es una respuesta inválida y nunca se pinta), `member_id` y
//   `record_id` son UUID o null, e ingresos no son negativos.
// - `last_movements` trae como máximo diez frases ya armadas por el servidor; el front las pinta como
//   texto (nunca HTML).
import { z } from "zod";
import { isUuid } from "../../shared/lib/ids";

/** Las tres tablas que alimentan los últimos movimientos (S4A-D28). */
export const MOVEMENT_TABLES = ["members.members", "memberships.memberships", "payments.payments"] as const;

/** Máximo de movimientos que manda el api (LAST_MOVEMENTS_LIMIT). */
export const LAST_MOVEMENTS_LIMIT = 10;

const count = z.number().int().nonnegative();
const futureCount = count.nullable();
const CIVIL_DATE = /^\d{4}-\d{2}-\d{2}$/;
const CIVIL_MONTH = /^\d{4}-\d{2}$/;
/** Revisión de seguridad de F3 (M2): un id que no es UUID nunca llega a una URL (`/socios/:id`). */
const uuidOrNull = z.string().refine(isUuid).nullable();

export const movementSchema = z
  .object({
    seq: z.number().int().positive(),
    at: z.string().min(1),
    table_name: z.enum(MOVEMENT_TABLES),
    record_id: uuidOrNull,
    member_id: uuidOrNull,
    phrase: z.string(),
  })
  .strict();

export const dashboardSchema = z
  .object({
    today: z.string().regex(CIVIL_DATE),
    members_active: count,
    members_expiring: count,
    members_expired: count,
    members_frozen: count,
    members_pending_payment: count,
    income_month: z.string().regex(CIVIL_MONTH),
    income_month_cop: z.number().int().nonnegative().nullable(),
    attendance_week: futureCount,
    sessions_today: futureCount,
    notifications_today: futureCount,
    members_without_consent: futureCount,
    wod_today: z.string().nullable(),
    last_movements: z.array(movementSchema).max(LAST_MOVEMENTS_LIMIT),
  })
  .strict();

export type MovementView = z.infer<typeof movementSchema>;
export type DashboardView = z.infer<typeof dashboardSchema>;

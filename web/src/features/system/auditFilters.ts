// S4A-F1 · US-102 (S4A-D31, S4A-D58, S4A-D106): los filtros de /sistema/auditoria, de la URL al api.
// - En la URL quedan `from` y `to` como días civiles de Bogotá ("AAAA-MM-DD", lo que se ve en el
//   campo), `table`, `user_id`, `action`, `record_id`, `subject_member_id`, `limit`, `offset` y el
//   `seq` del detalle. La búsqueda vive en memoria (S2-D41) y viaja como `q`: un `q` de la URL se ignora.
// - toApiParams construye con URLSearchParams y solo deja pasar lo que el api acepta: UUID para los
//   ids, `table` con el patrón del api y en la lista de tablas auditadas, `action` de la lista y fechas
//   reales. El rango va en UTC como `[from, to)`: "Hasta 20 oct" incluye todo el 20 de octubre. Un
//   rango invertido no viaja. `record_id` sin `table` tampoco (el api da 422, S4A-D106 a).
// - `offset` es múltiplo de `limit` y no pasa de MAX_AUDIT_OFFSET (S4A-D45).
// - parseSeq: `?seq=` solo vale si es un entero seguro >= 1 escrito en decimal (S4A-D58).
import { addDaysCivil, bogotaDayEndUtc, bogotaDayStartUtc } from "../../core/i18n/format";
import { clampLimit } from "../../core/api/query";
import { SYSTEM_USER_ID } from "../../shared/lib/audit-labels";
import { isUuid } from "../../shared/lib/ids";
import { AUDIT_ACTIONS, type AuditAction } from "./schemas";

export const AUDIT_FILTERS = ["from", "to", "table", "user_id", "action", "record_id", "subject_member_id"] as const;
export type AuditFilter = (typeof AUDIT_FILTERS)[number];
export const SEQ_PARAM = "seq";
/** Tope de `offset` del api (S4A-D45). */
export const MAX_AUDIT_OFFSET = 100_000;
/** Patrón de `table` del api (audit/schemas.py, TABLE_PATTERN). */
const TABLE_PATTERN = /^[a-z_]{1,63}\.[a-z_]{1,63}$/;
const DECIMAL = /^[1-9]\d*$/;

export interface AuditUrlFilters {
  from: string;
  to: string;
  table: string;
  user_id: string;
  action: AuditAction | "";
  record_id: string;
  subject_member_id: string;
}

// Las tablas que audita el api hoy (AUDITABLE_TABLES de api/src/app/modules/audit/queries.py). S9-V8: la lista se había
// quedado en la de v0.1; ahora trae avisos (v0.2), adjuntos y llaves (v0.3), clases (v0.4), WODs y resultados (v0.5) y
// medidas y récords (v0.6). Una tabla fuera de la lista se descarta de la URL.
export const AUDIT_TABLES: readonly { value: string; label: string }[] = [
  { value: "members.members", label: "Socio" },
  { value: "members.member_channel_preferences", label: "Canales de aviso del socio" },
  { value: "attachments.attachments", label: "Adjunto" },
  { value: "classes.class_slots", label: "Franja del horario" },
  { value: "classes.class_sessions", label: "Clase" },
  { value: "classes.attendance", label: "Asistencia" },
  { value: "wods.movements", label: "Movimiento" },
  { value: "wods.benchmarks", label: "Benchmark" },
  { value: "wods.wods", label: "WOD" },
  { value: "wods.wod_movements", label: "Movimiento del WOD" },
  { value: "results.wod_results", label: "Resultado" },
  { value: "athletes.body_metrics", label: "Medición" },
  { value: "athletes.personal_records", label: "Récord" },
  { value: "notifications.notification_templates", label: "Plantilla de aviso" },
  { value: "notifications.notification_rules", label: "Regla de aviso" },
  { value: "notifications.notifications", label: "Aviso" },
  { value: "crypto.crypto_keys", label: "Llave" },
  { value: "memberships.memberships", label: "Membresía" },
  { value: "memberships.membership_freezes", label: "Congelamiento" },
  { value: "payments.payments", label: "Pago" },
  { value: "plans.plans", label: "Plan" },
  { value: "auth.users", label: "Usuario del equipo" },
  { value: "auth.one_time_tokens", label: "Enlace de acceso" },
  { value: "settings.settings_sections", label: "Configuración" },
  { value: "audit.verifications", label: "Verificación de la cadena" },
];

export const AUDIT_ACTION_LABELS: Readonly<Record<AuditAction, string>> = {
  insert: "Crear",
  update: "Cambiar",
  delete: "Borrar",
  reveal: "Descifrar dato",
  export: "Exportar",
  download: "Descargar adjunto",
  login: "Iniciar sesión",
  verify: "Verificar cadena",
};

const KNOWN_TABLES: ReadonlySet<string> = new Set(AUDIT_TABLES.map((t) => t.value));

const isAction = (value: string): value is AuditAction => (AUDIT_ACTIONS as readonly string[]).includes(value);
const isTable = (value: string): boolean => TABLE_PATTERN.test(value) && KNOWN_TABLES.has(value);
/** Una fecha civil real "AAAA-MM-DD", o "" si no lo es. */
const civilOrEmpty = (value: string | null): string => (value !== null && addDaysCivil(value, 0) === value ? value : "");
const uuidOrEmpty = (value: string | null): string => (value !== null && isUuid(value) ? value : "");

const asParams = (search: string | URLSearchParams): URLSearchParams => (typeof search === "string" ? new URLSearchParams(search) : search);

/** Los filtros válidos de la URL ("" si falta o no es válido). */
export function readAuditFilters(search: string | URLSearchParams): AuditUrlFilters {
  const url = asParams(search);
  const table = url.get("table") ?? "";
  const action = url.get("action") ?? "";
  return {
    from: civilOrEmpty(url.get("from")),
    to: civilOrEmpty(url.get("to")),
    table: isTable(table) ? table : "",
    user_id: uuidOrEmpty(url.get("user_id")),
    action: isAction(action) ? action : "",
    record_id: uuidOrEmpty(url.get("record_id")),
    subject_member_id: uuidOrEmpty(url.get("subject_member_id")),
  };
}

function offsetFor(raw: string | null, limit: number): number {
  const value = raw !== null && /^\d+$/.test(raw) ? Number(raw) : 0;
  const capped = Math.min(value, MAX_AUDIT_OFFSET);
  return Math.floor(capped / limit) * limit;
}

/** Los parámetros de GET /audit: solo lo válido, con los nombres del api. */
export function toApiParams(search: string | URLSearchParams, q = ""): URLSearchParams {
  const url = asParams(search);
  const filters = readAuditFilters(url);
  const limit = clampLimit(url.get("limit"));
  const out = new URLSearchParams({ limit: String(limit), offset: String(offsetFor(url.get("offset"), limit)) });
  const text = q.trim();
  if (text) out.set("q", text);
  const inverted = filters.from !== "" && filters.to !== "" && filters.to < filters.from;
  const from = filters.from && !inverted ? bogotaDayStartUtc(filters.from) : null;
  const to = filters.to && !inverted ? bogotaDayEndUtc(filters.to) : null;
  if (from) out.set("from", from);
  if (to) out.set("to", to);
  if (filters.table) out.set("table", filters.table);
  if (filters.user_id) out.set("user_id", filters.user_id);
  if (filters.action) out.set("action", filters.action);
  if (filters.record_id && filters.table) out.set("record_id", filters.record_id);
  if (filters.subject_member_id) out.set("subject_member_id", filters.subject_member_id);
  return out;
}

/** El `seq` del detalle si es un entero seguro >= 1 escrito en decimal; si no, null. */
export function parseSeq(raw: string | null): number | null {
  if (raw === null || !DECIMAL.test(raw)) return null;
  const value = Number(raw);
  return Number.isSafeInteger(value) && value >= 1 ? value : null;
}

/** "Socio", "Pago"…; una tabla desconocida se muestra tal cual. */
export function tableLabel(table: string): string {
  return AUDIT_TABLES.find((t) => t.value === table)?.label ?? table;
}

/** "Crear", "Cambiar"…; una acción desconocida se muestra tal cual. */
export function actionLabel(action: string): string {
  return isAction(action) ? AUDIT_ACTION_LABELS[action] : action;
}

/** Opción del selector de usuario y nombre del usuario técnico (N-15) en la lista. */
export const SYSTEM_USER_LABEL = "Sistema (worker)";
/** Una fila cuyo `user_id` ya no está en auth.users: no se inventa un nombre. */
export const UNKNOWN_USER_LABEL = "Usuario sin cuenta";

/** Quién hizo la acción: el correo, "Sistema (worker)" o "Usuario sin cuenta". */
export function auditUserLabel(row: { user_id: string; user_email: string | null }): string {
  if (row.user_id === SYSTEM_USER_ID) return SYSTEM_USER_LABEL;
  return row.user_email ?? UNKNOWN_USER_LABEL;
}

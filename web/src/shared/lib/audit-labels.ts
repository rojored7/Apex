// US-066 T3: etiquetas del historial y del valor enmascarado.
// - El enmascarado lo calcula el api al leer la ficha (N-01): maskValue no enmascara nada,
//   solo muestra el texto del api o "Sin dato".
// - Un campo cifrado (lista de v0.1 o un valor con prefijo "apx1.") nunca se muestra: se
//   resume como "dato cifrado modificado". Ningún texto de aquí contiene un blob.
// S4A-F2 (S4A-D32): GET /members/{id}/audit (MemberHistoryItem de S4A-B5) no trae valores: solo
// `fields` (nombres de campo), así que AuditEntryView gana `fields`, `phrase` y `purpose`; la feature
// members la arma (features/members/lib/historyEntries.ts). `before`/`after` quedan para quien sí los
// tenga; ninguna pantalla los recibe hoy del api (la auditoría del admin descarta los suyos, S4A-F1).
import { formatCop } from "../../core/i18n/format";

/** Entrada de auditoría tal como la entregará GET /members/{id}/audit (US-106). */
export interface AuditEntryView {
  id: string;
  /** Instante UTC ISO 8601. */
  at: string;
  actor_id: string;
  actor_name?: string | null;
  /** Tabla: "members", "memberships", "payments"... */
  entity: string;
  /** insert, update, delete, reveal, export, download, login, verify (N-08). */
  action: string;
  before?: Readonly<Record<string, unknown>> | null;
  after?: Readonly<Record<string, unknown>> | null;
  /** S4A-D32: nombres de los campos cambiados o del revelado, sin valores (GET /members/{id}/audit). */
  fields?: readonly string[];
  /** S4A-D32: la frase de la entrada ("Ana editó teléfono y correo"); HistoryAside la pinta en fuerte. */
  phrase?: string;
  /** S4A-D50: propósito de un `reveal` automático (`notify`, `auth_link`); null en el interactivo. */
  purpose?: string | null;
}

export type SensitiveKind = "document" | "phone" | "email" | "birth_date" | "emergency_contact";

/** Usuario técnico (N-15); nunca autentica y en pantalla es "Sistema". */
export const SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001";

const BLOB_PREFIX = "apx1.";
/** S4A-F2 (S4A-D50): etiqueta de un `reveal` automático (con `purpose`: notify, auth_link). */
export const PURPOSE_LABEL = "automático (aviso)";
/** Texto cuando el campo no tiene valor. */
export const NO_VALUE_LABEL = "Sin dato";

export const ACTION_LABELS: Readonly<Record<string, string>> = Object.freeze({
  insert: "creó",
  update: "modificó",
  delete: "eliminó",
  reveal: "mostró",
  export: "exportó",
  download: "descargó",
  login: "inició sesión",
  verify: "verificó",
});

export const ENTITY_LABELS: Readonly<Record<string, string>> = Object.freeze({
  members: "Socio",
  memberships: "Membresía",
  payments: "Pago",
  // S4A-F2 (S4A-D32): los nombres reales `esquema.tabla` de GET /members/{id}/audit.
  "members.members": "Socio",
  "memberships.memberships": "Membresía",
  "payments.payments": "Pago",
});

export const FIELD_LABELS: Readonly<Record<string, string>> = Object.freeze({
  // members
  first_name: "Nombres",
  last_name: "Apellidos",
  document: "Documento",
  document_type: "Tipo de documento",
  phone: "Teléfono",
  email: "Correo",
  birth_date: "Fecha de nacimiento",
  emergency_contact: "Contacto de emergencia",
  sex: "Sexo",
  preferred_unit: "Unidad preferida",
  deleted_at: "Fecha de baja",
  data_consent_at: "Autorización de datos",
  data_consent_version: "Versión de la autorización",
  created_by: "Creado por",
  // memberships
  member_id: "Socio",
  plan_id: "Plan",
  start_date: "Inicio",
  end_date: "Vence",
  status: "Estado",
  price_cop: "Precio",
  agreed_price_cop: "Precio acordado",
  classes_total: "Clases",
  classes_remaining: "Clases restantes",
  frozen_until: "Congelada hasta",
  cancel_reason: "Motivo de cancelación",
  cancelled_at: "Fecha de anulación",
  cancelled_by: "Anulada por",
  // payments
  membership_id: "Membresía",
  amount_cop: "Monto",
  method: "Medio de pago",
  paid_at: "Fecha de pago",
  registered_by: "Registrado por",
  reference: "Referencia",
  voided: "Anulado",
  voided_at: "Fecha de anulación",
  voided_by: "Anulado por",
  void_reason: "Motivo de anulación",
  // reveal
  field: "Campo",
});

/** Campos cifrados por el bus en v0.1 (CLAUDE.md, bus de criptografía, regla 9). */
export const ENCRYPTED_FIELDS: readonly string[] = Object.freeze([
  "document",
  "phone",
  "email",
  "emergency_contact",
  "birth_date",
]);

const MONEY_FIELDS = new Set(["amount_cop", "price_cop"]);

const isBlob = (value: unknown): boolean => typeof value === "string" && value.startsWith(BLOB_PREFIX);

/** Texto enmascarado del api o "Sin dato"; antepone el tipo de documento si falta. */
export function maskValue(kind: SensitiveKind, masked: string | null | undefined, documentType?: string): string {
  const text = masked?.trim() ?? "";
  if (text === "" || isBlob(text)) return NO_VALUE_LABEL;
  if (kind === "document" && documentType && !text.startsWith(documentType)) return `${documentType} ${text}`;
  return text;
}

export const actionLabel = (action: string): string => ACTION_LABELS[action] ?? action;
export const entityLabel = (entity: string): string => ENTITY_LABELS[entity] ?? entity;
const fieldLabel = (field: string): string => FIELD_LABELS[field] ?? field;

export function actorLabel(entry: Pick<AuditEntryView, "actor_id" | "actor_name">): string {
  if (entry.actor_id === SYSTEM_USER_ID) return "Sistema";
  return entry.actor_name?.trim() ? entry.actor_name : "Usuario";
}

/** Columnas de índice ciego (`<campo>_idx`): HMAC del valor, nunca se muestran. */
const BLIND_INDEX = /_idx$/;

function isSensitive(field: string, ...values: unknown[]): boolean {
  return ENCRYPTED_FIELDS.includes(field) || BLIND_INDEX.test(field) || values.some(isBlob);
}

function plain(field: string, value: unknown): string | null {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "sí" : "no";
  if (typeof value === "number") return MONEY_FIELDS.has(field) && Number.isInteger(value) ? formatCop(value) : String(value);
  if (typeof value === "string") return value;
  return null;
}

function changedLine(field: string, before: unknown, after: unknown): string {
  const label = fieldLabel(field);
  if (isSensitive(field, before, after)) return `${label}: dato cifrado modificado`;
  const from = plain(field, before);
  const to = plain(field, after);
  return from === null || to === null ? `${label}: modificado` : `${label}: ${from} → ${to}`;
}

function createdLine(field: string, value: unknown): string {
  const label = fieldLabel(field);
  if (isSensitive(field, value)) return `${label}: dato cifrado`;
  return `${label}: ${plain(field, value) ?? "registrado"}`;
}

const same = (a: unknown, b: unknown): boolean => JSON.stringify(a) === JSON.stringify(b);

/** Forma de un nombre de columna; lo que no la cumpla se dice "campo" (revisión S4A-F2, LOW-2). */
const COLUMN_NAME = /^[a-z_]{1,40}$/;
const UNKNOWN_FIELD_LABEL = "campo";

/**
 * La etiqueta de un nombre de campo: la de FIELD_LABELS, "campo cifrado" si trae un blob, el nombre
 * si tiene forma de columna y "campo" en otro caso.
 */
export function fieldNameLabel(field: string): string {
  const label = FIELD_LABELS[field];
  if (label !== undefined) return label;
  if (field.includes(BLOB_PREFIX)) return "campo cifrado";
  // Revisión S4A-F2 (LOW-2): un nombre que no tiene forma de columna no se pinta tal cual.
  return COLUMN_NAME.test(field) ? field : UNKNOWN_FIELD_LABEL;
}

/**
 * S4A-F2 (S4A-D32): resumen con solo nombres de campo (GET /members/{id}/audit no trae valores):
 * "Cambió: Teléfono, Correo", o "Campo: Documento" en un `reveal`.
 */
function fieldsSummary(action: string, fields: readonly string[]): string[] {
  if (fields.length === 0) return [];
  const labels = fields.map(fieldNameLabel);
  return action === "reveal" ? [`${fieldLabel("field")}: ${labels[0] ?? ""}`] : [`Cambió: ${labels.join(", ")}`];
}

/** Resumen en español de lo que cambió en una entrada; nunca incluye un blob. */
export function summarizeChange(entry: AuditEntryView): string[] {
  if (!entry.before && !entry.after && entry.fields) return fieldsSummary(entry.action, entry.fields);
  const before = entry.before ?? {};
  const after = entry.after ?? {};
  switch (entry.action) {
    case "update": {
      const fields = [...new Set([...Object.keys(before), ...Object.keys(after)])];
      return fields.filter((f) => !same(before[f], after[f])).map((f) => changedLine(f, before[f], after[f]));
    }
    case "insert":
      return Object.entries(after).map(([field, value]) => createdLine(field, value));
    case "reveal": {
      const field = after.field;
      return typeof field === "string" ? [`${fieldLabel("field")}: ${fieldLabel(field)}`] : [];
    }
    default:
      return [];
  }
}

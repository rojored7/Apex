// US-066 T3: etiquetas del historial y del valor enmascarado.
// - El enmascarado lo calcula el api al leer la ficha (N-01): maskValue no enmascara nada,
//   solo muestra el texto del api o "Sin dato".
// - Un campo cifrado (lista de v0.1 o un valor con prefijo "apx1.") nunca se muestra: se
//   resume como "dato cifrado modificado". Ningún texto de aquí contiene un blob.
// DESIGN-GAP: docs/openapi.json aún no publica AuditEntryOut (llega con US-106); la forma de
// AuditEntryView sigue 02_domain_model.md 2.12 y se ajusta cuando exista el contrato.
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
}

export type SensitiveKind = "document" | "phone" | "email" | "birth_date" | "emergency_contact";

/** Usuario técnico (N-15); nunca autentica y en pantalla es "Sistema". */
export const SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001";

const BLOB_PREFIX = "apx1.";
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
  // memberships
  plan_id: "Plan",
  start_date: "Inicio",
  end_date: "Vence",
  status: "Estado",
  price_cop: "Precio",
  frozen_until: "Congelada hasta",
  cancel_reason: "Motivo de cancelación",
  // payments
  amount_cop: "Monto",
  method: "Medio de pago",
  paid_at: "Fecha de pago",
  reference: "Referencia",
  voided: "Anulado",
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

export function actorLabel(entry: AuditEntryView): string {
  if (entry.actor_id === SYSTEM_USER_ID) return "Sistema";
  return entry.actor_name?.trim() ? entry.actor_name : "Usuario";
}

function isSensitive(field: string, ...values: unknown[]): boolean {
  return ENCRYPTED_FIELDS.includes(field) || values.some(isBlob);
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

/** Resumen en español de lo que cambió en una entrada; nunca incluye un blob. */
export function summarizeChange(entry: AuditEntryView): string[] {
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

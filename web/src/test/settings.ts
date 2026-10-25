// Datos de prueba de las secciones de configuración (S2-F5). Imitan las respuestas de
// GET /settings/{gym|privacy|memberships}: defaults con version 0 y updated_* nulos.
import type { GymSettings, MembershipsSettings, PaymentMethodsSettings, PrivacyView, SettingsSection } from "../features/system/api";
import type { MockReply } from "./server";

export const ADMIN_ID = "00000000-0000-4000-8000-000000000001";

export function gymSection(value: Partial<GymSettings> = {}, version = 0): SettingsSection<"gym"> {
  return {
    key: "gym",
    value: { name: "APEX", nit: null, address: null, city: null, phone: null, whatsapp: null, email: null, ...value },
    version,
    updated_at: version === 0 ? null : "2026-10-21T15:00:00Z",
    updated_by: version === 0 ? null : ADMIN_ID,
  };
}

export function privacySection(value: Partial<PrivacyView> = {}, version = 0): SettingsSection<"privacy"> {
  return {
    key: "privacy",
    value: { policy_version: null, policy_text: null, retention_years: 5, consent_required_from: null, ...value },
    version,
    updated_at: version === 0 ? null : "2026-10-21T15:00:00Z",
    updated_by: version === 0 ? null : ADMIN_ID,
  };
}

export function membershipsSection(value: Partial<MembershipsSettings> = {}, version = 0): SettingsSection<"memberships"> {
  return {
    key: "memberships",
    value: { expiring_days: 7, max_freeze_days_per_membership: 30, max_freezes_per_membership: 2, max_retroactive_days: 7, ...value },
    version,
    updated_at: version === 0 ? null : "2026-10-21T15:00:00Z",
    updated_by: version === 0 ? null : ADMIN_ID,
  };
}

export const CONFLICT_REPLY: MockReply = {
  status: 409,
  body: { error: { code: "version_conflict", message: "Otra persona cambió esta sección. Recarga para ver los cambios." } },
};

export function fieldErrorReply(field: string): MockReply {
  return { status: 422, body: { error: { code: "invalid_settings", message: `El campo ${field} no es válido.`, field } } };
}

export const SERVER_ERROR_REPLY: MockReply = {
  status: 500,
  body: { error: { code: "internal_error", message: "Ocurrió un error inesperado. Intenta de nuevo." } },
};

/** Promesa que la prueba resuelve a mano (para ver el estado "guardando"). */
export function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve: (value: T) => void = () => undefined;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

/** S3-F4: GET /settings/payment_methods con las etiquetas por defecto (D24). */
export function paymentMethodsSection(value: Partial<PaymentMethodsSettings> = {}, version = 0): SettingsSection<"payment_methods"> {
  return {
    key: "payment_methods",
    value: {
      cash: { label: "Efectivo", hint: "" },
      nequi: { label: "Nequi", hint: "" },
      breb: { label: "Bre-B", hint: "" },
      ...value,
    },
    version,
    updated_at: version === 0 ? null : "2026-10-21T15:00:00Z",
    updated_by: version === 0 ? null : ADMIN_ID,
  };
}

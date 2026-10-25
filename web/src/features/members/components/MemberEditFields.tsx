// S3-F1 · US-075 (front): las secciones de Socio_Form.html en modo editar.
// - Lo no sensible (nombres, apellidos, sexo y, solo el admin, el tipo de documento) se edita como
//   en el alta.
// - Los cinco sensibles NUNCA se precargan en claro (S3-D46, S3-D52): cada uno muestra su máscara
//   ("Actual: CC •••• 4417") y "Cambiar", que abre un campo vacío para el valor nuevo; los
//   opcionales tienen además "Quitar" (viaja `null`). El documento solo lo cambia quien tiene
//   members.document.update (el admin); el coach lo ve de solo lectura.
// - La autorización de datos: si ya está registrada se muestra; si falta, la casilla
//   "Registrar autorización" (nunca marcada de entrada; solo se puede marcar, M-4).
// DESIGN-GAP:
// - Socio_Form.html en modo editar no distingue roles ni dibuja cómo se cambia un dato cifrado: aquí
//   se usan "Cambiar" y "Quitar" sobre la máscara (BRECHAS §10, "Campos sensibles en la edición").
// - Las secciones que faltan (foto, firma, portal, cargas, salud) son las del alta (MemberFormFields).
import { useEffect, useId, useRef, type ReactNode } from "react";
import type { UseFormReturn } from "react-hook-form";
import { formatDate } from "../../../core/i18n/format";
import { maskValue } from "../../../shared/lib/audit-labels";
import { Button } from "../../../shared/ui/Button";
import { Field, type FieldErrorAction } from "../../../shared/ui/Field";
import { memberHref } from "../memberLinks";
import { DOCUMENT_TYPE_LABELS, DOCUMENT_TYPES, MEMBER_LIMITS, REMOVABLE_FIELDS, SEX_LABELS, SEXES, type MemberDetailView, type MemberEditValues, type SensitiveEditField } from "../schemas";
import { EXISTING_LINK_TEXT } from "./MemberFormFields";
import formStyles from "./MemberFormFields.module.css";
import styles from "./MemberEditFields.module.css";

export const CONSENT_EDIT_LABEL = "Registrar autorización";
export const DOCUMENT_ADMIN_ONLY = "Solo un administrador puede cambiar el documento.";
const CONSENT_EDIT_HINT_ID = "member-edit-consent-hint";
const CONSENT_EDIT_ERROR_ID = "member-edit-consent-error";

type Focus = "input" | "change" | "remove" | "undo" | null;

interface SensitiveBlockProps {
  form: UseFormReturn<MemberEditValues>;
  field: SensitiveEditField;
  label: string;
  masked: string | null;
  documentType?: string;
  canChange: boolean;
  hint?: string;
  /** El primer control del valor nuevo (al que va el foco al pulsar "Cambiar"). */
  firstPath: "document" | "birth_date" | "phone" | "email" | "emergency_contact.name";
  children: ReactNode;
}

function SensitiveBlock({ form, field, label, masked, documentType, canChange, hint, firstPath, children }: SensitiveBlockProps) {
  const labelId = useId();
  const mode = form.watch(`modes.${field}`);
  // El foco pedido se aplica tras el render que cambia el modo (setValue de `modes` vuelve a pintar).
  const pendingFocus = useRef<Focus>(null);
  // Los botones del bloque se buscan por `data-action` (Button no reenvía `ref`).
  const groupRef = useRef<HTMLDivElement>(null);
  const shown = maskValue(field, masked, documentType);
  const removable = REMOVABLE_FIELDS.includes(field) && masked !== null && masked.trim() !== "";

  useEffect(() => {
    const focus = pendingFocus.current;
    pendingFocus.current = null;
    if (focus === "input") form.setFocus(firstPath);
    else if (focus !== null) groupRef.current?.querySelector<HTMLButtonElement>(`button[data-action="${focus}"]`)?.focus();
  });

  const setMode = (next: MemberEditValues["modes"][SensitiveEditField], then: Focus): void => {
    form.setValue(`modes.${field}`, next, { shouldDirty: true });
    if (next !== "change") {
      // El valor a medio escribir no se guarda en ningún lado al cancelar.
      if (field === "emergency_contact") form.setValue("emergency_contact", { name: "", phone: "", relationship: "" });
      else form.setValue(field, "");
      form.clearErrors(field);
    }
    pendingFocus.current = then;
  };

  return (
    <div ref={groupRef} role="group" aria-labelledby={labelId} className={styles.sensitive}>
      <span id={labelId} className={styles.label}>
        {label}
      </span>
      {mode === "change" ? <div className={styles.inputs}>{children}</div> : <span className={styles.current} aria-live="polite">{mode === "remove" ? "Se quitará al guardar." : `Actual: ${shown}`}</span>}
      <span className={styles.actions}>
        {mode === "keep" && canChange ? (
          <Button data-action="change" variant="secondary" onClick={() => { setMode("change", "input"); }}>
            Cambiar
          </Button>
        ) : null}
        {mode === "keep" && canChange && removable ? (
          <Button data-action="remove" variant="ghost" onClick={() => { setMode("remove", "undo"); }}>
            Quitar
          </Button>
        ) : null}
        {mode === "change" ? (
          <Button variant="ghost" onClick={() => { setMode("keep", "change"); }}>
            Cancelar cambio
          </Button>
        ) : null}
        {mode === "remove" ? (
          <Button data-action="undo" variant="ghost" onClick={() => { setMode("keep", "remove"); }}>
            Deshacer
          </Button>
        ) : null}
      </span>
      {hint ? <p className={formStyles.note}>{hint}</p> : null}
    </div>
  );
}

export interface MemberEditFieldsProps {
  form: UseFormReturn<MemberEditValues>;
  member: MemberDetailView;
  /** members.document.update: el documento y su tipo (solo el admin, M-3). */
  canChangeDocument: boolean;
  /** 409: el socio que ya tiene el documento; su error enlaza a esa ficha (S2-D34). */
  existingId: string | null;
  onNavigate: (href: string) => void;
}

function consentRegistered(member: MemberDetailView): string | null {
  if (member.data_consent_at === null) return null;
  const version = member.data_consent_version ? ` · versión ${member.data_consent_version}` : "";
  return `Autorización registrada el ${formatDate(member.data_consent_at)}${version}`;
}

export function MemberEditFields({ form, member, canChangeDocument, existingId, onNavigate }: MemberEditFieldsProps) {
  const {
    register,
    formState: { errors },
  } = form;
  const existing: { errorAction?: FieldErrorAction } = existingId ? { errorAction: { href: memberHref(existingId), text: EXISTING_LINK_TEXT, onNavigate } } : {};
  const registered = consentRegistered(member);
  const consentError = errors.data_consent?.message;

  return (
    <>
      <fieldset className={formStyles.section}>
        <legend className={formStyles.legend}>1 · Identificación</legend>
        <div className={formStyles.grid}>
          <Field label="Nombres" required autoComplete="off" maxLength={MEMBER_LIMITS.name} error={errors.first_name?.message} {...register("first_name")} />
          <Field label="Apellidos" required autoComplete="off" maxLength={MEMBER_LIMITS.name} error={errors.last_name?.message} {...register("last_name")} />
          <Field label="Sexo (leaderboard)" name="sex" error={errors.sex?.message}>
            {(control) => (
              <select {...control} {...register("sex")}>
                <option value="">Sin indicar</option>
                {SEXES.map((sex) => (
                  <option key={sex} value={sex}>
                    {SEX_LABELS[sex]}
                  </option>
                ))}
              </select>
            )}
          </Field>
          {canChangeDocument ? (
            <Field label="Tipo de documento" name="document_type" error={errors.document_type?.message}>
              {(control) => (
                <select {...control} {...register("document_type")}>
                  {DOCUMENT_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {DOCUMENT_TYPE_LABELS[type]}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          ) : null}
          <SensitiveBlock
            form={form}
            field="document"
            label="Documento"
            masked={member.document}
            documentType={member.document_type}
            canChange={canChangeDocument}
            firstPath="document"
            {...(canChangeDocument ? {} : { hint: DOCUMENT_ADMIN_ONLY })}
          >
            <Field label="Nuevo documento" required autoComplete="off" maxLength={MEMBER_LIMITS.documentMax} error={errors.document?.message} {...existing} {...register("document")} />
          </SensitiveBlock>
          <SensitiveBlock form={form} field="birth_date" label="Fecha de nacimiento" masked={member.birth_date} canChange firstPath="birth_date">
            <Field label="Nueva fecha de nacimiento" type="date" required error={errors.birth_date?.message} {...register("birth_date")} />
          </SensitiveBlock>
        </div>
      </fieldset>

      <fieldset className={formStyles.section}>
        <legend className={formStyles.legend}>2 · Contacto</legend>
        <div className={formStyles.grid}>
          <SensitiveBlock form={form} field="phone" label="Teléfono (WhatsApp)" masked={member.phone} canChange firstPath="phone">
            <Field label="Nuevo teléfono" type="tel" inputMode="tel" required autoComplete="off" placeholder="+57 3xx xxx xxxx" error={errors.phone?.message} {...register("phone")} />
          </SensitiveBlock>
          <SensitiveBlock form={form} field="email" label="Correo" masked={member.email} canChange firstPath="email">
            <Field label="Nuevo correo" type="email" inputMode="email" required autoComplete="off" error={errors.email?.message} {...register("email")} />
          </SensitiveBlock>
        </div>
      </fieldset>

      <fieldset className={formStyles.section}>
        <legend className={formStyles.legend}>3 · Contacto de emergencia</legend>
        <SensitiveBlock form={form} field="emergency_contact" label="Contacto de emergencia" masked={member.emergency_contact} canChange firstPath="emergency_contact.name">
          <div className={formStyles.grid}>
            <Field label="Nombre del contacto" required autoComplete="off" error={errors.emergency_contact?.name?.message} {...register("emergency_contact.name")} />
            <Field label="Parentesco" autoComplete="off" error={errors.emergency_contact?.relationship?.message} {...register("emergency_contact.relationship")} />
            <Field label="Teléfono del contacto" type="tel" inputMode="tel" required autoComplete="off" error={errors.emergency_contact?.phone?.message} {...register("emergency_contact.phone")} />
          </div>
        </SensitiveBlock>
      </fieldset>

      <fieldset className={formStyles.section}>
        <legend className={formStyles.legend}>4 · Autorización de datos (Ley 1581)</legend>
        {registered ? (
          <p className={styles.registered}>{registered}</p>
        ) : (
          <>
            <label className={formStyles.check}>
              <input
                type="checkbox"
                className={formStyles.checkbox}
                aria-describedby={consentError ? `${CONSENT_EDIT_HINT_ID} ${CONSENT_EDIT_ERROR_ID}` : CONSENT_EDIT_HINT_ID}
                aria-invalid={consentError ? true : undefined}
                {...register("data_consent")}
              />
              <span>{CONSENT_EDIT_LABEL}</span>
            </label>
            <p id={CONSENT_EDIT_HINT_ID} className={formStyles.note}>
              Márcala solo si el socio leyó y aceptó la política de tratamiento de datos del gimnasio. Una vez registrada no se retira desde aquí.
            </p>
            {consentError ? (
              <p id={CONSENT_EDIT_ERROR_ID} className={styles.error}>
                {consentError}
              </p>
            ) : null}
          </>
        )}
      </fieldset>
    </>
  );
}

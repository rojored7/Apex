// S2-F6 · US-069 (front): las secciones de Socio_Form.html con los campos de MemberCreate.
// 1 · Identificación (nombres, apellidos, sexo, tipo y número de documento, fecha de nacimiento),
// 2 · Contacto (teléfono, correo), 3 · Contacto de emergencia (nombre, parentesco, teléfono) y
// 4 · Autorización de datos (la casilla de M-4, nunca marcada de entrada).
// DESIGN-GAP:
// - Sin foto (cuadro "foto"), sin firma táctil ni documento firmado (opciones A y B de la
//   sección 4): los adjuntos llegan con v0.3 (POST /members/:id/attachments).
// - Sin "5 · Acceso al portal" (v1.0), sin "Unidad para cargas" (atleta, v0.6) y sin
//   "Observaciones de salud" (no están en MemberCreate; tampoco hay notas, M-5).
// - El nombre va en dos campos (Nombres y Apellidos) y no en "Nombre completo": MemberCreate
//   pide first_name y last_name.
// - Sexo y teléfono no son obligatorios (en la pantalla llevan *): MemberCreate los deja
//   opcionales. El sexo suma "Otro" (`x`) y "Sin indicar".
import type { UseFormReturn } from "react-hook-form";
import { Field, type FieldErrorAction } from "../../../shared/ui/Field";
import { memberHref } from "../memberLinks";
import { DOCUMENT_TYPE_LABELS, DOCUMENT_TYPES, MEMBER_LIMITS, SEX_LABELS, SEXES, type MemberFormValues } from "../schemas";
import styles from "./MemberFormFields.module.css";

export interface MemberFormFieldsProps {
  form: UseFormReturn<MemberFormValues>;
  /** 409: el socio que ya tiene el documento; el error del documento enlaza a su ficha. */
  existingId: string | null;
  onNavigate: (href: string) => void;
}

export const CONSENT_LABEL = "El socio autorizó el tratamiento de datos";
export const EXISTING_LINK_TEXT = "Ver socio existente";
const CONSENT_HINT_ID = "member-consent-hint";


export function MemberFormFields({ form, existingId, onNavigate }: MemberFormFieldsProps) {
  const {
    register,
    formState: { errors },
  } = form;
  const existing: { errorAction?: FieldErrorAction } = existingId ? { errorAction: { href: memberHref(existingId), text: EXISTING_LINK_TEXT, onNavigate } } : {};

  return (
    <>
      <fieldset className={styles.section}>
        <legend className={styles.legend}>1 · Identificación</legend>
        <div className={styles.grid}>
          <Field label="Nombres" required autoComplete="off" maxLength={MEMBER_LIMITS.name} error={errors.first_name?.message} {...register("first_name")} />
          <Field label="Apellidos" required autoComplete="off" maxLength={MEMBER_LIMITS.name} error={errors.last_name?.message} {...register("last_name")} />
          <Field label="Tipo de documento" name="document_type" required error={errors.document_type?.message}>
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
          <Field
            label="Número de documento"
            required
            autoComplete="off"
            hint="Se cifra al guardar. Si ya existe, se avisa con enlace al socio."
            error={errors.document?.message}
            {...existing}
            {...register("document")}
          />
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
          <Field label="Fecha de nacimiento" type="date" error={errors.birth_date?.message} {...register("birth_date")} />
        </div>
      </fieldset>

      <fieldset className={styles.section}>
        <legend className={styles.legend}>2 · Contacto</legend>
        <div className={styles.grid}>
          <Field
            label="Teléfono (WhatsApp)"
            type="tel"
            inputMode="tel"
            autoComplete="off"
            placeholder="+57 3xx xxx xxxx"
            error={errors.phone?.message}
            {...register("phone")}
          />
          <Field label="Correo" type="email" inputMode="email" autoComplete="off" error={errors.email?.message} {...register("email")} />
        </div>
      </fieldset>

      <fieldset className={styles.section}>
        <legend className={styles.legend}>3 · Contacto de emergencia</legend>
        <div className={styles.grid}>
          <Field label="Nombre del contacto" autoComplete="off" error={errors.emergency_contact?.name?.message} {...register("emergency_contact.name")} />
          <Field label="Parentesco" autoComplete="off" error={errors.emergency_contact?.relationship?.message} {...register("emergency_contact.relationship")} />
          <Field
            label="Teléfono del contacto"
            type="tel"
            inputMode="tel"
            autoComplete="off"
            error={errors.emergency_contact?.phone?.message}
            {...register("emergency_contact.phone")}
          />
        </div>
        <p className={styles.note}>Opcional. Si lo llenas, escribe al menos el nombre y el teléfono.</p>
      </fieldset>

      <fieldset className={styles.section}>
        <legend className={styles.legend}>4 · Autorización de datos (Ley 1581)</legend>
        <label className={styles.check}>
          <input type="checkbox" className={styles.checkbox} aria-describedby={CONSENT_HINT_ID} {...register("data_consent")} />
          <span>{CONSENT_LABEL}</span>
        </label>
        <p id={CONSENT_HINT_ID} className={styles.note}>
          Márcala solo si el socio leyó y aceptó la política de tratamiento de datos del gimnasio. Si no la marcas, el socio queda registrado y la lista
          avisa que falta la autorización.
        </p>
      </fieldset>
    </>
  );
}

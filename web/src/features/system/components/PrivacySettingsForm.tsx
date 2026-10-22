// S2-F5 · US-057: sección "Privacidad" (Config.html, "8 · Datos personales", texto de
// autorización de la Ley 1581). Versión, texto con contador, años de retención y
// "Autorización obligatoria desde". Muestra la versión vigente con su fecha.
// - El texto de la política es texto plano: va como valor de un <textarea> y nunca se
//   interpreta como HTML (sin dangerouslySetInnerHTML).
// - Publicar una versión distinta de la vigente pide confirmación: "Los socios que ya
//   aceptaron conservan la versión anterior." La primera publicación no la pide (no hay
//   versión anterior que conservar).
// DESIGN-GAP: Config.html junta la TV y los datos personales en una caja con un textarea de
// dos líneas; aquí la sección es propia (pestaña Privacidad, blueprint F5) con los cuatro
// campos del contrato `privacy`.
import { useState } from "react";
import { formatCount, formatDate } from "../../../core/i18n/format";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { cx } from "../../../shared/ui/cx";
import { Field } from "../../../shared/ui/Field";
import { useSettingsSection, type PrivacyInput, type PrivacyView, type SettingsSection, type SettingsSectionApi } from "../api";
import { POLICY_TEXT_MAX, privacySettingsSchema, type PrivacySettingsForm as PrivacyForm } from "../schemas";
import styles from "./SettingsForm.module.css";
import { SectionLoadState, SettingsFormFrame, type SettingsFormProps } from "./SettingsFormFrame";
import { blankToNull, useSectionForm } from "./useSectionForm";

const FIELD_MESSAGES: Partial<Record<keyof PrivacyForm, string>> = {
  policy_version: "El servidor no aceptó la versión. Revísala y vuelve a guardar.",
  policy_text: "El servidor no aceptó el texto. Revísalo y vuelve a guardar.",
  retention_years: "El servidor no aceptó los años de retención. Revísalos y vuelve a guardar.",
  consent_required_from: "El servidor no aceptó la fecha. Revísala y vuelve a guardar.",
};

function toForm(value: PrivacyView): PrivacyForm {
  return {
    policy_version: value.policy_version ?? "",
    policy_text: value.policy_text ?? "",
    retention_years: String(value.retention_years),
    consent_required_from: value.consent_required_from ?? "",
  };
}

function toInput(values: PrivacyForm): PrivacyInput {
  return {
    policy_version: values.policy_version.trim(),
    policy_text: values.policy_text.trim(),
    retention_years: Number(values.retention_years),
    consent_required_from: blankToNull(values.consent_required_from),
  };
}

function CurrentVersion({ section }: { section: SettingsSection<"privacy"> }) {
  const { policy_version: version } = section.value;
  if (!version) {
    return <p className={styles.current}>Todavía no hay una política publicada. Escribe la versión y el texto para publicar la primera.</p>;
  }
  const since = section.updated_at ? ` · vigente desde ${formatDate(section.updated_at)}` : "";
  return <p className={styles.current}>{`Versión vigente: ${version}${since}`}</p>;
}

function PrivacyFields({ section, api, onDirtyChange }: SettingsFormProps & { section: SettingsSection<"privacy">; api: SettingsSectionApi<"privacy"> }) {
  const { form, submitValues, frame } = useSectionForm({
    section,
    api,
    schema: privacySettingsSchema,
    toForm,
    toInput,
    fieldMessages: FIELD_MESSAGES,
    onDirtyChange,
  });
  const [pending, setPending] = useState<PrivacyForm | null>(null);
  const { register, formState, watch } = form;
  const { errors } = formState;
  const textLength = watch("policy_text").length;
  const published = section.value.policy_version;

  const onValid = async (values: PrivacyForm): Promise<void> => {
    if (published && values.policy_version.trim() !== published) {
      setPending(values);
      return;
    }
    await submitValues(values);
  };

  return (
    <>
      <SettingsFormFrame
        title="Privacidad"
        description="Política de tratamiento de datos personales (Ley 1581). Cada socio acepta una versión."
        summary={<CurrentVersion section={section} />}
        onSubmit={(event) => {
          void form.handleSubmit(onValid)(event);
        }}
        {...frame}
      >
        <Field
          label="Versión de la política"
          required
          hint="Cambia la versión cada vez que cambies el texto. Ejemplo: 2026-10."
          autoComplete="off"
          error={errors.policy_version?.message}
          {...register("policy_version")}
        />
        <Field
          label="Años de retención de los datos"
          required
          type="number"
          inputMode="numeric"
          min={1}
          max={20}
          step={1}
          hint="Entre 1 y 20. Por defecto: 5."
          error={errors.retention_years?.message}
          {...register("retention_years")}
        />
        <div className={styles.wide}>
          <Field
            label="Texto de la política"
            name="policy_text"
            required
            hint={`${formatCount(textLength)} de ${formatCount(POLICY_TEXT_MAX)} caracteres`}
            error={errors.policy_text?.message}
          >
            {(control) => <textarea {...control} {...register("policy_text")} className={cx(control.className, styles.textarea)} rows={8} />}
          </Field>
        </div>
        <Field
          label="Autorización obligatoria desde"
          type="date"
          hint="Desde esta fecha cada socio nuevo debe aceptar la política. Déjalo vacío si aún no aplica."
          error={errors.consent_required_from?.message}
          {...register("consent_required_from")}
        />
      </SettingsFormFrame>
      <ConfirmModal
        open={pending !== null}
        title={`¿Publicar la versión ${pending?.policy_version.trim() ?? ""}?`}
        consequence="Los socios que ya aceptaron conservan la versión anterior."
        confirmLabel="Publicar versión"
        tone="primary"
        onConfirm={async () => {
          if (pending) await submitValues(pending);
        }}
        onClose={() => {
          setPending(null);
        }}
      />
    </>
  );
}

export function PrivacySettingsForm({ onDirtyChange }: SettingsFormProps) {
  const api = useSettingsSection("privacy");
  const section = api.query.data;
  if (!section) return <SectionLoadState query={api.query} />;
  return <PrivacyFields section={section} api={api} onDirtyChange={onDirtyChange} />;
}

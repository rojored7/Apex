// S2-F5 · US-055: sección "Gimnasio" de Config.html. Siete Field de 44 px (los campos de
// GymSettings del contrato) y "Guardar". Al guardar, la sesión toma el nombre nuevo para que
// el TopBar lo muestre sin recargar.
// DESIGN-GAP: Config.html dibuja un cuadro de logo (los adjuntos llegan en v0.3) y "Zona
// horaria" como campo de solo lectura; no están en el contrato de `gym`. La zona se informa
// como nota (es fija, America/Bogota). NIT, ciudad y correo no están en Config.html y sí en
// el contrato (US-055).
import { getAccessToken, getSession, setSession } from "../../../core/auth/session";
import { TZ_DISPLAY } from "../../../config/locale";
import { cx } from "../../../shared/ui/cx";
import { Field } from "../../../shared/ui/Field";
import { useSettingsSection, type GymSettings, type SettingsSection, type SettingsSectionApi } from "../api";
import { gymSettingsSchema, type GymSettingsForm as GymForm } from "../schemas";
import styles from "./SettingsForm.module.css";
import { SectionLoadState, SettingsFormFrame, type SettingsFormProps } from "./SettingsFormFrame";
import { blankToNull, errorOf, useSectionForm } from "./useSectionForm";

const FIELD_MESSAGES: Partial<Record<keyof GymForm, string>> = {
  name: "El servidor no aceptó el nombre. Revísalo y vuelve a guardar.",
  nit: "El servidor no aceptó el NIT. Revísalo y vuelve a guardar.",
  address: "El servidor no aceptó la dirección. Revísala y vuelve a guardar.",
  city: "El servidor no aceptó la ciudad. Revísala y vuelve a guardar.",
  phone: "El servidor no aceptó el teléfono. Revísalo y vuelve a guardar.",
  whatsapp: "El servidor no aceptó el WhatsApp. Revísalo y vuelve a guardar.",
  email: "El servidor no aceptó el correo. Revísalo y vuelve a guardar.",
};

function toForm(value: GymSettings): GymForm {
  return {
    name: value.name,
    nit: value.nit ?? "",
    address: value.address ?? "",
    city: value.city ?? "",
    phone: value.phone ?? "",
    whatsapp: value.whatsapp ?? "",
    email: value.email ?? "",
  };
}

function toInput(values: GymForm): GymSettings {
  return {
    name: values.name.trim(),
    nit: blankToNull(values.nit),
    address: blankToNull(values.address),
    city: blankToNull(values.city),
    phone: blankToNull(values.phone),
    whatsapp: blankToNull(values.whatsapp),
    email: blankToNull(values.email),
  };
}

/** El TopBar lee el nombre del gimnasio de la sesión (gym_name de GET /auth/me). */
function syncGymName(saved: SettingsSection<"gym">): void {
  const { status, user } = getSession();
  const token = getAccessToken();
  if (status !== "authenticated" || !user || !token || user.gymName === saved.value.name) return;
  setSession({ accessToken: token, user: { ...user, gymName: saved.value.name } });
}

function GymFields({ section, api, onDirtyChange }: SettingsFormProps & { section: SettingsSection<"gym">; api: SettingsSectionApi<"gym"> }) {
  const { form, submitValues, frame } = useSectionForm({
    section,
    api,
    schema: gymSettingsSchema,
    toForm,
    toInput,
    fieldMessages: FIELD_MESSAGES,
    onDirtyChange,
    onSaved: syncGymName,
  });
  const { register, formState } = form;
  const { errors } = formState;

  return (
    <SettingsFormFrame
      title="Gimnasio"
      description="Lo ven los socios en el portal, los recibos y los avisos."
      onSubmit={(event) => {
        void form.handleSubmit(submitValues)(event);
      }}
      {...frame}
    >
      <Field label="Nombre" required autoComplete="organization" {...errorOf(errors, "name")} {...register("name")} />
      <Field
        label="NIT"
        hint="Solo dígitos y, si tiene, un guion con el dígito de verificación."
        inputMode="numeric"
        {...errorOf(errors, "nit")}
        {...register("nit")}
      />
      <Field label="Dirección" autoComplete="street-address" {...errorOf(errors, "address")} {...register("address")} />
      <Field label="Ciudad" autoComplete="address-level2" {...errorOf(errors, "city")} {...register("city")} />
      <Field label="Teléfono" type="tel" autoComplete="tel" {...errorOf(errors, "phone")} {...register("phone")} />
      <Field label="WhatsApp Business" type="tel" hint="El número desde el que el box escribe a los socios." {...errorOf(errors, "whatsapp")} {...register("whatsapp")} />
      <Field
        label="Correo de contacto"
        type="email"
        autoComplete="email"
        hint="Se guarda en minúsculas."
        {...errorOf(errors, "email")}
        {...register("email")}
      />
      <p className={cx(styles.note, styles.wide)}>{`Zona horaria: ${TZ_DISPLAY}. Es fija para todo el sistema.`}</p>
    </SettingsFormFrame>
  );
}

export function GymSettingsForm({ onDirtyChange }: SettingsFormProps) {
  const api = useSettingsSection("gym");
  const section = api.query.data;
  if (!section) return <SectionLoadState query={api.query} />;
  return <GymFields section={section} api={api} onDirtyChange={onDirtyChange} />;
}

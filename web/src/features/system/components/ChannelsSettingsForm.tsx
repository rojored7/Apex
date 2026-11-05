// S5-F2 · US-122 (front): pestaña "Canales" de Configuración (Config.html, "4 · Canales de aviso"),
// solo admin. Enciende o apaga cada canal y fija lo que ve quien recibe el aviso.
// - GET y PATCH /settings/channels con la versión leída (useSectionForm); 409 con Recargar; 422 con
//   campo (`value.email.sender_name`, ...) bajo su campo y sin campo como aviso.
// - Cada canal con credenciales muestra una insignia desde `credentials_present` (S5-D204): "Credenciales
//   listas" o "Faltan credenciales en .env". Los secretos viven en el entorno del servidor: este
//   formulario nunca pide ni muestra contraseñas, tokens ni claves.
// DESIGN-GAP:
// - Config.html dibuja "Correo · proveedor: Brevo · remitente configurado · Probar envío" y "Telegram ·
//   bot no configurado": el api no expone el proveedor ni tiene "Probar envío" (S5-D204: solo
//   `credentials_present`), así que la insignia reemplaza ese texto y no hay botón de prueba.
// - Config.html pone "WhatsApp manual" como una casilla sin más; aquí suma el indicativo del país
//   (`country_code`), que el api usa para armar el enlace wa.me.
import { cx } from "../../../shared/ui/cx";
import { Field } from "../../../shared/ui/Field";
import { useSettingsSection, type ChannelsSettings, type SettingsSection, type SettingsSectionApi } from "../api";
import { channelsSettingsSchema, REPLY_TO_MAX, SENDER_NAME_MAX, type ChannelsSettingsForm as ChannelsForm } from "../schemas";
import styles from "./SettingsForm.module.css";
import { SectionLoadState, SettingsFormFrame, type SettingsFormProps } from "./SettingsFormFrame";
import { blankToNull, useSectionForm } from "./useSectionForm";

export const CREDENTIALS_READY = "Credenciales listas";
export const CREDENTIALS_MISSING = "Faltan credenciales en .env";
export const NO_CREDENTIALS_NEEDED = "No necesita credenciales";

const FIELD_MESSAGES: Partial<Record<string, string>> = {
  "email.sender_name": "El servidor no aceptó este nombre. Revísalo y vuelve a guardar.",
  "email.reply_to": "El servidor no aceptó este correo. Revísalo y vuelve a guardar.",
  "whatsapp.country_code": "El servidor no aceptó este indicativo. Revísalo y vuelve a guardar.",
};

function toForm(value: ChannelsSettings): ChannelsForm {
  return {
    email: { enabled: value.email.enabled, sender_name: value.email.sender_name, reply_to: value.email.reply_to ?? "" },
    whatsapp: { enabled: value.whatsapp.enabled, country_code: value.whatsapp.country_code },
    telegram: { enabled: value.telegram.enabled },
  };
}

function toInput(values: ChannelsForm): ChannelsSettings {
  return {
    email: { enabled: values.email.enabled, sender_name: values.email.sender_name.trim(), reply_to: blankToNull(values.email.reply_to) },
    whatsapp: { enabled: values.whatsapp.enabled, country_code: values.whatsapp.country_code.trim() },
    telegram: { enabled: values.telegram.enabled },
  };
}

function CredentialsBadge({ ready }: { ready: boolean | null }) {
  if (ready === null) return <span className={styles.badge}>{NO_CREDENTIALS_NEEDED}</span>;
  return <span className={cx(styles.badge, !ready && styles.badgeWarn)}>{ready ? CREDENTIALS_READY : CREDENTIALS_MISSING}</span>;
}

function ChannelsFields({ section, api, onDirtyChange }: SettingsFormProps & { section: SettingsSection<"channels">; api: SettingsSectionApi<"channels"> }) {
  const { form, submitValues, frame } = useSectionForm({
    section,
    api,
    schema: channelsSettingsSchema,
    toForm,
    toInput,
    fieldMessages: FIELD_MESSAGES,
    onDirtyChange,
  });
  const { register, formState } = form;
  const { credentials_present: credentials } = section;

  return (
    <SettingsFormFrame
      title="Canales de aviso"
      description="Por dónde pueden salir los avisos. Los canales empiezan apagados; cada socio además decide los suyos."
      onSubmit={(event) => {
        void form.handleSubmit(submitValues)(event);
      }}
      {...frame}
    >
      <fieldset className={styles.group}>
        <legend className={styles.legend}>Correo</legend>
        <div className={styles.channelHead}>
          <label className={styles.toggle}>
            <input type="checkbox" className={styles.checkbox} {...register("email.enabled")} />
            Enviar avisos por correo
          </label>
          <CredentialsBadge ready={credentials.email} />
        </div>
        {credentials.email ? null : <p className={styles.note}>Si faltan credenciales, el correo no sale aunque esté activo. Pide a quien instala el sistema que las agregue al archivo .env.</p>}
        <Field
          label="Nombre del remitente"
          required
          autoComplete="off"
          maxLength={SENDER_NAME_MAX * 2}
          hint="Lo ve quien recibe el correo."
          error={formState.errors.email?.sender_name?.message}
          {...register("email.sender_name")}
        />
        <Field
          label="Responder a (opcional)"
          type="email"
          autoComplete="off"
          maxLength={REPLY_TO_MAX * 2}
          hint="Si el socio responde, le llega a este correo."
          error={formState.errors.email?.reply_to?.message}
          {...register("email.reply_to")}
        />
      </fieldset>
      <fieldset className={styles.group}>
        <legend className={styles.legend}>WhatsApp</legend>
        <div className={styles.channelHead}>
          <label className={styles.toggle}>
            <input type="checkbox" className={styles.checkbox} {...register("whatsapp.enabled")} />
            Ofrecer WhatsApp manual (lista «Por avisar hoy»)
          </label>
          <CredentialsBadge ready={null} />
        </div>
        <Field
          label="Indicativo del país"
          inputMode="numeric"
          autoComplete="off"
          maxLength={6}
          hint="Solo dígitos, sin el signo +. Colombia es 57."
          error={formState.errors.whatsapp?.country_code?.message}
          {...register("whatsapp.country_code")}
        />
      </fieldset>
      <fieldset className={styles.group}>
        <legend className={styles.legend}>Telegram</legend>
        <div className={styles.channelHead}>
          <label className={styles.toggle}>
            <input type="checkbox" className={styles.checkbox} {...register("telegram.enabled")} />
            Avisar al equipo por Telegram
          </label>
          <CredentialsBadge ready={credentials.telegram} />
        </div>
        <p className={styles.note}>Es un canal interno del equipo (resumen diario y alertas): nunca le escribe a un socio.</p>
      </fieldset>
    </SettingsFormFrame>
  );
}

export function ChannelsSettingsForm({ onDirtyChange }: SettingsFormProps) {
  const api = useSettingsSection("channels");
  const section = api.query.data;
  if (!section) return <SectionLoadState query={api.query} />;
  return <ChannelsFields section={section} api={api} onDirtyChange={onDirtyChange} />;
}

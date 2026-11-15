// S8-F5 · US-175 (S8-D30, S8-D32, L-4): pestaña «Pantalla de TV» de Configuración (?tab=tv, Config.html «7 · Pantalla TV»).
// - Refresco (15 a 300 s, S8-D33) y «Mostrar el ranking»: PATCH /settings/tv con solo esos dos campos y la versión leída.
// - Token: el estado dice si hay uno, cómo termina y cuándo se generó; nunca el valor. «Generar enlace nuevo» y «Revocar» piden
//   confirmación. El enlace con `#token=` (S8-D32) se ve UNA vez: vive solo en el estado de este componente, la mutación tiene
//   gcTime 0 y la caché de la sección se relee (no se escribe con la respuesta); al pulsar «Listo» o salir, desaparece.
// DESIGN-GAP: Config.html dibuja el enlace «con token» visible y editable desde el principio; aquí el token no se puede volver a ver
// (el api solo guarda su hash), así que se muestra una vez, al generarlo. Tampoco hay «Abrir» sin token vigente.
import { useState } from "react";
import { formatDateTime } from "../../../core/i18n/format";
import { Button } from "../../../shared/ui/Button";
import { ConfirmModal } from "../../../shared/ui/ConfirmModal";
import { Field } from "../../../shared/ui/Field";
import { useRegenerateTvToken, useRevokeTvToken, useSettingsSection, type IssuedTvLink, type SettingsSection, type SettingsSectionApi, type TvView } from "../api";
import { tvSettingsSchema, TV_REFRESH_MAX, TV_REFRESH_MIN, type TvSettingsForm as TvForm } from "../schemas";
import { regenerateTokenError, revokeTokenError } from "../tvErrors";
import { LinkField } from "./LinkField";
import { SectionLoadState, SettingsFormFrame, type SettingsFormProps } from "./SettingsFormFrame";
import styles from "./SettingsForm.module.css";
import tvStyles from "./TvSettingsForm.module.css";
import { useSectionForm } from "./useSectionForm";

export const TV_HANDOFF =
  "Genera el enlace en otro equipo y pégalo en la TV: así no queda en el historial de este navegador. Se ve una sola vez; al pulsar «Listo» ya no se puede volver a ver (para eso se genera otro). Usa HTTPS (perfil tls) para que no viaje en claro por la red del box. La TV cierra la sesión del panel del navegador donde se abre: no la abras en este equipo si sigues trabajando aquí.";

const SHOWN =
  "Qué muestra: nombre e inicial del apellido (Ana P.), nivel y marca del ranking «Todos» (hasta 50 filas) y el WOD de hoy con sus cargas. Nunca documento, teléfono, correo, sexo ni notas. No aparecen socios dados de baja ni sin autorización de datos vigente.";

type Modal = "regenerate" | "revoke" | null;

function toForm(value: TvView): TvForm {
  return { refresh_seconds: String(value.refresh_seconds), show_leaderboard: value.show_leaderboard };
}

function toInput(values: TvForm): { refresh_seconds: number; show_leaderboard: boolean } {
  return { refresh_seconds: Number(values.refresh_seconds), show_leaderboard: values.show_leaderboard };
}

const FIELD_MESSAGES = { refresh_seconds: "El servidor no aceptó este valor. Escribe un número entre 15 y 300." };

function TokenState({ view }: { view: TvView }) {
  if (!view.has_token) return <p className={tvStyles.state}>Sin token: la pantalla de la pared no puede abrirse.</p>;
  const since = view.rotated_at ? ` · generado el ${formatDateTime(view.rotated_at)}` : "";
  const ending = view.token_last4 ? ` · termina en ${view.token_last4}` : "";
  return <p className={tvStyles.state}>{`Token activo${ending}${since}`}</p>;
}

function TokenCard({ view }: { view: TvView }) {
  const regenerate = useRegenerateTvToken();
  const revoke = useRevokeTvToken();
  const [modal, setModal] = useState<Modal>(null);
  const [issued, setIssued] = useState<IssuedTvLink | null>(null);

  const doRegenerate = async (): Promise<void> => {
    try {
      setIssued(await regenerate.mutateAsync());
    } catch (error) {
      throw regenerateTokenError(error);
    }
  };
  const doRevoke = async (): Promise<void> => {
    try {
      await revoke.mutateAsync();
      setIssued(null);
    } catch (error) {
      throw revokeTokenError(error);
    }
  };

  return (
    <div className={tvStyles.token}>
      <h3 className={tvStyles.heading}>Enlace de la TV</h3>
      <TokenState view={view} />
      {issued ? (
        <div className={tvStyles.issued} role="group" aria-label="Enlace nuevo de la TV">
          <LinkField label="Enlace de la TV" name="tv_link" url={issued.url} handoff={TV_HANDOFF} />
          <a className={tvStyles.open} href={issued.url} target="_blank" rel="noopener noreferrer">
            Abrir la TV
          </a>
          <div className={tvStyles.actions}>
            <Button
              onClick={() => {
                setIssued(null);
              }}
            >
              Listo
            </Button>
          </div>
        </div>
      ) : (
        <div className={tvStyles.actions}>
          <Button
            variant={view.has_token ? "secondary" : "primary"}
            onClick={() => {
              setModal("regenerate");
            }}
          >
            Generar enlace nuevo
          </Button>
          {view.has_token ? (
            <Button
              variant="secondary"
              onClick={() => {
                setModal("revoke");
              }}
            >
              Revocar
            </Button>
          ) : null}
        </div>
      )}
      <ConfirmModal
        open={modal === "regenerate"}
        title="¿Generar un enlace nuevo?"
        consequence={
          view.has_token
            ? "El enlace anterior deja de servir al instante: la pantalla actual mostrará «Token inválido» hasta que abras el enlace nuevo."
            : "Se crea el primer enlace de la pantalla. Se ve una sola vez."
        }
        confirmLabel="Generar enlace"
        tone="primary"
        onConfirm={doRegenerate}
        onClose={() => {
          setModal(null);
        }}
      />
      <ConfirmModal
        open={modal === "revoke"}
        title="¿Revocar el token de la TV?"
        consequence="La pantalla dejará de abrir hasta que generes otro enlace."
        confirmLabel="Revocar token"
        onConfirm={doRevoke}
        onClose={() => {
          setModal(null);
        }}
      />
    </div>
  );
}

function TvFields({ section, api, onDirtyChange }: SettingsFormProps & { section: SettingsSection<"tv">; api: SettingsSectionApi<"tv"> }) {
  const { form, submitValues, frame } = useSectionForm({
    section,
    api,
    schema: tvSettingsSchema,
    toForm,
    toInput,
    fieldMessages: FIELD_MESSAGES,
    onDirtyChange,
  });
  const { register, formState } = form;

  return (
    <SettingsFormFrame
      title="Pantalla de TV"
      description="La pantalla de la pared del box: el WOD de hoy y el ranking. No tiene usuario: abre con un enlace secreto."
      summary={<p className={styles.note}>{SHOWN}</p>}
      onSubmit={(event) => {
        void form.handleSubmit(submitValues)(event);
      }}
      {...frame}
    >
      <Field
        label="Refresco de la pantalla (segundos)"
        required
        type="number"
        inputMode="numeric"
        min={TV_REFRESH_MIN}
        max={TV_REFRESH_MAX}
        step={1}
        hint={`Cada cuánto vuelve a pedir el tablero. Entre ${String(TV_REFRESH_MIN)} y ${String(TV_REFRESH_MAX)}. Por defecto: 30.`}
        error={formState.errors.refresh_seconds?.message}
        {...register("refresh_seconds")}
      />
      <label className={styles.toggle}>
        <input type="checkbox" className={styles.checkbox} {...register("show_leaderboard")} />
        Mostrar el ranking
      </label>
      <div className={styles.wide}>
        <TokenCard view={section.value} />
      </div>
    </SettingsFormFrame>
  );
}

export function TvSettingsForm({ onDirtyChange }: SettingsFormProps) {
  const api = useSettingsSection("tv");
  const section = api.query.data;
  if (!section) return <SectionLoadState query={api.query} />;
  return <TvFields section={section} api={api} onDirtyChange={onDirtyChange} />;
}

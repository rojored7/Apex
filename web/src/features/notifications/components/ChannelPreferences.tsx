// S5-F3 · US-123 (front): preferencias de canal de aviso de un socio, en la pestaña Avisos de su ficha.
// - GET y PATCH /members/{id}/channels: dos interruptores con su etiqueta de texto ("Correo" y "WhatsApp
//   manual"); cada cambio guarda ese canal al momento y avisa "Preferencia guardada.".
// - El correo es opt-in: solo se le escribe al socio si se activa aquí y si autorizó el uso de sus datos
//   (S5-D211: un 422 `consent_required` se muestra con el mensaje del api y el interruptor no cambia).
//   "Sin consentimiento no se avisa": sin esa autorización no sale ningún aviso por ningún canal.
// - S5-D245: sin consentimiento el correo no se puede activar desde aquí (sí desactivar); el 422 del api es el respaldo.
// - Un socio dado de baja es de solo lectura (N-20).
// DESIGN-GAP: Socio_Ficha.html no dibuja el contenido de la pestaña Avisos (solo la tarjeta "Push activo");
// en v0.2 no hay push ni Telegram para el socio, así que son dos interruptores y un resumen de "se le avisa por".
import { useId, useState } from "react";
import { Button } from "../../../shared/ui/Button";
import { CHANNEL_LABELS } from "../adminSchemas";
import { useMemberChannels, useSetMemberChannel } from "../memberApi";
import { channelsLoadError, channelSaveMessage } from "../memberErrors";
import { channelEnabled, type MemberChannel } from "../memberSchemas";
import styles from "./ChannelPreferences.module.css";

export interface ChannelPreferencesProps {
  memberId: string;
  /** Socio dado de baja: solo se lee. */
  readOnly?: boolean;
}

type Message = { kind: "saved" } | { kind: "error"; text: string };

const CHANNELS: readonly { channel: MemberChannel; hint: string }[] = [
  { channel: "email", hint: "Opt-in: solo si lo activas." },
  { channel: "whatsapp_link", hint: "Lo abre el equipo desde «Por avisar hoy»." },
];

/** "correo y WhatsApp manual": en minúscula solo el correo. */
function effectiveText(effective: readonly string[]): string {
  const names = effective.map((channel) => {
    if (channel === "email") return "correo";
    if (channel === "whatsapp_link") return CHANNEL_LABELS.whatsapp_link;
    return channel;
  });
  if (names.length === 0) return "Se le avisa por: nadie.";
  return `Se le avisa por: ${names.join(" y ")}.`;
}

export function ChannelPreferences({ memberId, readOnly = false }: ChannelPreferencesProps) {
  const titleId = useId();
  const channels = useMemberChannels(memberId);
  const save = useSetMemberChannel(memberId);
  const [message, setMessage] = useState<Message | null>(null);
  const data = channels.data;

  if (!data) {
    const error = channelsLoadError(channels.error);
    if (!error) {
      return (
        <p role="status" className={styles.state}>
          Cargando los canales…
        </p>
      );
    }
    return (
      <div role="alert" className={styles.problem}>
        <p>{error.message}</p>
        <Button
          variant="secondary"
          loading={channels.isFetching}
          onClick={() => {
            void channels.refetch();
          }}
        >
          Reintentar
        </Button>
      </div>
    );
  }

  const change = async (channel: MemberChannel, active: boolean): Promise<void> => {
    setMessage(null);
    try {
      await save.mutateAsync({ channel, active });
      setMessage({ kind: "saved" });
    } catch (error) {
      setMessage({ kind: "error", text: channelSaveMessage(error) });
    }
  };

  return (
    <section aria-labelledby={titleId} className={styles.card}>
      <h2 id={titleId} className={styles.title}>
        Canales de aviso
      </h2>
      <p className={styles.note}>El correo es opt-in: solo se le escribe al socio si lo activas aquí.</p>
      {data.has_consent ? null : (
        <p className={styles.warning}>Sin consentimiento no se avisa: este socio no autorizó el uso de sus datos, así que no recibe avisos por ningún canal.</p>
      )}
      {data.has_consent ? null : <p className={styles.note}>Para activar el correo, primero registra el consentimiento del socio en su ficha (pestaña Datos).</p>}
      {readOnly ? <p className={styles.note}>Este socio está dado de baja: sus preferencias son de solo lectura.</p> : null}
      <div className={styles.switches}>
        {CHANNELS.map(({ channel, hint }) => (
          <div key={channel} className={styles.row}>
            <label className={styles.toggle}>
              <input
                type="checkbox"
                className={styles.checkbox}
                checked={channelEnabled(data, channel)}
                disabled={readOnly || save.isPending || (channel === "email" && !data.has_consent && !channelEnabled(data, channel))}
                aria-describedby={`${titleId}-${channel}`}
                aria-busy={save.isPending ? true : undefined}
                onChange={(event) => {
                  void change(channel, event.target.checked);
                }}
              />
              <span>{CHANNEL_LABELS[channel]}</span>
            </label>
            <span id={`${titleId}-${channel}`} className={styles.hint}>
              {hint}
            </span>
          </div>
        ))}
      </div>
      <p className={styles.summary}>{effectiveText(data.effective)}</p>
      <p aria-live="polite" className={styles.note}>
        {save.isPending ? "Guardando…" : ""}
      </p>
      {message?.kind === "saved" ? (
        <p role="status" className={styles.saved}>
          Preferencia guardada.
        </p>
      ) : null}
      {message?.kind === "error" ? (
        <p role="alert" className={styles.error}>
          {message.text}
        </p>
      ) : null}
    </section>
  );
}

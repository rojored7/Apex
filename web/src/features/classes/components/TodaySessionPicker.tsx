// S7-F4c · S7-D42: selector «Clases de hoy» del check-in en modo quiosco. Lista las sesiones programadas de HOY
// (GET /class-sessions ya está en la lista blanca del quiosco) y, al confirmar otra, pide cambiar de sesión sin salir del modo
// y sin contraseña (el servidor solo acepta hoy y ayer). No aparece fuera del modo tablet ni si no hay otra sesión distinta de la actual.
// S7-F5b (L1): si la actual no está entre las de hoy (por ejemplo, la de ayer), el selector muestra «Elige otra clase» y no una
// sesión que no está abierta.
// S7-V7f (M-5): elegir en la lista NO cambia de clase al instante (las flechas del teclado recorrerían las opciones y
// cambiarían de sesión sin querer, WCAG 3.2.2): el cambio es con el botón «Cambiar de clase».
import { useState } from "react";
import { formatTime24 } from "../../../core/i18n/format";
import { useGym } from "../../../shared/hooks/gymContext";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { useTodaySessions, type SessionView } from "../api";
import { OPEN_BOX } from "./WeekGrid";
import styles from "../pages/CheckInPage.module.css";

const label = (session: SessionView): string => `${formatTime24(session.starts_at)} · ${session.name ?? (session.coach_name ? `Coach ${session.coach_name}` : OPEN_BOX)}`;

export function TodaySessionPicker({ currentId }: { currentId: string }) {
  const { tablet, switchSession } = useGym();
  const query = useTodaySessions(tablet);
  const [choice, setChoice] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sessions = query.data?.items ?? [];
  if (!tablet || !sessions.some((session) => session.id !== currentId)) return null;
  const isListed = sessions.some((session) => session.id === currentId);
  const selected = choice !== "" ? choice : isListed ? currentId : "";
  const canSwitch = selected !== "" && selected !== currentId && !busy;

  const change = (): void => {
    if (!canSwitch) return;
    setError(null);
    setBusy(true);
    void switchSession(`/clases/${selected}/checkin`)
      .then(setError)
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <div className={styles.picker}>
      <Field label="Clases de hoy" name="clases-de-hoy" size="lg">
        {(control) => (
          <select
            {...control}
            value={selected}
            onChange={(event) => {
              setChoice(event.target.value);
            }}
          >
            {isListed ? null : (
              <option value="" disabled>
                Elige otra clase
              </option>
            )}
            {sessions.map((session) => (
              <option key={session.id} value={session.id}>
                {label(session)}
              </option>
            ))}
          </select>
        )}
      </Field>
      <Button size="lg" variant="secondary" disabled={!canSwitch} loading={busy} onClick={change}>
        Cambiar de clase
      </Button>
      {error !== null ? (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

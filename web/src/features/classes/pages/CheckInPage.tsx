// S7-F4 · US-159 y US-161 (front): /clases/:id/checkin (CheckIn.html), tablet del box en GymLayout. Admin y coach (`classes.view`).
// - Una sola cosa por pantalla: registrar llegadas. Izquierda, buscar y tocar «Llegó»; derecha, «Ya llegaron (N)» con «Quitar».
// - Nunca bloquea la puerta: vencida o sin plan entra igual y queda marcada (N-38, N-39). `other_day` y `over_capacity` son
//   advertencias con el 201; los únicos 409 son `already_checked_in` y `session_cancelled`.
// - Modo tablet (S7-D24): solo se lee la sesión, la búsqueda (nombre, estado y foto) y se escribe la asistencia; jamás /members/{id},
//   /reveal ni /attachments salvo la foto. «Vender» sale del modo con la contraseña.
// - Estados: cargando, error con Reintentar (403, 404, 429, 5xx), sesión cancelada, sin asistentes, cupo lleno.
// DESIGN-GAP: el WOD del encabezado («WOD "Helen"») llega con v0.5 (wods).
import { useState } from "react";
import { useParams } from "react-router";
import { formatLongDate, formatTime24 } from "../../../core/i18n/format";
import { useGym, useGymHeader } from "../../../shared/hooks/gymContext";
import type { MemberOption } from "../../../shared/data/members";
import { memberFullName } from "../../../shared/data/members";
import { Button } from "../../../shared/ui/Button";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { useCheckIn, useClassSession, type SessionDetailView } from "../api";
import { checkInMessage, sessionLoadError } from "../classErrors";
import { AttendeeList } from "../components/AttendeeList";
import { CheckInSearch } from "../components/CheckInSearch";
import { OPEN_BOX } from "../components/WeekGrid";
import { knownFlags } from "../flags";
import styles from "./CheckInPage.module.css";

type Outcome = { kind: "ok"; name: string; flags: string[] } | { kind: "error"; message: string };

export const FULL_NOTE = "Cupo lleno: la llegada se registra igual. El coach decide.";

const coachLabel = (session: SessionDetailView): string => (session.coach_name ? `Coach ${session.coach_name}` : OPEN_BOX);

function CheckInContent({ session }: { session: SessionDetailView }) {
  const { requestLeave } = useGym();
  const checkIn = useCheckIn();
  const [text, setText] = useState("");
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const arrived = new Set(session.attendees.map((attendee) => attendee.member_id));
  const cancelled = session.status === "cancelled";
  const full = session.attendance_count >= session.capacity;

  const arrive = async (member: MemberOption): Promise<void> => {
    if (checkIn.isPending) return;
    const name = memberFullName(member);
    try {
      const result = await checkIn.mutateAsync({ sessionId: session.id, memberId: member.id });
      setOutcome({ kind: "ok", name, flags: result.flags });
      setText("");
    } catch (error) {
      setOutcome({ kind: "error", message: checkInMessage(error) });
    }
  };

  return (
    <div className={styles.columns}>
      <section className={styles.left} aria-label="Registrar llegada">
        {cancelled ? (
          <p className={styles.cancelled}>{`Esta sesión fue cancelada${session.cancel_reason ? `: ${session.cancel_reason}` : ""}. Ya no se puede registrar la llegada.`}</p>
        ) : (
          <>
            <CheckInSearch
              text={text}
              onTextChange={setText}
              arrived={arrived}
              pending={checkIn.isPending}
              onArrive={(member) => {
                void arrive(member);
              }}
              onSell={(member) => {
                requestLeave(`/membresias/vender?socio=${encodeURIComponent(member.id)}`);
              }}
            />
            <div role="status" aria-label="Resultado del check-in" className={styles.outcome}>
              {outcome?.kind === "ok" ? (
                <p className={styles.ok}>
                  {`${outcome.name} llegó.`}{" "}
                  {knownFlags(outcome.flags).map((flag) => (
                    <StatusTag key={flag} flag={flag} />
                  ))}
                </p>
              ) : null}
            </div>
            {outcome?.kind === "error" ? (
              <p role="alert" className={styles.error}>
                {outcome.message}
              </p>
            ) : null}
            {full ? <p className={styles.warn}>{FULL_NOTE}</p> : null}
            <p className={styles.note}>Vencida o sin plan: entra igual, queda marcado y el coach lo ve en rojo. Nunca se bloquea la puerta desde la app.</p>
          </>
        )}
      </section>
      <AttendeeList attendees={session.attendees} />
    </div>
  );
}

export default function CheckInPage() {
  const { id = "" } = useParams();
  const query = useClassSession(id);
  const session = query.data;
  useGymHeader(
    session
      ? {
          title: `Check-in · ${formatTime24(session.starts_at)} · ${coachLabel(session)}`,
          subtitle: `${formatLongDate(session.session_date)} · cupo ${String(session.capacity)}`,
          counter: { value: session.attendees.length, of: session.capacity, label: "llegaron" },
        }
      : null,
  );

  if (query.isPending) {
    return (
      <div role="status" aria-label="Cargando la sesión" className={styles.state}>
        Cargando la sesión…
      </div>
    );
  }
  if (query.isError || !session) {
    const error = sessionLoadError(query.error);
    return (
      <div className={styles.state}>
        <p role="alert" className={styles.error}>
          {error?.message}
        </p>
        <Button
          size="lg"
          variant="secondary"
          onClick={() => {
            void query.refetch();
          }}
        >
          Reintentar
        </Button>
      </div>
    );
  }
  return <CheckInContent session={session} />;
}

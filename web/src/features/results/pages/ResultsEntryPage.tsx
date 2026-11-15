// S8-F4 · US-169 y US-170 (front): /clases/:id/resultados (Resultados_Registro.html), tablet del box en GymLayout y modo quiosco
// (S8-D15). Admin y coach (`results.record`).
// - Izquierda: «Asistieron» con la marca de cada uno o «sin registrar» y «+ Alguien que no hizo check-in». Derecha: el formulario
//   del elegido (por `score_type`), «Guardar y siguiente» y «Omitir». El contador «7 / 11 registrados» va en la barra.
// - Un resultado ya registrado se muestra lleno y guardar lo corrige: `PUT /results` con `supersedes_id` y el MISMO `session_id`
//   (S8-B1d M-3). No hay «mover a otra sesión»: un resultado en el socio o la clase equivocados lo anula un admin desde el WOD.
// - S8-D24: nunca llama /reveal ni /members/{id}. 403 `kiosk_mode` (corregir uno de escritorio), 409 y 422 se explican en la pantalla.
// - Estados: cargando, error con Reintentar, sin WOD, WOD sin marca, sesión cancelada, sin asistentes, guardando.
import { useRef, useState } from "react";
import { useParams } from "react-router";
import { formatLongDate, formatTime24 } from "../../../core/i18n/format";
import { useGymHeader } from "../../../shared/hooks/gymContext";
import { Button } from "../../../shared/ui/Button";
import { useSaveResult, useSessionAttendance } from "../api";
import { AddWalkIn } from "../components/AddWalkIn";
import { AttendeeResults } from "../components/AttendeeResults";
import { ScoreForm } from "../components/ScoreForm";
import { resultsLoadError, saveMessage } from "../resultErrors";
import { attendeeName, type AttendeeResultView, type ScoreValues, type ScoringType } from "../schemas";
import styles from "./ResultsEntryPage.module.css";

export const NO_WOD_MESSAGE = "Esta clase no tiene WOD asignado. Pídele a un administrador que lo asigne desde Clases y vuelve aquí.";
export const NO_SCORE_MESSAGE = "El WOD de esta clase no registra resultados: es un WOD sin marca.";
export const EMPTY_MESSAGE = "Nadie ha llegado todavía. Registra la llegada en el check-in o agrega a alguien aquí abajo.";
export const CANCELLED_MESSAGE = "Esta sesión fue cancelada. Ya no se pueden registrar resultados.";
const SCORE_LABELS: Readonly<Record<ScoringType, string>> = { time: "Por tiempo", rounds_reps: "Rondas + repeticiones", reps: "Repeticiones", load: "Carga" };
const SECONDS_PER_MINUTE = 60;

/** El próximo asistente sin marca después de `currentId` (con vuelta al principio); null si no hay otro. */
export function nextPending(items: readonly AttendeeResultView[], currentId: string): string | null {
  const start = items.findIndex((item) => item.member_id === currentId);
  const ordered = [...items.slice(start + 1), ...items.slice(0, Math.max(start, 0))];
  return ordered.find((item) => !item.has_result && item.member_id !== currentId)?.member_id ?? null;
}

export default function ResultsEntryPage() {
  const { id = "" } = useParams();
  const query = useSessionAttendance(id);
  const save = useSaveResult();
  const inFlight = useRef(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const data = query.data;
  const items = data?.items ?? [];
  const wod = data?.wod ?? null;
  const registered = items.filter((item) => item.has_result).length;

  useGymHeader(
    data && wod
      ? {
          title: `Resultados · ${wod.title} · ${formatTime24(data.session.starts_at)}`,
          subtitle: `${formatLongDate(data.session.session_date)}${wod.score_type === "none" ? "" : ` · ${SCORE_LABELS[wod.score_type]}`}${wod.time_cap_s === null ? "" : ` · límite ${String(Math.round(wod.time_cap_s / SECONDS_PER_MINUTE))} min`}`,
          counter: { value: registered, of: items.length, label: "registrados" },
        }
      : null,
  );

  if (query.isPending) {
    return (
      <div role="status" aria-label="Cargando la clase" className={styles.state}>
        Cargando la clase…
      </div>
    );
  }
  if (query.isError || !data) {
    return (
      <div className={styles.state}>
        <p role="alert" className={styles.error}>
          {resultsLoadError(query.error)?.message}
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
  if (data.session.status === "cancelled") return <p className={styles.notice}>{CANCELLED_MESSAGE}</p>;
  if (wod === null) return <p className={styles.notice}>{NO_WOD_MESSAGE}</p>;
  if (wod.score_type === "none") return <p className={styles.notice}>{NO_SCORE_MESSAGE}</p>;

  const scoreType: ScoringType = wod.score_type;
  const effectiveId = selectedId ?? items.find((item) => !item.has_result)?.member_id ?? items[0]?.member_id ?? null;
  const selected = items.find((item) => item.member_id === effectiveId) ?? null;
  const present = new Set(items.map((item) => item.member_id));

  const choose = (memberId: string): void => {
    setSaveError(null);
    setSelectedId(memberId);
  };

  const submit = async (score: ScoreValues): Promise<void> => {
    if (selected === null || inFlight.current) return;
    inFlight.current = true;
    setSaveError(null);
    try {
      await save.mutateAsync({ wodId: wod.id, memberId: selected.member_id, sessionId: id, score, supersedesId: selected.result?.id });
      const next = nextPending(items, selected.member_id);
      if (next !== null) setSelectedId(next);
    } catch (error) {
      setSaveError(saveMessage(error));
    } finally {
      inFlight.current = false;
    }
  };

  return (
    <div className={styles.columns}>
      <section className={styles.left} aria-label="Asistentes">
        {items.length === 0 ? <p className={styles.notice}>{EMPTY_MESSAGE}</p> : <AttendeeResults attendees={items} scoreType={scoreType} selectedId={effectiveId} onSelect={choose} />}
        <AddWalkIn sessionId={id} presentIds={present} onReady={choose} />
      </section>
      <section className={styles.right} aria-label="Registrar resultado">
        {selected !== null ? (
          <ScoreForm
            key={`${selected.member_id}:${selected.result?.id ?? "nuevo"}`}
            wod={wod}
            memberName={attendeeName(selected)}
            initial={selected.result}
            pending={save.isPending}
            error={saveError}
            onSubmit={(score) => {
              void submit(score);
            }}
            onSkip={() => {
              const next = nextPending(items, selected.member_id);
              if (next !== null) choose(next);
            }}
          />
        ) : selectedId !== null ? (
          <p role="status" className={styles.notice}>
            Actualizando la lista…
          </p>
        ) : (
          <p className={styles.notice}>Elige a un atleta de la lista para registrar su marca.</p>
        )}
        <p className={styles.note}>Un resultado por atleta por WOD. Si ya existe, se muestra lleno y guardar lo corrige dejando el valor anterior en la auditoría.</p>
      </section>
    </div>
  );
}

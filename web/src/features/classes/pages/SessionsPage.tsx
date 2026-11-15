// S7-F3 · US-157 (front): /clases (Sesiones.html), admin y coach (`classes.view`).
// - PageHeader «Clases» con «+ Sesión extra» y «Check-in de la próxima clase» (la primera sesión de hoy que aún no termina).
// - Semana en la URL (`?semana=AAAA-Www`): sin ella, inválida o con `?dia=hoy` es la semana de hoy en Bogotá. «‹ Semana anterior»,
//   «Semana siguiente ›» y «Hoy» solo cambian la URL; el filtro de coach es local sobre la semana cargada.
// - WeekGrid con las sesiones de la semana (GET /class-sessions?week, hasta 200) y SessionDetail de la elegida; CancelSessionModal
//   y ExtraSessionPanel. Al cancelar o crear, las semanas se releen (invalidación) y un aviso lo dice.
// - Estados: carga, semana sin sesiones (guía a crear una extra), error con Reintentar, 403 y semana con más de 200 sesiones.
// DESIGN-GAP: «Cada noche el sistema crea las sesiones de los próximos 14 días» (Sesiones.html): el job corre a las 07:00 (S7-D10),
// así que el texto dice «cada mañana»; los 14 días son fijos (Q23).
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { todayBogota } from "../../../core/i18n/format";
import { Button } from "../../../shared/ui/Button";
import { PageHeader, type PageAction } from "../../../shared/ui/PageHeader";
import { useSessions, type SessionView } from "../api";
import { sessionsListError } from "../classErrors";
import { CancelSessionModal } from "../components/CancelSessionModal";
import { ClassesTabs } from "../components/ClassesTabs";
import { ExtraSessionPanel } from "../components/ExtraSessionPanel";
import { checkInHref, SessionDetail } from "../components/SessionDetail";
import { WeekGrid } from "../components/WeekGrid";
import { bogotaTime, currentWeek, parseWeek, shiftWeek, weekDates, weekLabel } from "../weeks";
import styles from "./SessionsPage.module.css";

export const WEEK_PARAM = "semana";
export const DAY_PARAM = "dia";
const ALL_COACHES = "";
const NO_COACH = "none";

export const EMPTY_WEEK = "Esta semana no tiene sesiones. Se generan solas desde el horario semanal; también puedes crear una sesión extra.";
export const HOW_THEY_ARE_BORN =
  "Cada mañana a las 7:00 el sistema crea las sesiones de los próximos 14 días a partir del horario semanal. Lo que ya existe no se toca si cambias el horario. Una sesión extra o una cancelación se hace aquí, sesión por sesión.";

export const truncatedNote = (shown: number, total: number): string =>
  `Se muestran ${String(shown)} de ${String(total)} sesiones de esta semana. Filtra por coach o cambia de semana para ver las demás.`;

/** La semana que pide la URL: la de hoy con `?dia=hoy`, la de `?semana=` si es válida, o la de hoy. */
function useWeek(): [string, (week: string | null) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const week = searchParams.get(DAY_PARAM) === "hoy" ? currentWeek() : (parseWeek(searchParams.get(WEEK_PARAM)) ?? currentWeek());
  const go = (next: string | null): void => {
    if (next === null) return;
    setSearchParams({ [WEEK_PARAM]: next });
  };
  return [week, go];
}

/** Opciones del filtro de coach: los de las sesiones cargadas y «Sin coach» si alguna no tiene. */
function coachOptions(sessions: readonly SessionView[]): { value: string; label: string }[] {
  const byId = new Map<string, string>();
  let hasOpen = false;
  for (const session of sessions) {
    if (session.coach_id === null) hasOpen = true;
    else byId.set(session.coach_id, session.coach_name ?? "Coach");
  }
  const named = [...byId.entries()].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label, "es"));
  return [...named, ...(hasOpen ? [{ value: NO_COACH, label: "Sin coach" }] : [])];
}

/** La primera sesión de hoy programada que aún no termina (para «Check-in de la próxima clase»). */
function nextSession(sessions: readonly SessionView[], today: string): SessionView | null {
  const now = Date.now();
  return (
    sessions
      .filter((s) => s.session_date === today && s.status === "scheduled" && new Date(s.starts_at).getTime() + s.duration_min * 60_000 > now)
      .sort((a, b) => a.starts_at.localeCompare(b.starts_at))[0] ?? null
  );
}

export default function SessionsPage() {
  const canView = useCan("classes.view");
  const [week, goToWeek] = useWeek();
  const sessions = useSessions(week, canView);
  const [coach, setCoach] = useState(ALL_COACHES);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState<SessionView | null>(null);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const today = todayBogota();
  const dates = useMemo(() => weekDates(week), [week]);
  const loaded = sessions.isPlaceholderData ? undefined : sessions.data;
  const all = useMemo(() => loaded?.items ?? [], [loaded]);
  const visible = useMemo(() => all.filter((s) => coach === ALL_COACHES || (coach === NO_COACH ? s.coach_id === null : s.coach_id === coach)), [all, coach]);
  const selected = visible.find((s) => s.id === selectedId) ?? null;
  const next = nextSession(all, today);
  const error = sessionsListError(sessions.error);
  const loading = sessions.isLoading || sessions.isPlaceholderData;

  const actions: PageAction[] = [
    { id: "extra", label: "+ Sesión extra", variant: "secondary", onClick: () => {
      setCreating(true);
    } },
    ...(next ? [{ id: "checkin", label: "Check-in de la próxima clase", variant: "primary" as const, href: checkInHref(next.id) }] : []),
  ];

  return (
    <div className={styles.page}>
      <PageHeader title="Clases" actions={actions} />
      <ClassesTabs>
        <div className={styles.content}>
          <div className={styles.weekBar}>
            <Button
              variant="secondary"
              onClick={() => {
                goToWeek(shiftWeek(week, -1));
              }}
            >
              ‹ Semana anterior
            </Button>
            <b className={styles.label}>{weekLabel(week)}</b>
            <Button
              variant="secondary"
              onClick={() => {
                goToWeek(shiftWeek(week, 1));
              }}
            >
              Semana siguiente ›
            </Button>
            <Link className={styles.today} to={`?${WEEK_PARAM}=${currentWeek()}`}>
              Hoy
            </Link>
            <span className={styles.spacer} />
            <label className={styles.coach}>
              <span className={styles.visually}>Coach</span>
              <select
                className={styles.select}
                value={coach}
                onChange={(event) => {
                  setCoach(event.target.value);
                }}
              >
                <option value={ALL_COACHES}>Todos los coaches</option>
                {coachOptions(all).map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {notice ? (
            <p className={styles.notice} role="status">
              {notice}
            </p>
          ) : null}
          {error ? (
            <div className={styles.error} role="alert">
              <p>{error.message}</p>
              <Button
                variant="secondary"
                onClick={() => {
                  void sessions.refetch();
                }}
              >
                Reintentar
              </Button>
            </div>
          ) : loading ? (
            <p className={styles.note} role="status">
              Cargando sesiones…
            </p>
          ) : (
            <>
              <WeekGrid dates={dates} today={today} sessions={visible} selectedId={selected?.id ?? null} onSelect={(session) => { setSelectedId(session.id); }} />
              {loaded && loaded.total === 0 ? <p className={styles.note}>{EMPTY_WEEK}</p> : null}
              {loaded && loaded.total > all.length ? <p className={styles.note}>{truncatedNote(all.length, loaded.total)}</p> : null}
            </>
          )}
          {selected ? <SessionDetail session={selected} onCancel={setCancelling} /> : null}
          <p className={styles.note}>{HOW_THEY_ARE_BORN}</p>
        </div>
      </ClassesTabs>
      <ExtraSessionPanel
        open={creating}
        onClose={() => {
          setCreating(false);
        }}
        onCreated={(session) => {
          setNotice(`Sesión extra de las ${bogotaTime(session.starts_at)} creada.`);
        }}
      />
      <CancelSessionModal
        session={cancelling}
        onClose={() => {
          setCancelling(null);
        }}
        onDone={(session) => {
          setNotice(`Sesión de las ${bogotaTime(session.starts_at)} cancelada.`);
        }}
      />
    </div>
  );
}

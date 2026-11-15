// S7-F3 · US-157 (front): sesión extra (Sesiones.html, «+ Sesión extra») en un SidePanel, admin y coach (`classes.view`).
// - React Hook Form + Zod (extraSessionSchema): Fecha y hora (hora de Bogotá; viaja en UTC), Duración, Cupo (opcional: sin él
//   usa el de Configuración), Coach y Nombre (opcional).
// - Coach: el admin elige entre los coaches y admins activos (GET /users) o nadie; el coach solo puede ponerse a sí mismo o
//   a nadie (el api lo exige, L-3) y no lee la lista de usuarios.
// - 409 `session_duplicate` y 422 `starts_at` bajo la fecha; `coach_invalid` bajo el coach; 403, 429, 5xx y red como aviso.
// - 201: avisa al padre y cierra; useCreateSession ya invalidó las semanas.
import { useId, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useSession } from "../../../core/auth/session";
import { useCan } from "../../../core/auth/useCan";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { useCoachCandidates, useCreateSession, type SessionView } from "../api";
import { extraSessionFieldError, extraSessionSaveMessage } from "../classErrors";
import { emptyExtraSessionForm, extraSessionSchema, toSessionCreate, type ExtraSessionFormValues } from "../schemas";
import styles from "./SlotPanel.module.css";

export interface ExtraSessionPanelProps {
  open: boolean;
  onClose: () => void;
  /** La sesión ya quedó creada (el padre avisa y cierra). */
  onCreated: (session: SessionView) => void;
}

export const EXTRA_SESSION_TITLE = "Sesión extra";
export const OPEN_BOX_LABEL = "Sin coach (open box)";

const resolver = zodResolver(extraSessionSchema);

export function ExtraSessionPanel({ open, onClose, onCreated }: ExtraSessionPanelProps) {
  const formId = useId();
  const create = useCreateSession();
  const session = useSession();
  const chooseAnyCoach = useCan("classes.schedule");
  const coaches = useCoachCandidates(open && chooseAnyCoach);
  const [initialValues] = useState<ExtraSessionFormValues>(() => emptyExtraSessionForm());
  const form = useForm<ExtraSessionFormValues>({ resolver, defaultValues: initialValues });
  const {
    register,
    formState: { errors, isDirty },
  } = form;
  const [generalError, setGeneralError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const isPending = create.isPending;
  const myUser = session.user;

  const resetAll = (): void => {
    create.reset();
    form.reset(emptyExtraSessionForm());
    setGeneralError(null);
  };

  /** Mientras se guarda no se cierra: la sesión podría quedar creada sin aviso. */
  const close = (): void => {
    if (isPending) return;
    resetAll();
    onClose();
  };

  const save = async (values: ExtraSessionFormValues): Promise<void> => {
    if (inFlight.current) return;
    inFlight.current = true;
    setGeneralError(null);
    try {
      const created = await create.mutateAsync(toSessionCreate(values));
      resetAll();
      onCreated(created);
      onClose();
    } catch (error) {
      const target = extraSessionFieldError(error);
      if (target) {
        form.setError(target.path, { type: "server", message: target.message }, { shouldFocus: true });
        return;
      }
      setGeneralError(extraSessionSaveMessage(error));
    } finally {
      inFlight.current = false;
    }
  };

  const candidates = chooseAnyCoach ? (coaches.data ?? []) : myUser ? [{ id: myUser.id, email: `Yo (${myUser.email})` }] : [];
  const coachReady = !chooseAnyCoach || coaches.isSuccess || coaches.isError;

  return (
    <SidePanel
      open={open}
      title={EXTRA_SESSION_TITLE}
      isDirty={!isPending && isDirty}
      onClose={close}
      footer={
        <Button type="submit" form={formId} loading={isPending}>
          {isPending ? "Guardando…" : "Crear sesión"}
        </Button>
      }
    >
      <form id={formId} className={styles.form} noValidate aria-label={EXTRA_SESSION_TITLE} onSubmit={(event) => void form.handleSubmit(save)(event)}>
        {generalError ? (
          <p className={styles.error} role="alert">
            {generalError}
          </p>
        ) : null}
        <Field label="Fecha y hora" type="datetime-local" required error={errors.starts_at?.message} {...register("starts_at")} />
        <div className={styles.pair}>
          <Field label="Duración (min)" inputMode="numeric" autoComplete="off" required error={errors.duration_min?.message} {...register("duration_min")} />
          <Field
            label="Cupo (opcional)"
            inputMode="numeric"
            autoComplete="off"
            hint="Vacío usa el cupo por defecto de Configuración."
            error={errors.capacity?.message}
            {...register("capacity")}
          />
        </div>
        {coachReady ? (
          <Field label="Coach" name="coach_id" error={errors.coach_id?.message}>
            {(control) => (
              <select {...control} {...register("coach_id")}>
                <option value="">{OPEN_BOX_LABEL}</option>
                {candidates.map((coach) => (
                  <option key={coach.id} value={coach.id}>
                    {coach.email}
                  </option>
                ))}
              </select>
            )}
          </Field>
        ) : (
          <Field label="Coach" name="coach_id" hint="Cargando coaches…">
            {(control) => (
              <select {...control} disabled>
                <option value="">{OPEN_BOX_LABEL}</option>
              </select>
            )}
          </Field>
        )}
        {chooseAnyCoach && coaches.isError ? <p className={styles.note}>No pudimos cargar los coaches. Puedes crear la sesión sin coach.</p> : null}
        <Field label="Nombre (opcional)" autoComplete="off" placeholder="Open box festivo, Halterofilia…" error={errors.name?.message} {...register("name")} />
        <p className={styles.note}>La sesión extra no sale del horario semanal: se crea una sola vez, para la fecha y la hora que elijas.</p>
      </form>
    </SidePanel>
  );
}

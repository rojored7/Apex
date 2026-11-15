// S7-F2 · US-155 (front): alta y edición de una franja del horario en el SidePanel de Horario.html (solo admin).
// - React Hook Form + Zod (slotFormSchema): Días (L M X J V S D), Hora de inicio, Duración, Coach, Cupo, Nombre,
//   Vigente desde y, al editar, Activa. Los números viajan como texto y toSlotCreate los vuelve enteros.
// - El coach sale de GET /users (admin y coach activos, por correo) más «Sin coach (open box)».
// - Crear: POST /class-slots. Editar: PATCH /class-slots/{id} solo con los campos modificados (toSlotPatch); sin
//   cambios no sale nada y el panel se cierra. Un solo envío a la vez.
// - 409 `slot_conflict` bajo los días; 422 con `field` y `coach_invalid` bajo su campo; 403, 404, 429, 5xx y red como
//   aviso general.
// - Al editar ofrece «Cancelar sesiones futuras» (US-158), que abre el modal desde el padre.
// DESIGN-GAP: el coach se muestra por correo: GET /users no trae nombre (la franja guardada sí lo trae como `coach_name`).
// DESIGN-GAP: Horario.html dice «Al guardar se regeneran las sesiones futuras de esta franja»; contradice Q23 (un
// PATCH nunca toca sesiones, BRECHAS 15.5): el aviso dice que los cambios valen para las sesiones aún no generadas.
import { useId, useRef, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { cx } from "../../../shared/ui/cx";
import { Field } from "../../../shared/ui/Field";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { useCoachCandidates, useCreateSlot, useUpdateSlot, type CoachCandidate, type SlotView } from "../api";
import { slotFieldError, slotSaveMessage } from "../classErrors";
import {
  EMPTY_SLOT_FORM,
  slotFormSchema,
  slotToFormValues,
  toSlotCreate,
  toSlotPatch,
  WEEKDAY_LETTERS,
  WEEKDAY_NAMES,
  WEEKDAY_VALUES,
  type SlotFormValues,
} from "../schemas";
import styles from "./SlotPanel.module.css";

export interface SlotPanelProps {
  open: boolean;
  /** La franja a editar; null crea una nueva. */
  slot: SlotView | null;
  onClose: () => void;
  /** La franja ya quedó guardada (el padre avisa y cierra). */
  onSaved: (slot: SlotView, created: boolean) => void;
  /** Abre «Cancelar sesiones futuras» de esta franja. */
  onCancelFuture?: (slot: SlotView) => void;
}

export const NEW_SLOT_TITLE = "Nueva franja";
export const OPEN_BOX_LABEL = "Sin coach (open box)";
export const GENERATION_NOTE = 'Los cambios valen para las sesiones que aún no se generaron. Para mover las ya generadas usa "Cancelar sesiones futuras".';

export const editSlotTitle = (time: string): string => `Editar franja · ${time}`;

const resolver = zodResolver(slotFormSchema);

function coachOptions(candidates: CoachCandidate[], slot: SlotView | null): CoachCandidate[] {
  const current = slot?.default_coach_id;
  if (!current || candidates.some((c) => c.id === current)) return candidates;
  // El coach de la franja ya no está entre los activos: se conserva a la vista para no perderlo sin querer.
  return [...candidates, { id: current, email: slot.coach_name ?? "Coach actual" }];
}

export function SlotPanel({ open, slot, onClose, onSaved, onCancelFuture }: SlotPanelProps) {
  const formId = useId();
  const create = useCreateSlot();
  const update = useUpdateSlot(slot?.id ?? "");
  const coaches = useCoachCandidates(open);
  const [initialValues] = useState<SlotFormValues>(() => (slot ? slotToFormValues(slot) : EMPTY_SLOT_FORM));
  const form = useForm<SlotFormValues>({ resolver, defaultValues: initialValues });
  const {
    register,
    control,
    formState: { errors, isDirty },
  } = form;
  const [generalError, setGeneralError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const isEditing = slot !== null;
  const isPending = create.isPending || update.isPending;
  const title = slot ? editSlotTitle(slot.start_time) : NEW_SLOT_TITLE;
  const daysErrorId = `${formId}-days-error`;

  const resetAll = (): void => {
    create.reset();
    update.reset();
    form.reset();
    setGeneralError(null);
  };

  /** Mientras se guarda no se cierra: la franja podría quedar guardada sin aviso. */
  const close = (): void => {
    if (isPending) return;
    resetAll();
    onClose();
  };

  const submit = async (values: SlotFormValues): Promise<void> => {
    if (!slot) {
      const created = await create.mutateAsync(toSlotCreate(values));
      resetAll();
      onSaved(created, true);
      onClose();
      return;
    }
    const patch = toSlotPatch(values, initialValues);
    if (Object.keys(patch).length === 0) {
      close();
      return;
    }
    const saved = await update.mutateAsync(patch);
    form.reset(slotToFormValues(saved));
    setGeneralError(null);
    onSaved(saved, false);
    onClose();
  };

  const save = async (values: SlotFormValues): Promise<void> => {
    if (inFlight.current) return;
    inFlight.current = true;
    setGeneralError(null);
    try {
      await submit(values);
    } catch (error) {
      const target = slotFieldError(error);
      if (target) {
        form.setError(target.path, { type: "server", message: target.message }, { shouldFocus: true });
        return;
      }
      setGeneralError(slotSaveMessage(error));
    } finally {
      inFlight.current = false;
    }
  };

  const daysError = errors.weekdays?.message;
  const candidates = coachOptions(coaches.data ?? [], slot);

  return (
    <SidePanel
      open={open}
      title={title}
      isDirty={!isPending && isDirty}
      onClose={close}
      footer={
        <Button type="submit" form={formId} loading={isPending}>
          {isPending ? "Guardando…" : isEditing ? "Guardar" : "Crear franja"}
        </Button>
      }
    >
      <form id={formId} className={styles.form} noValidate aria-label={title} onSubmit={(event) => void form.handleSubmit(save)(event)}>
        {generalError ? (
          <p className={styles.error} role="alert">
            {generalError}
          </p>
        ) : null}
        <Controller
          control={control}
          name="weekdays"
          render={({ field }) => (
            <fieldset className={styles.days} aria-describedby={daysError ? daysErrorId : undefined} aria-invalid={daysError ? true : undefined}>
              <legend className={styles.legend}>
                Días<span aria-hidden="true"> *</span>
              </legend>
              <div className={styles.dayRow}>
                {WEEKDAY_VALUES.map((day) => {
                  const checked = field.value.includes(day);
                  return (
                    <label key={day} className={cx(styles.day, checked && styles.dayOn)}>
                      <input
                        type="checkbox"
                        className={styles.dayInput}
                        aria-label={WEEKDAY_NAMES[day]}
                        checked={checked}
                        onChange={() => {
                          field.onChange(checked ? field.value.filter((d) => d !== day) : [...field.value, day]);
                        }}
                      />
                      <span aria-hidden="true">{WEEKDAY_LETTERS[day]}</span>
                    </label>
                  );
                })}
              </div>
              {daysError ? (
                <p id={daysErrorId} className={styles.fieldError}>
                  {daysError}
                </p>
              ) : null}
            </fieldset>
          )}
        />
        <div className={styles.pair}>
          <Field label="Hora de inicio" type="time" required error={errors.start_time?.message} {...register("start_time")} />
          <Field label="Duración (min)" inputMode="numeric" autoComplete="off" required error={errors.duration_min?.message} {...register("duration_min")} />
        </div>
        <div className={styles.pair}>
          {coaches.isSuccess || coaches.isError ? (
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
          <Field label="Cupo" inputMode="numeric" type="number" autoComplete="off" required error={errors.capacity?.message} {...register("capacity")} />
        </div>
        {coaches.isError ? <p className={styles.note}>No pudimos cargar los coaches. Puedes guardar la franja y elegirlo después.</p> : null}
        <Field label="Nombre (opcional)" autoComplete="off" placeholder="CrossFit, Open box, Halterofilia…" error={errors.name?.message} {...register("name")} />
        <Field label="Vigente desde" type="date" error={errors.valid_from?.message} {...register("valid_from")} />
        {isEditing ? (
          <label className={styles.check}>
            <input type="checkbox" {...register("is_active")} /> Activa
          </label>
        ) : null}
        <p className={styles.note}>{GENERATION_NOTE}</p>
        {slot && onCancelFuture ? (
          <Button
            variant="secondary"
            disabled={isDirty}
            onClick={() => {
              onCancelFuture(slot);
            }}
          >
            Cancelar sesiones futuras
          </Button>
        ) : null}
        {slot && onCancelFuture && isDirty ? <p className={styles.note}>Guarda o descarta los cambios para cancelar sesiones futuras.</p> : null}
      </form>
    </SidePanel>
  );
}

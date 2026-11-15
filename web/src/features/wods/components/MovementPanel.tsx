// S8-F1 · US-165 (front): alta y edición de un movimiento en el SidePanel de Movimientos.html.
// - React Hook Form + Zod (movementFormSchema): Nombre, Categoría, Unidad y, al editar, Activo.
// - Crear: POST /movements. Editar: PATCH /movements/{id} solo con lo cambiado; sin cambios no sale nada y se cierra.
// - La nota de carga sigue a la unidad (S8-D5): solo kg admite carga en un WOD.
// - 409 `movement_exists` bajo «Nombre»; 422 con `field` bajo su campo; 403, 404, 429, 5xx y red como aviso general.
// DESIGN-GAP: alias, «lb», «Peso corporal» y «Tipos de récord» no existen en el contrato (S8-D5); la unidad es qué se mide.
// DESIGN-GAP: el 409 no enlaza al movimiento existente: no hay ficha de movimiento; se busca en la lista.
import { useId, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { useCreateMovement, useUpdateMovement, type MovementView } from "../api";
import {
  CATEGORY_LABELS,
  EMPTY_MOVEMENT_FORM,
  MOVEMENT_CATEGORIES,
  MOVEMENT_UNITS,
  movementFormSchema,
  movementToFormValues,
  toMovementCreate,
  toMovementPatch,
  UNIT_LABELS,
  type MovementFormValues,
} from "../schemas";
import { movementFieldError, movementSaveMessage } from "../wodErrors";
import styles from "./CatalogPanel.module.css";

export interface MovementPanelProps {
  open: boolean;
  /** El movimiento a editar; null crea uno nuevo. */
  movement: MovementView | null;
  onClose: () => void;
  /** El movimiento ya quedó guardado (el padre avisa y cierra). */
  onSaved: (movement: MovementView, created: boolean) => void;
}

export const NEW_MOVEMENT_TITLE = "Nuevo movimiento";
export const LOAD_NOTE = "Este movimiento admite carga en los WODs.";
export const NO_LOAD_NOTE = "Sin carga: los WODs no piden peso para este movimiento.";
export const RENAME_NOTE = "Los WODs ya guardados conservan su propia copia del nombre: renombrar no los cambia.";

const resolver = zodResolver(movementFormSchema);

export const editMovementTitle = (name: string): string => `Editar movimiento · ${name}`;

export function MovementPanel({ open, movement, onClose, onSaved }: MovementPanelProps) {
  const formId = useId();
  const create = useCreateMovement();
  const update = useUpdateMovement(movement?.id ?? "");
  const [initialValues] = useState<MovementFormValues>(() => (movement ? movementToFormValues(movement) : EMPTY_MOVEMENT_FORM));
  const form = useForm<MovementFormValues>({ resolver, defaultValues: initialValues });
  const {
    register,
    control,
    formState: { errors, isDirty },
  } = form;
  const unit = useWatch({ control, name: "unit" });
  const [generalError, setGeneralError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const isEditing = movement !== null;
  const isPending = create.isPending || update.isPending;
  const title = movement ? editMovementTitle(movement.name) : NEW_MOVEMENT_TITLE;

  const resetAll = (): void => {
    create.reset();
    update.reset();
    form.reset();
    setGeneralError(null);
  };

  /** Mientras se guarda no se cierra: el movimiento podría quedar guardado sin aviso. */
  const close = (): void => {
    if (isPending) return;
    resetAll();
    onClose();
  };

  const submit = async (values: MovementFormValues): Promise<void> => {
    if (!movement) {
      const created = await create.mutateAsync(toMovementCreate(values));
      resetAll();
      onSaved(created, true);
      onClose();
      return;
    }
    const patch = toMovementPatch(values, initialValues);
    if (Object.keys(patch).length === 0) {
      close();
      return;
    }
    const saved = await update.mutateAsync(patch);
    resetAll();
    onSaved(saved, false);
    onClose();
  };

  const save = async (values: MovementFormValues): Promise<void> => {
    if (inFlight.current) return;
    inFlight.current = true;
    setGeneralError(null);
    try {
      await submit(values);
    } catch (error) {
      const target = movementFieldError(error);
      if (target) {
        form.setError(target.path, { type: "server", message: target.message }, { shouldFocus: true });
        return;
      }
      setGeneralError(movementSaveMessage(error));
    } finally {
      inFlight.current = false;
    }
  };

  return (
    <SidePanel
      open={open}
      title={title}
      isDirty={!isPending && isDirty}
      onClose={close}
      footer={
        <Button type="submit" form={formId} loading={isPending}>
          {isPending ? "Guardando…" : isEditing ? "Guardar" : "Crear movimiento"}
        </Button>
      }
    >
      <form id={formId} className={styles.form} noValidate aria-label={title} onSubmit={(event) => void form.handleSubmit(save)(event)}>
        {generalError ? (
          <p className={styles.error} role="alert">
            {generalError}
          </p>
        ) : null}
        <Field label="Nombre" autoComplete="off" placeholder="Deadlift" required error={errors.name?.message} {...register("name")} />
        {isEditing ? <p className={styles.note}>{RENAME_NOTE}</p> : null}
        <Field label="Categoría" name="category" required error={errors.category?.message}>
          {(controlProps) => (
            <select {...controlProps} {...register("category")}>
              {MOVEMENT_CATEGORIES.map((value) => (
                <option key={value} value={value}>
                  {CATEGORY_LABELS[value]}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="Unidad" name="unit" required hint="Qué se mide en este movimiento." error={errors.unit?.message}>
          {(controlProps) => (
            <select {...controlProps} {...register("unit")}>
              {MOVEMENT_UNITS.map((value) => (
                <option key={value} value={value}>
                  {UNIT_LABELS[value]}
                </option>
              ))}
            </select>
          )}
        </Field>
        <p className={styles.note}>{unit === "kg" ? LOAD_NOTE : NO_LOAD_NOTE}</p>
        {isEditing ? (
          <label className={styles.check}>
            <input type="checkbox" {...register("is_active")} /> Activo
          </label>
        ) : null}
        <p className={styles.note}>Un movimiento inactivo deja de aparecer al crear WODs; el histórico no cambia.</p>
      </form>
    </SidePanel>
  );
}

// S8-F2 · US-167 (front): movimientos de un WOD (WOD_Form.html). Elegir de la lista de activos, ordenar, quitar y, por fila:
// repeticiones, cargas RX de hombres y mujeres en kg (solo si el movimiento se mide en kg o ya traía carga), nota y «Principal».
// Solo un movimiento es principal. Las cargas se escriben en kg con hasta dos decimales; el contrato las lleva en gramos (S8-D41).
import { useState } from "react";
import { useFieldArray, useWatch, type Control, type FieldErrors, type UseFormRegister, type UseFormSetValue } from "react-hook-form";
import { Button } from "../../../shared/ui/Button";
import type { MovementView } from "../api";
import { newMovementRow, type MovementRowValues, type WodFormValues } from "../wodSchemas";
import styles from "./MovementPicker.module.css";

export interface MovementPickerProps {
  control: Control<WodFormValues>;
  register: UseFormRegister<WodFormValues>;
  setValue: UseFormSetValue<WodFormValues>;
  errors: FieldErrors<WodFormValues>;
  /** Movimientos del catálogo (activos e inactivos): el estado decide qué se puede agregar. */
  catalog: readonly MovementView[];
  disabled?: boolean;
}

function rowPath<F extends keyof MovementRowValues>(index: number, field: F): `movements.${number}.${F}` {
  return `movements.${String(index)}.${field}` as `movements.${number}.${F}`;
}

export function MovementPicker({ control, register, setValue, errors, catalog, disabled = false }: MovementPickerProps) {
  const { fields, append, remove, move } = useFieldArray({ control, name: "movements" });
  const rows = useWatch({ control, name: "movements" });
  const [choice, setChoice] = useState("");
  const addable = catalog.filter((movement) => movement.is_active);
  const rowErrors = errors.movements;

  const add = (): void => {
    const movement = addable.find((item) => item.id === choice);
    if (!movement) return;
    append(newMovementRow(movement.id, movement.name));
    setChoice("");
  };

  const makePrimary = (index: number): void => {
    rows.forEach((_, position) => {
      setValue(rowPath(position, "is_primary"), position === index, { shouldDirty: true });
    });
  };

  return (
    <fieldset className={styles.picker}>
      <legend>Movimientos</legend>
      <div className={styles.add}>
        <label htmlFor="add-movement">Agregar movimiento</label>
        <select
          id="add-movement"
          value={choice}
          disabled={disabled}
          onChange={(event) => {
            setChoice(event.target.value);
          }}
        >
          <option value="">Elige un movimiento</option>
          {addable.map((movement) => (
            <option key={movement.id} value={movement.id}>
              {movement.name}
            </option>
          ))}
        </select>
        <Button type="button" variant="secondary" disabled={disabled || choice === ""} onClick={add}>
          Agregar
        </Button>
      </div>
      {typeof rowErrors?.message === "string" ? (
        <p className={styles.error} role="alert">
          {rowErrors.message}
        </p>
      ) : null}
      {rowErrors?.root?.message ? (
        <p className={styles.error} role="alert">
          {rowErrors.root.message}
        </p>
      ) : null}
      <ol className={styles.rows}>
        {fields.map((field, index) => {
          const name = field.movement_name;
          const unit = catalog.find((movement) => movement.id === field.movement_id)?.unit;
          const row = rows[index];
          const showLoad = unit === "kg" || Boolean(row?.load_m) || Boolean(row?.load_f);
          const rowError = rowErrors?.[index];
          
          return (
            <li key={field.id} className={styles.row}>
              <p className={styles.name}>
                {index + 1}. {name}
              </p>
              <label>
                <span>Repeticiones</span>
                <input aria-label={`Repeticiones de ${name}`} autoComplete="off" placeholder="21-15-9" disabled={disabled} {...register(rowPath(index, "reps"))} />
              </label>
              {showLoad ? (
                <>
                  <label>
                    <span>RX hombres (kg)</span>
                    <input aria-label={`Carga RX hombres (kg) de ${name}`} inputMode="decimal" autoComplete="off" disabled={disabled} {...register(rowPath(index, "load_m"))} />
                  </label>
                  <label>
                    <span>RX mujeres (kg)</span>
                    <input aria-label={`Carga RX mujeres (kg) de ${name}`} inputMode="decimal" autoComplete="off" disabled={disabled} {...register(rowPath(index, "load_f"))} />
                  </label>
                </>
              ) : null}
              <label>
                <span>Nota</span>
                <input aria-label={`Nota de ${name}`} autoComplete="off" disabled={disabled} {...register(rowPath(index, "notes"))} />
              </label>
              <label className={styles.primary}>
                <input
                  type="radio"
                  name="principal"
                  aria-label={`Principal: ${name}`}
                  checked={Boolean(row?.is_primary)}
                  disabled={disabled}
                  onChange={() => {
                    makePrimary(index);
                  }}
                />
                <span>Principal</span>
              </label>
              <span className={styles.actions}>
                <Button type="button" variant="ghost" aria-label={`Subir ${name}`} disabled={disabled || index === 0} onClick={() => { move(index, index - 1); }}>
                  Subir
                </Button>
                <Button type="button" variant="ghost" aria-label={`Bajar ${name}`} disabled={disabled || index === fields.length - 1} onClick={() => { move(index, index + 1); }}>
                  Bajar
                </Button>
                <Button type="button" variant="ghost" aria-label={`Quitar ${name}`} disabled={disabled} onClick={() => { remove(index); }}>
                  Quitar
                </Button>
              </span>
              {[rowError?.reps, rowError?.load_m, rowError?.load_f, rowError?.notes].map((fieldError) =>
                fieldError?.message ? (
                  <p key={fieldError.message + String(fieldError.ref?.name)} className={styles.error} role="alert">
                    {fieldError.message}
                  </p>
                ) : null,
              )}
            </li>
          );
        })}
      </ol>
    </fieldset>
  );
}

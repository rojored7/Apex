// S8-F4 · US-169 y US-170 (front): el formulario de marca de la tablet (Resultados_Registro.html, panel derecho).
// - Campos por `score_type`: tiempo mm:ss (con «No terminó» y repeticiones si hay time cap), rondas + reps, reps o carga en kg.
// - Nivel con Segmented de 56 px; «¿Qué escaló?» (chips del WOD) solo con Escalado. React Hook Form + Zod (scoreFormSchema).
// - Prellena la marca existente (corregir); «Guardar y siguiente» valida y entrega la marca ya en la forma del contrato.
// DESIGN-GAP: «Nota (opcional)» y «anterior en <WOD>» no existen en el contrato (EP-24).
import { useMemo } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { Segmented } from "../../../shared/ui/Segmented";
import { LEVEL_FULL, RESULT_LEVELS, scoreFormFrom, scoreFormSchema, toScoreValues, type ResultLevel, type ResultView, type ScoreFormValues, type ScoreValues, type ScoringType, type ScoringWod } from "../schemas";
import { ScaledChips } from "./ScaledChips";
import styles from "./ScoreForm.module.css";

export interface ScoreFormProps {
  wod: ScoringWod;
  memberName: string;
  /** La marca ya registrada (corregir); null para un resultado nuevo. */
  initial: ResultView | null;
  pending: boolean;
  /** Error del servidor al guardar, ya en palabras de la pantalla. */
  error: string | null;
  onSubmit: (values: ScoreValues) => void;
  onSkip: () => void;
}

const LEVEL_OPTIONS = RESULT_LEVELS.map((level) => ({ value: level, label: LEVEL_FULL[level] }));

export function ScoreForm({ wod, memberName, initial, pending, error, onSubmit, onSkip }: ScoreFormProps) {
  const scoreType = wod.score_type as ScoringType;
  const resolver = useMemo(() => zodResolver<ScoreFormValues>(scoreFormSchema(scoreType, wod.time_cap_s)), [scoreType, wod.time_cap_s]);
  const form = useForm<ScoreFormValues>({ resolver, defaultValues: scoreFormFrom(initial), mode: "onSubmit" });
  const { register, control, setValue, handleSubmit, formState } = form;
  const level = useWatch({ control, name: "level" });
  const capped = useWatch({ control, name: "capped" });
  const scaled = useWatch({ control, name: "scaled" });
  const errors = formState.errors;
  const canCap = scoreType === "time" && wod.time_cap_s !== null;
  const showTime = scoreType === "time" && !capped;
  const showReps = scoreType === "rounds_reps" || scoreType === "reps" || (scoreType === "time" && capped);

  return (
    <form
      className={styles.form}
      noValidate
      aria-label={`Resultado de ${memberName}`}
      onSubmit={(event) => {
        void handleSubmit((values) => {
          onSubmit(toScoreValues(values, scoreType));
        })(event);
      }}
    >
      <h2 className={styles.name}>{memberName}</h2>
      {error ? (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      ) : null}
      <div className={styles.marks}>
        {showTime ? <Field label="Tiempo (mm:ss)" size="lg" inputMode="numeric" autoComplete="off" placeholder="11:42" error={errors.time?.message} {...register("time")} /> : null}
        {scoreType === "rounds_reps" ? <Field label="Rondas" size="lg" inputMode="numeric" autoComplete="off" error={errors.rounds?.message} {...register("rounds")} /> : null}
        {showReps ? <Field label={capped ? "Repeticiones completadas" : "Repeticiones"} size="lg" inputMode="numeric" autoComplete="off" error={errors.reps?.message} {...register("reps")} /> : null}
        {scoreType === "load" ? <Field label="Carga (kg)" size="lg" inputMode="decimal" autoComplete="off" placeholder="102,5" error={errors.load?.message} {...register("load")} /> : null}
        {canCap ? (
          <Button
            type="button"
            size="lg"
            variant={capped ? "primary" : "secondary"}
            aria-pressed={capped}
            onClick={() => {
              setValue("capped", !capped, { shouldDirty: true });
            }}
          >
            No terminó
          </Button>
        ) : null}
      </div>
      <Segmented
        label="Nivel"
        size="large"
        options={LEVEL_OPTIONS}
        value={level}
        onChange={(next) => {
          setValue("level", next as ResultLevel, { shouldDirty: true });
          if (next !== "scaled") setValue("scaled", []);
        }}
      />
      {level === "scaled" ? (
        <ScaledChips
          movements={wod.movements}
          value={scaled}
          onChange={(ids) => {
            setValue("scaled", ids, { shouldDirty: true });
          }}
        />
      ) : null}
      <div className={styles.actions}>
        <Button type="button" size="lg" variant="secondary" onClick={onSkip} disabled={pending}>
          Omitir
        </Button>
        <Button type="submit" size="lg" disabled={pending} loading={pending}>
          Guardar y siguiente ›
        </Button>
      </div>
    </form>
  );
}

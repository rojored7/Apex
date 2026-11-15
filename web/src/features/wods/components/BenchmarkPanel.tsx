// S8-F1 · US-166 (front, S8-D6): alta y edición de un benchmark en el SidePanel de la pestaña Benchmarks.
// - React Hook Form + Zod (benchmarkFormSchema): Nombre, Tipo de marca y Descripción.
// - Crear: POST /benchmarks. Editar: PATCH /benchmarks/{id} solo con lo cambiado.
// - Con WODs que lo usan (`wod_count` > 0) el tipo se ve bloqueado; si otro coach lo usa mientras tanto, el 422
//   `score_type_locked` sale bajo «Tipo de marca».
// - 409 `benchmark_exists` bajo «Nombre»; 403, 404, 429, 5xx y red como aviso general.
// DESIGN-GAP (S8-D6): el diseño no dibuja la pestaña ni este panel; reutiliza el patrón del panel de movimientos.
import { useId, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { useCreateBenchmark, useUpdateBenchmark, type BenchmarkView } from "../api";
import {
  benchmarkFormSchema,
  benchmarkToFormValues,
  EMPTY_BENCHMARK_FORM,
  SCORE_TYPE_LABELS,
  SCORE_TYPES,
  toBenchmarkCreate,
  toBenchmarkPatch,
  type BenchmarkFormValues,
} from "../schemas";
import { benchmarkFieldError, benchmarkSaveMessage, SCORE_TYPE_LOCKED_MESSAGE } from "../wodErrors";
import styles from "./CatalogPanel.module.css";

export interface BenchmarkPanelProps {
  open: boolean;
  /** El benchmark a editar; null crea uno nuevo. */
  benchmark: BenchmarkView | null;
  onClose: () => void;
  onSaved: (benchmark: BenchmarkView, created: boolean) => void;
}

export const NEW_BENCHMARK_TITLE = "Nuevo benchmark";
export const editBenchmarkTitle = (name: string): string => `Editar benchmark · ${name}`;

const resolver = zodResolver(benchmarkFormSchema);

export function BenchmarkPanel({ open, benchmark, onClose, onSaved }: BenchmarkPanelProps) {
  const formId = useId();
  const create = useCreateBenchmark();
  const update = useUpdateBenchmark(benchmark?.id ?? "");
  const [initialValues] = useState<BenchmarkFormValues>(() => (benchmark ? benchmarkToFormValues(benchmark) : EMPTY_BENCHMARK_FORM));
  const form = useForm<BenchmarkFormValues>({ resolver, defaultValues: initialValues });
  const {
    register,
    formState: { errors, isDirty },
  } = form;
  const [generalError, setGeneralError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const isEditing = benchmark !== null;
  const isPending = create.isPending || update.isPending;
  const isTypeLocked = benchmark !== null && benchmark.wod_count > 0;
  const title = benchmark ? editBenchmarkTitle(benchmark.name) : NEW_BENCHMARK_TITLE;

  const resetAll = (): void => {
    create.reset();
    update.reset();
    form.reset();
    setGeneralError(null);
  };

  const close = (): void => {
    if (isPending) return;
    resetAll();
    onClose();
  };

  const submit = async (values: BenchmarkFormValues): Promise<void> => {
    if (!benchmark) {
      const created = await create.mutateAsync(toBenchmarkCreate(values));
      resetAll();
      onSaved(created, true);
      onClose();
      return;
    }
    const patch = toBenchmarkPatch(values, initialValues);
    if (Object.keys(patch).length === 0) {
      close();
      return;
    }
    const saved = await update.mutateAsync(patch);
    resetAll();
    onSaved(saved, false);
    onClose();
  };

  const save = async (values: BenchmarkFormValues): Promise<void> => {
    if (inFlight.current) return;
    inFlight.current = true;
    setGeneralError(null);
    try {
      await submit(values);
    } catch (error) {
      const target = benchmarkFieldError(error);
      if (target) {
        form.setError(target.path, { type: "server", message: target.message }, { shouldFocus: true });
        return;
      }
      setGeneralError(benchmarkSaveMessage(error));
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
          {isPending ? "Guardando…" : isEditing ? "Guardar" : "Crear benchmark"}
        </Button>
      }
    >
      <form id={formId} className={styles.form} noValidate aria-label={title} onSubmit={(event) => void form.handleSubmit(save)(event)}>
        {generalError ? (
          <p className={styles.error} role="alert">
            {generalError}
          </p>
        ) : null}
        <Field label="Nombre" autoComplete="off" placeholder="Fran" required error={errors.name?.message} {...register("name")} />
        <Field
          label="Tipo de marca"
          name="score_type"
          required
          {...(isTypeLocked ? { hint: SCORE_TYPE_LOCKED_MESSAGE } : { hint: "Cómo se mide el resultado de este benchmark." })}
          error={errors.score_type?.message}
        >
          {(controlProps) => (
            <select {...controlProps} {...register("score_type")} disabled={isTypeLocked}>
              {SCORE_TYPES.map((value) => (
                <option key={value} value={value}>
                  {SCORE_TYPE_LABELS[value]}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="Descripción" name="description" error={errors.description?.message}>
          {(controlProps) => <textarea {...controlProps} rows={5} {...register("description")} />}
        </Field>
        <p className={styles.note}>La descripción es opcional: el estándar del benchmark, por ejemplo «21-15-9 de thrusters y pull-ups».</p>
      </form>
    </SidePanel>
  );
}

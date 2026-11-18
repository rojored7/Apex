// S9-F2 · US-180 (Atleta_Perfil.html «+ Registrar RM»): panel lateral para registrar un récord manual (POST /athletes/{id}/records).
// - Segmented «Tipo de récord»: RM (movimiento activo que se mide en kg y su carga) o Benchmark (benchmark, nivel y la marca de su
//   `score_type`: tiempo mm:ss, rondas + repeticiones, repeticiones o carga). Sin «No terminó»: no hay `capped` manual (S9-D8).
// - Las cargas viajan en gramos enteros (S9-D41); la fecha es la civil de Bogotá, hasta hoy. React Hook Form + Zod (recordFormSchema).
// - 422 bajo su campo; 409 record_duplicate; 403, 404, 429 y 5xx explicados. Un récord no es dato de salud: no pide la autorización de datos.
// - Si falla el catálogo hay «Reintentar»; si el catálogo no cabe en las páginas pedidas, un aviso lo dice.
// - El formulario vive solo mientras el panel está abierto: al cerrar o guardar se desmonta (reset) y la mutación pasa por
//   useSensitiveMutation (gcTime 0): ningún valor queda para la próxima apertura.
// DESIGN-GAP: 3RM, 5RM, «máx. reps» y la unidad preferida del diseño; «editar» un récord (se invalida y se registra otro, S9-D13).
import { useId, useRef, useState } from "react";
import { useForm, useWatch, type UseFormReturn } from "react-hook-form";
import { useBenchmarkOptions, useKgMovementOptions, type CatalogOptions } from "../../../shared/data/catalog";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { Segmented } from "../../../shared/ui/Segmented";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { useAddRecord } from "../api";
import { RECORD_ERROR_MESSAGES, recordFieldError, recordSaveError } from "../recordErrors";
import { EMPTY_RECORD_FORM, parseRecordForm, recordFormSchema, type RecordFormValues, type RecordKind, type RecordLevel } from "../schemas";
import styles from "./AthletePanel.module.css";

export interface RecordPanelProps {
  open: boolean;
  memberId: string;
  onClose: () => void;
  onSaved: () => void;
}

export const RECORD_PANEL_TITLE = "Registrar récord";
export const MOVEMENTS_TRUNCATED = "Hay más movimientos de los que caben en esta lista. Desactiva en Movimientos los que ya no uses.";
export const BENCHMARKS_TRUNCATED = "Hay más benchmarks de los que caben en esta lista. Pide a un administrador que depure el catálogo.";
const resolver = zodResolver<RecordFormValues>(recordFormSchema);
const KIND_OPTIONS = [
  { value: "rm", label: "RM" },
  { value: "benchmark", label: "Benchmark" },
];
const LEVEL_OPTIONS = [
  { value: "rx", label: "RX" },
  { value: "rx_plus", label: "RX+" },
  { value: "scaled", label: "Escalado" },
];

type RecordForm = UseFormReturn<RecordFormValues>;

interface CatalogNoticeProps {
  options: CatalogOptions<unknown>;
  failed: string;
  truncated: string;
}

/** Lo que el catálogo debe decir: el error con «Reintentar» y el aviso de lista incompleta. */
function CatalogNotice({ options, failed, truncated }: CatalogNoticeProps) {
  return (
    <>
      {options.isError ? (
        <div className={styles.error} role="alert">
          <p className={styles.inline}>{failed}</p>
          <Button
            variant="secondary"
            onClick={() => {
              void options.refetch();
            }}
          >
            Reintentar
          </Button>
        </div>
      ) : null}
      {options.truncated ? <p className={styles.note}>{truncated}</p> : null}
    </>
  );
}

/** Los campos de la marca del benchmark elegido: solo los de su `score_type`. */
function MarkFields({ scoreType, form }: { scoreType: string; form: RecordForm }) {
  const { register } = form;
  const { errors } = form.formState;
  const reps = <Field label="Repeticiones" inputMode="numeric" autoComplete="off" error={errors.reps?.message} {...register("reps")} />;
  switch (scoreType) {
    case "time":
      return <Field label="Tiempo (mm:ss)" inputMode="numeric" autoComplete="off" placeholder="11:42" error={errors.time?.message} {...register("time")} />;
    case "rounds_reps":
      return (
        <div className={styles.pair}>
          <Field label="Rondas" inputMode="numeric" autoComplete="off" error={errors.rounds?.message} {...register("rounds")} />
          {reps}
        </div>
      );
    case "reps":
      return reps;
    case "load":
      return <Field label="Carga (kg)" inputMode="decimal" autoComplete="off" placeholder="102,5" error={errors.load?.message} {...register("load")} />;
    default:
      return null;
  }
}

function RmFields({ form, movements }: { form: RecordForm; movements: CatalogOptions<{ value: string; label: string }> }) {
  const { register } = form;
  const { errors } = form.formState;
  const noKgMovements = movements.isSuccess && movements.data?.length === 0;
  return (
    <>
      <CatalogNotice options={movements} failed={RECORD_ERROR_MESSAGES.movementsFailed} truncated={MOVEMENTS_TRUNCATED} />
      {noKgMovements ? <p className={styles.note}>{RECORD_ERROR_MESSAGES.noKgMovements}</p> : null}
      <Field label="Movimiento" name="movement_id" error={errors.movement_id?.message}>
        {(control) => (
          <select {...control} {...register("movement_id")}>
            <option value="">Elige un movimiento</option>
            {(movements.data ?? []).map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        )}
      </Field>
      <Field label="Carga (kg)" hint="De 0,01 a 1.000 kg, con hasta dos decimales." inputMode="decimal" autoComplete="off" placeholder="102,5" error={errors.load?.message} {...register("load")} />
    </>
  );
}

interface BenchmarkFieldsProps {
  form: RecordForm;
  benchmarks: CatalogOptions<{ value: string; label: string; scoreType: string }>;
}

function BenchmarkFields({ form, benchmarks }: BenchmarkFieldsProps) {
  const { register, setValue, clearErrors, control } = form;
  const { errors } = form.formState;
  const level = useWatch({ control, name: "level" });
  const scoreType = useWatch({ control, name: "score_type" });

  const pickBenchmark = (id: string): void => {
    const option = benchmarks.data?.find((b) => b.value === id);
    setValue("score_type", option?.scoreType ?? "", { shouldDirty: true });
    clearErrors(["time", "rounds", "reps", "load"]);
  };

  return (
    <>
      <CatalogNotice options={benchmarks} failed={RECORD_ERROR_MESSAGES.benchmarksFailed} truncated={BENCHMARKS_TRUNCATED} />
      <Field label="Benchmark" name="benchmark_id" error={errors.benchmark_id?.message}>
        {(controlProps) => (
          <select
            {...controlProps}
            {...register("benchmark_id", {
              onChange: (event: { target: { value: string } }) => {
                pickBenchmark(event.target.value);
              },
            })}
          >
            <option value="">Elige un benchmark</option>
            {(benchmarks.data ?? []).map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        )}
      </Field>
      <Segmented
        label="Nivel"
        options={LEVEL_OPTIONS}
        value={level}
        onChange={(next) => {
          setValue("level", next as RecordLevel, { shouldDirty: true });
        }}
      />
      <MarkFields scoreType={scoreType} form={form} />
    </>
  );
}

function RecordPanelForm({ memberId, onClose, onSaved }: Omit<RecordPanelProps, "open">) {
  const formId = useId();
  const add = useAddRecord(memberId);
  const movements = useKgMovementOptions();
  const benchmarks = useBenchmarkOptions();
  const form = useForm<RecordFormValues>({ resolver, defaultValues: EMPTY_RECORD_FORM() });
  const {
    register,
    control,
    setValue,
    clearErrors,
    formState: { errors, isDirty },
  } = form;
  const kind = useWatch({ control, name: "kind" });
  const [generalError, setGeneralError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const isPending = add.isPending;

  const save = async (values: RecordFormValues): Promise<void> => {
    if (inFlight.current) return;
    inFlight.current = true;
    setGeneralError(null);
    try {
      await add.mutateAsync(parseRecordForm(values));
      onSaved();
    } catch (error) {
      const target = recordFieldError(error);
      if (target) form.setError(target.path, { type: "server", message: target.message }, { shouldFocus: true });
      else setGeneralError(recordSaveError(error).message);
    } finally {
      inFlight.current = false;
    }
  };

  return (
    <SidePanel
      open
      title={RECORD_PANEL_TITLE}
      isDirty={!isPending && isDirty}
      onClose={() => {
        if (!isPending) onClose();
      }}
      footer={
        <Button type="submit" form={formId} loading={isPending}>
          Guardar récord
        </Button>
      }
    >
      <form id={formId} className={styles.form} noValidate aria-label={RECORD_PANEL_TITLE} onSubmit={(event) => void form.handleSubmit(save)(event)}>
        {generalError ? (
          <p className={styles.error} role="alert">
            {generalError}
          </p>
        ) : null}
        <Segmented
          label="Tipo de récord"
          options={KIND_OPTIONS}
          value={kind}
          onChange={(next) => {
            setValue("kind", next as RecordKind, { shouldDirty: true });
            clearErrors();
          }}
        />
        {kind === "rm" ? <RmFields form={form} movements={movements} /> : <BenchmarkFields form={form} benchmarks={benchmarks} />}
        <Field label="Fecha del récord" type="date" error={errors.achieved_on?.message} {...register("achieved_on")} />
        <p className={styles.note}>El récord manual se puede invalidar después si se registró por error; no se edita.</p>
      </form>
    </SidePanel>
  );
}

export function RecordPanel({ open, ...rest }: RecordPanelProps) {
  return open ? <RecordPanelForm {...rest} /> : null;
}

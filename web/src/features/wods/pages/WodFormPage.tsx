// S8-F2 · US-166 y US-167 (front): /wods/nuevo y /wods/:id/editar (WOD_Form.html), admin y coach (`wods.view`).
// - React Hook Form + Zod (wodFormSchema). Crear: POST /wods (`?date=` precarga la fecha). Editar: PATCH solo con lo cambiado.
// - Un benchmark fija el tipo de marca. Con resultados, fecha, time cap y benchmark no cambian (aviso y campos bloqueados).
// - 409 `wod_date_taken` bajo «Fecha» con enlace al existente; 422 `locked_by_results` bajo su campo; el resto como aviso.
// - Cargas en kg con hasta dos decimales, gramos enteros en el contrato (S8-D41).
// DESIGN-GAP (S8-D7): «AMRAP/For time» y plantillas de WOD no están en el contrato; el tipo es el `score_type`.
import { useId, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { todayBogota } from "../../../core/i18n/format";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { MessagePage } from "../../../shared/ui/MessagePage";
import { PageHeader } from "../../../shared/ui/PageHeader";
import { useBenchmarks, useMovements } from "../api";
import { MovementPicker } from "../components/MovementPicker";
import { WodPreview } from "../components/WodPreview";
import { wodFieldError, wodLoadError, wodSaveMessage } from "../wodFormErrors";
import { emptyWodForm, toWodCreate, toWodPatch, WOD_SCORE_LABELS, WOD_SCORE_TYPES, wodFormSchema, wodToFormValues, type WodFormValues, type WodView } from "../wodSchemas";
import { useCreateWod, useUpdateWod, useWod } from "../wodsApi";
import styles from "./WodFormPage.module.css";

const CATALOG_LIMIT = 200;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const resolver = zodResolver(wodFormSchema);

interface WodFormProps {
  wod: WodView | null;
  initial: WodFormValues;
}

function WodForm({ wod, initial }: WodFormProps) {
  const formId = useId();
  const navigate = useNavigate();
  const create = useCreateWod();
  const update = useUpdateWod(wod?.id ?? "");
  const movements = useMovements({ limit: CATALOG_LIMIT, offset: 0 });
  const benchmarks = useBenchmarks({ limit: CATALOG_LIMIT, offset: 0 });
  const form = useForm<WodFormValues>({ resolver, defaultValues: initial });
  const {
    register,
    control,
    setValue,
    formState: { errors },
  } = form;
  const values = useWatch({ control });
  const preview = { ...initial, ...values, movements: values.movements ?? initial.movements } as WodFormValues;
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [existingId, setExistingId] = useState<string | undefined>(undefined);
  const inFlight = useRef(false);
  const isEditing = wod !== null;
  const locked = (wod?.result_count ?? 0) > 0;
  const isPending = create.isPending || update.isPending;
  const benchmark = (benchmarks.data?.items ?? []).find((item) => item.id === preview.benchmark_id);

  const onBenchmark = (id: string): void => {
    setValue("benchmark_id", id, { shouldDirty: true });
    const chosen = (benchmarks.data?.items ?? []).find((item) => item.id === id);
    if (chosen) setValue("score_type", chosen.score_type, { shouldDirty: true });
  };

  const submit = async (data: WodFormValues): Promise<void> => {
    if (!wod) {
      const created = await create.mutateAsync(toWodCreate(data));
      void navigate(`/wods/${encodeURIComponent(created.id)}`);
      return;
    }
    const patch = toWodPatch(data, initial);
    if (Object.keys(patch).length > 0) await update.mutateAsync(patch);
    void navigate(`/wods/${encodeURIComponent(wod.id)}`);
  };

  const save = async (data: WodFormValues): Promise<void> => {
    if (inFlight.current) return;
    inFlight.current = true;
    setGeneralError(null);
    setExistingId(undefined);
    try {
      await submit(data);
    } catch (error) {
      const target = wodFieldError(error);
      if (target) {
        form.setError(target.path, { type: "server", message: target.message }, { shouldFocus: true });
        setExistingId(target.existingId);
        return;
      }
      setGeneralError(wodSaveMessage(error));
    } finally {
      inFlight.current = false;
    }
  };

  const title = isEditing ? "Editar WOD" : "Nuevo WOD";
  return (
    <div className={styles.page}>
      <PageHeader title={title} breadcrumbs={[{ label: "WODs", href: "/wods" }, { label: title }]} />
      {locked ? (
        <p className={styles.notice} role="status">
          Este WOD ya tiene {String(wod?.result_count ?? 0)} resultados: la fecha, el time cap y el benchmark no se pueden cambiar.
        </p>
      ) : null}
      <div className={styles.layout}>
        <form id={formId} className={styles.form} noValidate aria-label={title} onSubmit={(event) => void form.handleSubmit(save)(event)}>
          {generalError ? (
            <p className={styles.error} role="alert">
              {generalError}
            </p>
          ) : null}
          <Field label="Fecha" type="date" required disabled={locked} error={errors.date?.message} {...register("date")} />
          {existingId ? (
            <Link to={`/wods/${encodeURIComponent(existingId)}/editar`} className={styles.link}>
              Abrir el WOD existente
            </Link>
          ) : null}
          <Field label="Título" autoComplete="off" placeholder="Fran" required error={errors.title?.message} {...register("title")} />
          <Field label="Benchmark" name="benchmark_id" hint="Opcional. Un benchmark fija el tipo de marca." error={errors.benchmark_id?.message}>
            {(controlProps) => (
              <select
                {...controlProps}
                disabled={locked}
                value={preview.benchmark_id}
                onChange={(event) => {
                  onBenchmark(event.target.value);
                }}
              >
                <option value="">Sin benchmark</option>
                {(benchmarks.data?.items ?? []).map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Tipo de marca" name="score_type" required error={errors.score_type?.message}>
            {(controlProps) => (
              <select {...controlProps} disabled={benchmark !== undefined || locked} {...register("score_type")}>
                {WOD_SCORE_TYPES.map((value) => (
                  <option key={value} value={value}>
                    {WOD_SCORE_LABELS[value]}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Time cap (minutos)" inputMode="numeric" autoComplete="off" disabled={locked} hint="Opcional. Un WOD de tiempo se corta al llegar al time cap." error={errors.time_cap_min?.message} {...register("time_cap_min")} />
          <Field label="Descripción" name="description" error={errors.description?.message}>
            {(controlProps) => <textarea {...controlProps} rows={4} {...register("description")} />}
          </Field>
          <MovementPicker control={control} register={register} setValue={setValue} errors={errors} catalog={movements.data?.items ?? []} />
        </form>
        <WodPreview values={preview} />
      </div>
      <div className={styles.footer}>
        <Link to={wod ? `/wods/${encodeURIComponent(wod.id)}` : "/wods"}>Cancelar</Link>
        <Button type="submit" form={formId} loading={isPending}>
          {isPending ? "Guardando…" : isEditing ? "Guardar" : "Crear WOD"}
        </Button>
      </div>
    </div>
  );
}

function EditLoader({ id }: { id: string }) {
  const wod = useWod(id);
  if (wod.isLoading) {
    return (
      <p role="status" className={styles.loading}>
        Cargando el WOD…
      </p>
    );
  }
  if (wod.isError || !wod.data) {
    return (
      <MessagePage
        title="No pudimos abrir el WOD"
        message={wodLoadError(wod.error)?.message ?? "No pudimos cargar el WOD. Intenta de nuevo en un momento."}
        linkLabel="Volver a WODs"
        linkTo="/wods"
        alert
      />
    );
  }
  return <WodForm key={wod.data.id} wod={wod.data} initial={wodToFormValues(wod.data)} />;
}

export default function WodFormPage() {
  const canEdit = useCan("wods.view");
  const { id } = useParams();
  const [search] = useSearchParams();
  const requested = search.get("date") ?? "";
  const date = DATE_PATTERN.test(requested) ? requested : todayBogota();

  if (!canEdit) {
    return <MessagePage title="No tienes permiso para editar WODs" message="Los WODs los editan el administrador y los coaches. Si lo necesitas, pídeselo a un administrador." linkLabel="Ir al inicio" linkTo="/" />;
  }
  if (id) return <EditLoader id={id} />;
  return <WodForm wod={null} initial={emptyWodForm(date)} />;
}

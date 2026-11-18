// S9-F1 · US-178, H-1 (S9-D29), L-7 (S9-D36): panel lateral para registrar medidas (POST /athletes/{id}/metrics).
// - React Hook Form + Zod (metricFormSchema): fecha civil de Bogotá (hoy por defecto), «Peso (kg)» con un decimal (viaja en gramos),
//   «Altura (cm)», «% grasa» y «Notas»; al menos una medida numérica.
// - 422 del api bajo su campo; 409 `consent_required` con el mensaje y el enlace a la ficha; con la ficha diciendo que falta la
//   autorización (`consentMissing`), el botón nace deshabilitado (H-1). Sin el dato en la ficha, decide el 409 del api.
// - El formulario vive solo mientras el panel está abierto: al cerrar o guardar se desmonta y ningún valor queda para la próxima vez.
//   La mutación pasa por useSensitiveMutation (gcTime 0 y reset()): nada de salud queda en la caché (L-7).
// DESIGN-GAP: «Cintura» y las medidas configurables del diseño no están en el contrato (MetricIn solo trae peso, altura, grasa y notas).
import { useId, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { useAddMetric } from "../api";
import { METRIC_ERROR_MESSAGES, fieldErrorOf, isConsentRequired, metricSaveError } from "../athleteErrors";
import { EMPTY_METRIC_FORM, metricFormSchema, parseMetricForm, type MetricFormValues } from "../schemas";
import styles from "./MetricPanel.module.css";

export interface MetricPanelProps {
  open: boolean;
  memberId: string;
  /** La ficha ya dice que falta la autorización de datos (H-1): el botón queda deshabilitado. */
  consentMissing?: boolean;
  onClose: () => void;
  onSaved: () => void;
}

export const METRIC_PANEL_TITLE = "Registrar medidas";
const resolver = zodResolver(metricFormSchema);

function ConsentNotice({ memberId, alert }: { memberId: string; alert: boolean }) {
  return (
    <p className={styles.consent} {...(alert ? { role: "alert" } : {})}>
      {METRIC_ERROR_MESSAGES.consentMissing}{" "}
      <Link className={styles.link} to={`/socios/${encodeURIComponent(memberId)}`}>
        Ir a la ficha del socio
      </Link>
    </p>
  );
}

function MetricPanelForm({ memberId, consentMissing, onClose, onSaved }: Omit<MetricPanelProps, "open">) {
  const formId = useId();
  const add = useAddMetric(memberId);
  const form = useForm<MetricFormValues>({ resolver, defaultValues: EMPTY_METRIC_FORM() });
  const {
    register,
    formState: { errors, isDirty },
  } = form;
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [consentError, setConsentError] = useState(false);
  const inFlight = useRef(false);
  const isPending = add.isPending;

  const close = (): void => {
    if (!isPending) onClose();
  };

  const save = async (values: MetricFormValues): Promise<void> => {
    // Sin autorización de datos nada sale, ni por un Enter en un campo (H-1): el botón ya está deshabilitado.
    if (consentMissing === true || inFlight.current) return;
    inFlight.current = true;
    setGeneralError(null);
    setConsentError(false);
    try {
      await add.mutateAsync(parseMetricForm(values));
      onSaved();
    } catch (error) {
      const target = fieldErrorOf(error);
      if (target) form.setError(target.path, { type: "server", message: target.message }, { shouldFocus: true });
      else if (isConsentRequired(error)) setConsentError(true);
      else setGeneralError(metricSaveError(error)?.message ?? METRIC_ERROR_MESSAGES.saveFailed);
    } finally {
      inFlight.current = false;
    }
  };

  return (
    <SidePanel
      open
      title={METRIC_PANEL_TITLE}
      isDirty={!isPending && isDirty}
      onClose={close}
      footer={
        <Button type="submit" form={formId} loading={isPending} disabled={consentMissing === true}>
          Guardar medidas
        </Button>
      }
    >
      <form id={formId} className={styles.form} noValidate aria-label={METRIC_PANEL_TITLE} onSubmit={(event) => void form.handleSubmit(save)(event)}>
        {consentMissing === true && !consentError ? <ConsentNotice memberId={memberId} alert={false} /> : null}
        {consentError ? <ConsentNotice memberId={memberId} alert /> : null}
        {generalError ? (
          <p className={styles.error} role="alert">
            {generalError}
          </p>
        ) : null}
        <Field label="Fecha de la medición" type="date" error={errors.measured_on?.message} {...register("measured_on")} />
        <Field label="Peso (kg)" hint="Con un decimal, de 20 a 400." inputMode="decimal" autoComplete="off" error={errors.weight_kg?.message} {...register("weight_kg")} />
        <div className={styles.pair}>
          <Field label="Altura (cm)" inputMode="numeric" autoComplete="off" error={errors.height_cm?.message} {...register("height_cm")} />
          <Field label="% grasa" inputMode="numeric" autoComplete="off" error={errors.body_fat_pct?.message} {...register("body_fat_pct")} />
        </div>
        <Field label="Notas" name="notes" hint="Opcional. Hasta 500 caracteres." error={errors.notes?.message}>
          {(control) => <textarea {...control} rows={4} {...register("notes")} />}
        </Field>
        <p className={styles.note}>Las medidas se guardan cifradas. No escribas documentos ni teléfonos en las notas.</p>
      </form>
    </SidePanel>
  );
}

export function MetricPanel({ open, ...rest }: MetricPanelProps) {
  return open ? <MetricPanelForm {...rest} /> : null;
}

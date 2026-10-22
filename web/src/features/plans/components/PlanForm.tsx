// S2-F7 · US-078 (front): alta de un plan en el SidePanel de Planes.html (solo admin, `plans.manage`).
// - React Hook Form + Zod (planFormSchema, con superRefine): Nombre, Precio (COP), Tipo de duración
//   y, según el tipo, "Duración en días" o "Número de clases" + "Días para usarlas". El campo de
//   clases solo existe con "Por número de clases"; por días no viaja `class_count`.
// - El precio se escribe y se muestra con formatCop ("$ 120.000", priceInputText) y viaja entero.
// - Un solo envío a la vez: el botón queda deshabilitado con "Guardando…" y un Enter no repite.
// - 422 con `field` y 409 `plan_name_duplicated` bajo su campo (el 409 bajo "Nombre", con foco y
//   con "Ver el plan existente", que abre ese plan sin recargar). 403, 429, 5xx, red y respuesta
//   inválida como aviso general.
// - 201: avisa al padre (onCreated, que muestra "Plan creado"), cierra el panel; useCreatePlan ya
//   invalidó ["plans"].
// DESIGN-GAP:
// - Sin "Descripción (la ve el socio en su portal)" ni la casilla "Activo (se puede vender)":
//   PlanCreate no los tiene (B9); todo plan nace activo. Llegan con la edición del Sprint 4A.
// - Planes.html dibuja "Editar plan"; en este sprint el panel solo crea.
import { useId, useRef, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { useLocation, useNavigate } from "react-router";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { useCreatePlan } from "../api";
import { createErrorMessage, fieldErrorOf } from "../planErrors";
import { planHref } from "../planLinks";
import { EMPTY_PLAN_FORM, PLAN_KIND_LABELS, PLAN_KINDS, planFormSchema, priceInputText, toPlanCreate, type PlanFormValues, type PlanRowView } from "../schemas";
import styles from "./PlanForm.module.css";

export interface PlanFormProps {
  open: boolean;
  onClose: () => void;
  /** El plan recién creado (el padre muestra el aviso "Plan creado"). */
  onCreated: (plan: PlanRowView) => void;
}

export const NEW_PLAN_TITLE = "Nuevo plan";

const resolver = zodResolver(planFormSchema);

export function PlanForm({ open, onClose, onCreated }: PlanFormProps) {
  const formId = useId();
  const create = useCreatePlan();
  const navigate = useNavigate();
  const location = useLocation();
  const form = useForm<PlanFormValues>({ resolver, defaultValues: EMPTY_PLAN_FORM });
  const {
    register,
    control,
    formState: { errors, isDirty },
  } = form;
  // useWatch y no form.watch: el compilador de React no puede memorizar watch() (react-hooks).
  const kind = useWatch({ control, name: "kind" });
  const [existingId, setExistingId] = useState<string | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);
  // Un segundo envío (Enter o clic) mientras el primero sigue en curso no sale.
  const inFlight = useRef(false);

  const resetAll = (): void => {
    create.reset();
    form.reset(EMPTY_PLAN_FORM);
    setExistingId(null);
    setGeneralError(null);
  };

  /** Mientras el alta está en curso no se cierra: el plan podría quedar creado sin aviso. */
  const close = (): void => {
    if (create.isPending) return;
    resetAll();
    onClose();
  };

  /** El plan existente, sin recargar la página (la sesión sigue en memoria). */
  const goToExisting = (href: string): void => {
    close();
    void navigate(href);
  };

  const save = async (values: PlanFormValues): Promise<void> => {
    if (inFlight.current) return;
    inFlight.current = true;
    setExistingId(null);
    setGeneralError(null);
    try {
      const created = await create.mutateAsync(toPlanCreate(values));
      resetAll();
      onCreated(created);
      onClose();
    } catch (error) {
      const target = fieldErrorOf(error);
      if (target) {
        setExistingId(target.existingId);
        form.setError(target.path, { type: "server", message: target.message }, { shouldFocus: true });
        return;
      }
      setGeneralError(createErrorMessage(error));
    } finally {
      inFlight.current = false;
    }
  };

  // Revisión M2: el enlace solo acompaña al error del servidor; uno del cliente (vacío, largo) no.
  const nameAction = existingId && errors.name?.type === "server" ? { errorAction: { href: planHref(existingId, location.search), text: "Ver el plan existente", onNavigate: goToExisting } } : {};

  return (
    <SidePanel
      open={open}
      title={NEW_PLAN_TITLE}
      isDirty={!create.isPending && isDirty}
      onClose={close}
      footer={
        <Button type="submit" form={formId} loading={create.isPending}>
          {create.isPending ? "Guardando…" : "Crear plan"}
        </Button>
      }
    >
      <form id={formId} className={styles.form} noValidate aria-label={NEW_PLAN_TITLE} onSubmit={(event) => void form.handleSubmit(save)(event)}>
        {generalError ? (
          <p className={styles.error} role="alert">
            {generalError}
          </p>
        ) : null}
        <Field label="Nombre" autoComplete="off" required error={errors.name?.message} {...nameAction} {...register("name")} />
        <Controller
          control={control}
          name="price"
          render={({ field }) => (
            <Field
              label="Precio (COP)"
              hint="Pesos colombianos, sin centavos."
              inputMode="numeric"
              autoComplete="off"
              required
              error={errors.price?.message}
              name={field.name}
              ref={field.ref}
              value={field.value}
              onBlur={field.onBlur}
              onChange={(event) => {
                field.onChange(priceInputText(event.target.value, field.value));
              }}
            />
          )}
        />
        <Field label="Tipo de duración" name="kind" required error={errors.kind?.message}>
          {(fieldControl) => (
            <select {...fieldControl} {...register("kind")}>
              {PLAN_KINDS.map((value) => (
                <option key={value} value={value}>
                  {PLAN_KIND_LABELS[value]}
                </option>
              ))}
            </select>
          )}
        </Field>
        {kind === "classes" ? (
          <div className={styles.pair}>
            <Field label="Número de clases" inputMode="numeric" autoComplete="off" required error={errors.class_count?.message} {...register("class_count")} />
            <Field label="Días para usarlas" inputMode="numeric" autoComplete="off" required error={errors.duration_days?.message} {...register("duration_days")} />
          </div>
        ) : (
          <Field label="Duración en días" inputMode="numeric" autoComplete="off" required error={errors.duration_days?.message} {...register("duration_days")} />
        )}
        <p className={styles.note}>Las membresías ya vendidas guardan su propio precio: cambiar el precio de un plan no cambia lo vendido.</p>
      </form>
    </SidePanel>
  );
}

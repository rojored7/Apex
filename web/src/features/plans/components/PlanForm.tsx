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
// S4A-F4 · US-080 (S4A-D22, S4A-D34, S4A-D114): con `plan`, el mismo panel edita ("Editar plan ·
// <nombre>", "Guardar"). Precarga el plan (planToFormValues), muestra el aviso fijo PLAN_EDIT_NOTICE y
// envía a PATCH /plans/{id} solo los campos modificados (`dirtyFields`, toPlanPatch; al pasar de
// clases a días viaja `class_count: null`). Sin cambios no sale nada y el panel se cierra. Los
// errores de campo son los del alta; 404, 403, 429 y 5xx van como aviso (updateErrorMessage). El 200
// deja el formulario en los valores guardados (`reset()`), avisa al padre (onSaved) y cierra. El
// padre monta un panel por plan (`key`): los valores iniciales salen del plan al montar.
// DESIGN-GAP:
// - Sin "Descripción (la ve el socio en su portal)": ni PlanCreate ni PlanPatch la tienen (S4A-D25).
// - Sin la casilla "Activo (se puede vender)": todo plan nace activo y, al editar, activar y
//   desactivar son acciones de la fila con su propio POST (S4A-D23); PlanPatch rechaza `is_active`.
// - "Días para usarlas" es el campo de la duración del plan por clases (Planes.html lo dibuja
//   opcional); aquí es obligatorio porque `duration_days` lo es en el api.
import { useId, useRef, useState } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { useLocation, useNavigate } from "react-router";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { useCreatePlan, useUpdatePlan } from "../api";
import { createErrorMessage, fieldErrorOf, updateErrorMessage } from "../planErrors";
import { planHref } from "../planLinks";
import {
  EMPTY_PLAN_FORM,
  PLAN_EDIT_NOTICE,
  PLAN_KIND_LABELS,
  PLAN_KINDS,
  planFormSchema,
  planToFormValues,
  priceInputText,
  toPlanCreate,
  toPlanPatch,
  type PlanFormValues,
  type PlanRowView,
} from "../schemas";
import styles from "./PlanForm.module.css";

export interface PlanFormProps {
  open: boolean;
  onClose: () => void;
  /** El plan recién creado (el padre muestra el aviso "Plan creado"). */
  onCreated?: (plan: PlanRowView) => void;
  /** S4A-F4: el plan a editar; sin él, el panel crea uno nuevo. */
  plan?: PlanRowView | null;
  /** S4A-F4: el plan ya guardado (el padre muestra el aviso). */
  onSaved?: (plan: PlanRowView) => void;
}

export const NEW_PLAN_TITLE = "Nuevo plan";

/** "Editar plan · 12 clases" (Planes.html). */
export function editPlanTitle(name: string): string {
  return `Editar plan · ${name}`;
}

const resolver = zodResolver(planFormSchema);

export function PlanForm({ open, onClose, onCreated, plan = null, onSaved }: PlanFormProps) {
  const formId = useId();
  const create = useCreatePlan();
  const update = useUpdatePlan(plan?.id ?? "");
  const navigate = useNavigate();
  const location = useLocation();
  const [initialValues] = useState<PlanFormValues>(() => (plan ? planToFormValues(plan) : EMPTY_PLAN_FORM));
  const form = useForm<PlanFormValues>({ resolver, defaultValues: initialValues });
  const {
    register,
    control,
    // dirtyFields se lee aquí para que React Hook Form lo calcule (formState es un proxy).
    formState: { errors, isDirty, dirtyFields },
  } = form;
  // useWatch y no form.watch: el compilador de React no puede memorizar watch() (react-hooks).
  const kind = useWatch({ control, name: "kind" });
  const [existingId, setExistingId] = useState<string | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);
  // Un segundo envío (Enter o clic) mientras el primero sigue en curso no sale.
  const inFlight = useRef(false);
  const isEditing = plan !== null;
  const isPending = create.isPending || update.isPending;
  const title = plan ? editPlanTitle(plan.name) : NEW_PLAN_TITLE;

  const clearMessages = (): void => {
    setExistingId(null);
    setGeneralError(null);
  };

  const resetAll = (): void => {
    create.reset();
    update.reset();
    form.reset();
    clearMessages();
  };

  /** Mientras se guarda no se cierra: el plan podría quedar guardado sin aviso. */
  const close = (): void => {
    if (isPending) return;
    resetAll();
    onClose();
  };

  /** El plan existente, sin recargar la página (la sesión sigue en memoria). */
  const goToExisting = (href: string): void => {
    close();
    void navigate(href);
  };

  const submit = async (values: PlanFormValues): Promise<void> => {
    if (!plan) {
      const created = await create.mutateAsync(toPlanCreate(values));
      resetAll();
      onCreated?.(created);
      onClose();
      return;
    }
    const patch = toPlanPatch(values, dirtyFields);
    if (Object.keys(patch).length === 0) {
      close();
      return;
    }
    const saved = await update.mutateAsync(patch);
    // reset() con lo guardado: al reabrir no quedan cambios pendientes ni valores viejos.
    form.reset(planToFormValues(saved));
    clearMessages();
    onSaved?.(saved);
    onClose();
  };

  const save = async (values: PlanFormValues): Promise<void> => {
    if (inFlight.current) return;
    inFlight.current = true;
    clearMessages();
    try {
      await submit(values);
    } catch (error) {
      const target = fieldErrorOf(error);
      if (target) {
        setExistingId(target.existingId);
        form.setError(target.path, { type: "server", message: target.message }, { shouldFocus: true });
        return;
      }
      setGeneralError(isEditing ? updateErrorMessage(error) : createErrorMessage(error));
    } finally {
      inFlight.current = false;
    }
  };

  // Revisión M2: el enlace solo acompaña al error del servidor; uno del cliente (vacío, largo) no.
  const nameAction = existingId && errors.name?.type === "server" ? { errorAction: { href: planHref(existingId, location.search), text: "Ver el plan existente", onNavigate: goToExisting } } : {};
  const idleLabel = isEditing ? "Guardar" : "Crear plan";

  return (
    <SidePanel
      open={open}
      title={title}
      isDirty={!isPending && isDirty}
      onClose={close}
      footer={
        <Button type="submit" form={formId} loading={isPending}>
          {isPending ? "Guardando…" : idleLabel}
        </Button>
      }
    >
      <form id={formId} className={styles.form} noValidate aria-label={title} onSubmit={(event) => void form.handleSubmit(save)(event)}>
        {isEditing ? <p className={styles.notice}>{PLAN_EDIT_NOTICE}</p> : null}
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
        {isEditing ? null : <p className={styles.note}>Las membresías ya vendidas guardan su propio precio: cambiar el precio de un plan no cambia lo vendido.</p>}
      </form>
    </SidePanel>
  );
}

// S5-F2 · US-121 (front): alta y edición de una regla en el SidePanel de Notif_Reglas.html (solo admin).
// - React Hook Form + Zod (ruleFormSchema): nombre, evento (por vencer o vencida), días antes o después
//   del fin, canal, plantilla y activa. Los días se escriben como se leen; toRuleBody arma el desfase del
//   api (negativo antes del fin, positivo después).
// - Con `rule` el mismo panel edita ("Editar regla · <nombre>") y envía solo lo que cambió (`dirtyFields`);
//   sin cambios no sale nada y el panel se cierra.
// - 422 con campo y 409 con el mensaje del api; 404, 403, 429, 5xx y red como aviso. Un solo envío a la vez.
// DESIGN-GAP: Notif_Reglas.html dibuja más eventos (quedan N clases, días sin entrenar, socio creado, pago
// registrado), días separados por coma ("1, 7, 15") y una lista de canales en orden de intento con push y
// Telegram; el contrato (RuleCreate, S5-D213) tiene dos eventos, un desfase y un canal por regla (correo o
// WhatsApp manual). Una regla de varios días se crea como varias reglas.
import { useId, useRef, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { useCreateRule, useUpdateRule } from "../adminApi";
import { ruleFieldProblem, ruleWriteMessage } from "../adminErrors";
import {
  CHANNEL_LABELS,
  EMPTY_RULE_FORM,
  RULE_TRIGGERS,
  ruleFormSchema,
  ruleToForm,
  toRuleBody,
  toRulePatch,
  TRIGGER_LABELS,
  type RuleFormValues,
  type RuleRowView,
  type TemplateRowView,
} from "../adminSchemas";
import { NOTIFICATION_CHANNELS } from "../schemas";
import styles from "./AdminPanel.module.css";

export interface RuleFormProps {
  open: boolean;
  /** La regla a editar; sin ella el panel crea una. */
  rule?: RuleRowView | null;
  templates: readonly TemplateRowView[];
  onClose: () => void;
  /** Avisa con el nombre ya guardado y si fue un alta. */
  onSaved: (name: string, isNew: boolean) => void;
}

const resolver = zodResolver(ruleFormSchema);

export function editRuleTitle(name: string): string {
  return `Editar regla · ${name}`;
}

export function RuleForm({ open, rule = null, templates, onClose, onSaved }: RuleFormProps) {
  const formId = useId();
  const create = useCreateRule();
  const update = useUpdateRule(rule?.id ?? "");
  const [initialValues] = useState<RuleFormValues>(() => (rule ? ruleToForm(rule) : EMPTY_RULE_FORM));
  const form = useForm<RuleFormValues>({ resolver, defaultValues: initialValues });
  const {
    register,
    control,
    formState: { errors, isDirty, dirtyFields },
  } = form;
  const trigger = useWatch({ control, name: "trigger" });
  const [generalError, setGeneralError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const isEditing = rule !== null;
  const isPending = create.isPending || update.isPending;
  const title = rule ? editRuleTitle(rule.name) : "Nueva regla";
  const isExpired = trigger === "membership_expired";

  const close = (): void => {
    if (isPending) return;
    create.reset();
    update.reset();
    form.reset();
    setGeneralError(null);
    onClose();
  };

  const submit = async (values: RuleFormValues): Promise<void> => {
    if (!rule) {
      const created = await create.mutateAsync(toRuleBody(values));
      form.reset();
      onSaved(created.name, true);
      onClose();
      return;
    }
    const patch = toRulePatch(values, dirtyFields);
    if (Object.keys(patch).length === 0) {
      close();
      return;
    }
    const saved = await update.mutateAsync(patch);
    form.reset(ruleToForm(saved));
    onSaved(saved.name, false);
    onClose();
  };

  const save = async (values: RuleFormValues): Promise<void> => {
    if (inFlight.current) return;
    inFlight.current = true;
    setGeneralError(null);
    try {
      await submit(values);
    } catch (error) {
      const problem = ruleFieldProblem(error);
      if (problem) {
        form.setError(problem.path, { type: "server", message: problem.message }, { shouldFocus: true });
        return;
      }
      setGeneralError(ruleWriteMessage(error));
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
          {isPending ? "Guardando…" : isEditing ? "Guardar" : "Crear regla"}
        </Button>
      }
    >
      <form id={formId} className={styles.form} noValidate aria-label={title} onSubmit={(event) => void form.handleSubmit(save)(event)}>
        {generalError ? (
          <p className={styles.error} role="alert">
            {generalError}
          </p>
        ) : null}
        <Field label="Nombre" autoComplete="off" required error={errors.name?.message} {...register("name")} />
        <Field label="Evento" name="trigger" required error={errors.trigger?.message}>
          {(control_) => (
            <select {...control_} {...register("trigger")}>
              {RULE_TRIGGERS.map((value) => (
                <option key={value} value={value}>
                  {TRIGGER_LABELS[value]}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field
          label={isExpired ? "Días después del fin" : "Días antes del fin"}
          inputMode="numeric"
          autoComplete="off"
          required
          hint={isExpired ? "1 o más. Por ejemplo, 7 avisa a la semana de vencida." : "0 avisa el mismo día del fin; 3 avisa tres días antes."}
          error={errors.days?.message}
          {...register("days")}
        />
        <Field label="Canal" name="channel" required error={errors.channel?.message}>
          {(control_) => (
            <select {...control_} {...register("channel")}>
              {NOTIFICATION_CHANNELS.map((value) => (
                <option key={value} value={value}>
                  {CHANNEL_LABELS[value]}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="Plantilla" name="template_id" required error={errors.template_id?.message}>
          {(control_) => (
            <select {...control_} {...register("template_id")}>
              <option value="">Elige una plantilla</option>
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </select>
          )}
        </Field>
        <label className={styles.toggle}>
          <input type="checkbox" className={styles.checkbox} {...register("is_active")} />
          Regla activa
        </label>
        <p className={styles.note}>Los canales que se intentan dependen de Configuración y de lo que cada socio tenga activo.</p>
      </form>
    </SidePanel>
  );
}

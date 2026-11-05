// S5-F2 · US-120 (front): editor de plantillas en el SidePanel de Notif_Reglas.html ("Pestaña Plantillas ·
// editor"). El admin crea y edita; el coach solo lee (sin campos, sin Guardar y sin vista previa).
// - React Hook Form + Zod (templateFormSchema): nombre, asunto (hasta 150) y mensaje (hasta 2000), con las
//   variables permitidas a la vista ({nombre}, {plan}, {vence}, {dias}).
// - "Ver vista previa": POST /notification-templates/preview con el asunto y el mensaje escritos; muestra
//   el resultado con datos de ejemplo. Una variable desconocida (422) se marca bajo el campo.
// - Con `template` edita y envía solo lo que cambió; sin cambios no sale nada.
// DESIGN-GAP: Notif_Reglas.html propone una plantilla por evento con texto para push, correo y WhatsApp,
// vista previa "con un socio real" y "Enviarme una prueba"; el contrato (S5-D212) es un asunto y un
// mensaje por plantilla y la vista previa usa datos de ejemplo del servidor, sin envío de prueba.
import { useId, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { Button } from "../../../shared/ui/Button";
import { cx } from "../../../shared/ui/cx";
import { Field } from "../../../shared/ui/Field";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { useCreateTemplate, usePreviewTemplate, useUpdateTemplate } from "../adminApi";
import { previewMessage, templateFieldProblem, templateWriteMessage } from "../adminErrors";
import { EMPTY_TEMPLATE_FORM, TEMPLATE_VARIABLES, templateFormSchema, toTemplatePatch, type PreviewView, type TemplateFormValues, type TemplateRowView } from "../adminSchemas";
import styles from "./AdminPanel.module.css";

export interface TemplateEditorProps {
  open: boolean;
  template?: TemplateRowView | null;
  /** Sin permiso de escritura (coach): solo se lee. */
  readOnly?: boolean;
  onClose: () => void;
  onSaved: (name: string, isNew: boolean) => void;
}

const resolver = zodResolver(templateFormSchema);

function Variables() {
  return (
    <>
      <p className={styles.label}>Variables disponibles</p>
      <ul className={styles.variables} aria-label="Variables disponibles">
        {TEMPLATE_VARIABLES.map((name) => (
          <li key={name} className={styles.variable}>
            {`{${name}}`}
          </li>
        ))}
      </ul>
    </>
  );
}

function ReadOnlyTemplate({ template, onClose }: { template: TemplateRowView; onClose: () => void }) {
  return (
    <SidePanel open title={`Plantilla · ${template.name}`} onClose={onClose} cancelLabel="Cerrar">
      <div className={styles.form}>
        <p className={styles.label}>Asunto</p>
        <p className={styles.readonly}>{template.subject}</p>
        <p className={styles.label}>Mensaje</p>
        <p className={styles.readonly}>{template.body}</p>
        <Variables />
        <p className={styles.note}>Solo un administrador puede cambiar las plantillas.</p>
      </div>
    </SidePanel>
  );
}

function TemplateFormPanel({ open, template = null, onClose, onSaved }: Omit<TemplateEditorProps, "readOnly">) {
  const formId = useId();
  const create = useCreateTemplate();
  const update = useUpdateTemplate(template?.id ?? "");
  const preview = usePreviewTemplate();
  const [initialValues] = useState<TemplateFormValues>(() => (template ? { name: template.name, subject: template.subject, body: template.body } : EMPTY_TEMPLATE_FORM));
  const form = useForm<TemplateFormValues>({ resolver, defaultValues: initialValues });
  const {
    register,
    formState: { errors, isDirty, dirtyFields },
  } = form;
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState<PreviewView | null>(null);
  const inFlight = useRef(false);
  const isEditing = template !== null;
  const isPending = create.isPending || update.isPending;
  const title = template ? `Editar plantilla · ${template.name}` : "Nueva plantilla";

  const close = (): void => {
    if (isPending) return;
    create.reset();
    update.reset();
    form.reset();
    onClose();
  };

  const submit = async (values: TemplateFormValues): Promise<void> => {
    if (!template) {
      const created = await create.mutateAsync({ name: values.name.trim(), subject: values.subject.trim(), body: values.body.trim() });
      form.reset();
      onSaved(created.name, true);
      onClose();
      return;
    }
    const patch = toTemplatePatch(values, dirtyFields);
    if (Object.keys(patch).length === 0) {
      close();
      return;
    }
    const saved = await update.mutateAsync(patch);
    form.reset({ name: saved.name, subject: saved.subject, body: saved.body });
    onSaved(saved.name, false);
    onClose();
  };

  const save = async (values: TemplateFormValues): Promise<void> => {
    if (inFlight.current) return;
    inFlight.current = true;
    setGeneralError(null);
    try {
      await submit(values);
    } catch (error) {
      const problem = templateFieldProblem(error);
      if (problem) {
        form.setError(problem.path, { type: "server", message: problem.message }, { shouldFocus: true });
        return;
      }
      setGeneralError(templateWriteMessage(error));
    } finally {
      inFlight.current = false;
    }
  };

  const showPreview = async (): Promise<void> => {
    setGeneralError(null);
    setPreviewText(null);
    if (!(await form.trigger(["subject", "body"]))) return;
    const { subject, body } = form.getValues();
    try {
      setPreviewText(await preview.mutateAsync({ subject: subject.trim(), body: body.trim() }));
    } catch (error) {
      const problem = templateFieldProblem(error);
      if (problem) form.setError(problem.path, { type: "server", message: problem.message }, { shouldFocus: true });
      else setGeneralError(previewMessage(error));
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
          {isPending ? "Guardando…" : isEditing ? "Guardar" : "Crear plantilla"}
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
        <Field label="Asunto" autoComplete="off" required hint="Una sola línea. Lo ve quien recibe el correo." error={errors.subject?.message} {...register("subject")} />
        <Field label="Mensaje" name="body" required error={errors.body?.message}>
          {(control) => <textarea {...control} {...register("body")} className={cx(control.className, styles.textarea)} rows={6} />}
        </Field>
        <Variables />
        <Button variant="secondary" loading={preview.isPending} onClick={() => void showPreview()}>
          Ver vista previa
        </Button>
        {previewText ? (
          <section className={styles.preview} aria-label="Vista previa">
            <h3 className={styles.previewTitle}>Vista previa</h3>
            <p className={styles.previewSubject}>{previewText.subject}</p>
            <p className={styles.previewBody}>{previewText.body}</p>
          </section>
        ) : null}
      </form>
    </SidePanel>
  );
}

export function TemplateEditor({ readOnly = false, ...props }: TemplateEditorProps) {
  if (readOnly) return props.open && props.template ? <ReadOnlyTemplate template={props.template} onClose={props.onClose} /> : null;
  return <TemplateFormPanel {...props} />;
}

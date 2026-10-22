// S2-F5 · US-058: sección "Membresías". Los cuatro enteros del contrato `memberships` con su
// explicación y su valor por defecto (N-18, Q9 y Q11); se envían como enteros estrictos.
// DESIGN-GAP: Config.html ("5 · Clases y cupos · 6 · Membresías") muestra "Días de gracia
// antes de marcar vencido", "Check-in vencido" y la unidad de carga, que no existen en el
// contrato del Sprint 2; los parámetros de clases llegan con US-154 (v0.4). Aquí van solo los
// cuatro de membresías.
import { Field } from "../../../shared/ui/Field";
import { useSettingsSection, type MembershipsSettings, type SettingsSection, type SettingsSectionApi } from "../api";
import { membershipsSettingsSchema, type MembershipsSettingsForm as MembershipsForm } from "../schemas";
import { SectionLoadState, SettingsFormFrame, type SettingsFormProps } from "./SettingsFormFrame";
import { errorOf, useSectionForm } from "./useSectionForm";

interface IntegerField {
  name: keyof MembershipsForm;
  label: string;
  min: number;
  max: number;
  fallback: number;
  explanation: string;
}

const FIELDS: readonly IntegerField[] = [
  {
    name: "expiring_days",
    label: "Días antes del vencimiento para marcar «Por vencer»",
    min: 1,
    max: 30,
    fallback: 7,
    explanation: "Una membresía pasa a «Por vencer» cuando le faltan estos días o menos.",
  },
  {
    name: "max_freeze_days_per_membership",
    label: "Máximo de días congelados por membresía",
    min: 0,
    max: 180,
    fallback: 30,
    explanation: "Suma de los días de todas las congelaciones de una membresía.",
  },
  {
    name: "max_freezes_per_membership",
    label: "Máximo de congelaciones por membresía",
    min: 0,
    max: 12,
    fallback: 2,
    explanation: "Cuántas veces se puede congelar una misma membresía.",
  },
  {
    name: "max_retroactive_days",
    label: "Días hacia atrás para la fecha de inicio",
    min: 0,
    max: 30,
    fallback: 7,
    explanation: "Al vender, la fecha de inicio puede estar hasta estos días en el pasado.",
  },
];

const SERVER_FIELD_MESSAGE = "El servidor no aceptó este valor. Revísalo y vuelve a guardar.";
const FIELD_MESSAGES: Partial<Record<keyof MembershipsForm, string>> = Object.fromEntries(FIELDS.map((field) => [field.name, SERVER_FIELD_MESSAGE]));

function toForm(value: MembershipsSettings): MembershipsForm {
  return {
    expiring_days: String(value.expiring_days),
    max_freeze_days_per_membership: String(value.max_freeze_days_per_membership),
    max_freezes_per_membership: String(value.max_freezes_per_membership),
    max_retroactive_days: String(value.max_retroactive_days),
  };
}

function toInput(values: MembershipsForm): MembershipsSettings {
  return {
    expiring_days: Number(values.expiring_days),
    max_freeze_days_per_membership: Number(values.max_freeze_days_per_membership),
    max_freezes_per_membership: Number(values.max_freezes_per_membership),
    max_retroactive_days: Number(values.max_retroactive_days),
  };
}

function MembershipsFields({ section, api, onDirtyChange }: SettingsFormProps & { section: SettingsSection<"memberships">; api: SettingsSectionApi<"memberships"> }) {
  const { form, submitValues, frame } = useSectionForm({
    section,
    api,
    schema: membershipsSettingsSchema,
    toForm,
    toInput,
    fieldMessages: FIELD_MESSAGES,
    onDirtyChange,
  });
  const { register, formState } = form;

  return (
    <SettingsFormFrame
      title="Membresías"
      description="Reglas de vencimiento, congelación y venta. Aplican a las membresías desde que se guardan."
      onSubmit={(event) => {
        void form.handleSubmit(submitValues)(event);
      }}
      {...frame}
    >
      {FIELDS.map((field) => (
        <Field
          key={field.name}
          label={field.label}
          required
          type="number"
          inputMode="numeric"
          min={field.min}
          max={field.max}
          step={1}
          hint={`${field.explanation} Entre ${String(field.min)} y ${String(field.max)}. Por defecto: ${String(field.fallback)}.`}
          {...errorOf(formState.errors, field.name)}
          {...register(field.name)}
        />
      ))}
    </SettingsFormFrame>
  );
}

export function MembershipsSettingsForm({ onDirtyChange }: SettingsFormProps) {
  const api = useSettingsSection("memberships");
  const section = api.query.data;
  if (!section) return <SectionLoadState query={api.query} />;
  return <MembershipsFields section={section} api={api} onDirtyChange={onDirtyChange} />;
}

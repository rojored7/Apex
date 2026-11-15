// S7-F1 · US-154 (S7-D8): pestaña "Clases". Cupo por defecto (1 a 100) y ventana de check-in (0 a 240 min),
// enteros estrictos como el api (N-18). Sin `allow_over_capacity` (N-38).
// DESIGN-GAP: Config.html ("5 · Clases y cupos") trae «Días hacia adelante que se generan sesiones» (editable) y
// «Check-in vencido: permitir y marcar»; aquí los días son fijos en 14 (Q23) y el check-in con membresía vencida
// siempre se permite y se marca (N-38). Se muestran como texto, no como campos.
import { Field } from "../../../shared/ui/Field";
import { useSettingsSection, type ClassesSettings, type SettingsSection, type SettingsSectionApi } from "../api";
import { classesSettingsSchema, type ClassesSettingsForm as ClassesForm } from "../schemas";
import { SectionLoadState, SettingsFormFrame, type SettingsFormProps } from "./SettingsFormFrame";
import styles from "./SettingsForm.module.css";
import { useSectionForm } from "./useSectionForm";

interface IntegerField {
  name: keyof ClassesForm;
  label: string;
  min: number;
  max: number;
  fallback: number;
  explanation: string;
}

const FIELDS: readonly IntegerField[] = [
  {
    name: "default_capacity",
    label: "Cupo por defecto por clase",
    min: 1,
    max: 100,
    fallback: 15,
    explanation: "Se usa en una sesión extra que se crea sin cupo.",
  },
  {
    name: "checkin_window_min",
    label: "Ventana de check-in (minutos)",
    min: 0,
    max: 240,
    fallback: 30,
    explanation: "Minutos antes del inicio de la clase en que se puede registrar la asistencia.",
  },
];

const SERVER_FIELD_MESSAGE = "El servidor no aceptó este valor. Revísalo y vuelve a guardar.";
const FIELD_MESSAGES: Partial<Record<keyof ClassesForm, string>> = Object.fromEntries(FIELDS.map((field) => [field.name, SERVER_FIELD_MESSAGE]));

function toForm(value: ClassesSettings): ClassesForm {
  return { default_capacity: String(value.default_capacity), checkin_window_min: String(value.checkin_window_min) };
}

function toInput(values: ClassesForm): ClassesSettings {
  return { default_capacity: Number(values.default_capacity), checkin_window_min: Number(values.checkin_window_min) };
}

function ClassesFields({ section, api, onDirtyChange }: SettingsFormProps & { section: SettingsSection<"classes">; api: SettingsSectionApi<"classes"> }) {
  const { form, submitValues, frame } = useSectionForm({
    section,
    api,
    schema: classesSettingsSchema,
    toForm,
    toInput,
    fieldMessages: FIELD_MESSAGES,
    onDirtyChange,
  });
  const { register, formState } = form;

  return (
    <SettingsFormFrame
      title="Clases"
      description="Valores por defecto del horario y del check-in. Aplican desde que se guardan."
      summary={
        <p className={styles.note}>
          Reglas fijas: las sesiones se generan siempre 14 días hacia adelante y el check-in de un socio con membresía vencida siempre se permite y se marca.
        </p>
      }
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
          error={formState.errors[field.name]?.message}
          {...register(field.name)}
        />
      ))}
    </SettingsFormFrame>
  );
}

export function ClassesSettingsForm({ onDirtyChange }: SettingsFormProps) {
  const api = useSettingsSection("classes");
  const section = api.query.data;
  if (!section) return <SectionLoadState query={api.query} />;
  return <ClassesFields section={section} api={api} onDirtyChange={onDirtyChange} />;
}

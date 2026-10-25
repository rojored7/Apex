// S3-F4 · US-056 (front): pestaña "Medios de pago" de Configuración (Config.html, "3 · Medios de
// pago"). Los tres medios son fijos (D24: cash, nequi y breb): cada fila edita el nombre que ve el
// equipo al cobrar y una ayuda corta. No se agregan ni se quitan medios.
// - GET y PATCH /settings/payment_methods con la versión leída (useSectionForm); 409
//   `version_conflict` con Recargar; 422 en `value.<code>.label` bajo la etiqueta de ese medio.
// - Etiquetas recortadas, de 1 a 30, sin repetirse sin distinguir mayúsculas (S3-D55).
// - Guardar relee los medios con etiqueta (["payment-methods"]) para la venta y el panel de pagos.
// DESIGN-GAP: Config.html muestra una casilla para habilitar cada medio, el número de Nequi y la llave
// Bre-B del box y "Exigir referencia en Nequi y Bre-B"; el contrato de la sección (D24) solo tiene
// `label` y `hint` por medio y los tres siempre están habilitados, así que no se muestran.
import { useQueryClient } from "@tanstack/react-query";
import { PAYMENT_METHODS_QUERY_KEY } from "../../../shared/data/paymentMethods";
import { Field } from "../../../shared/ui/Field";
import { useSettingsSection, type PaymentMethodsSettings, type SettingsSection, type SettingsSectionApi } from "../api";
import { METHOD_HINT_MAX, METHOD_LABEL_MAX, paymentMethodsSettingsSchema, type PaymentMethodsSettingsForm as MethodsForm } from "../schemas";
import styles from "./SettingsForm.module.css";
import { SectionLoadState, SettingsFormFrame, type SettingsFormProps } from "./SettingsFormFrame";
import { useSectionForm } from "./useSectionForm";

type MethodCode = keyof MethodsForm;

/** El nombre fijo de cada medio (el del sistema, no la etiqueta editable). */
const ROWS: readonly { method: MethodCode; name: string; hintExample: string }[] = [
  { method: "cash", name: "Efectivo", hintExample: "Por ejemplo: Recibo en caja" },
  { method: "nequi", name: "Nequi", hintExample: "Por ejemplo: Número de transacción de Nequi" },
  { method: "breb", name: "Bre-B", hintExample: "Por ejemplo: Referencia de la transferencia" },
];

export const ADD_METHOD_NOTE = "Para agregar un medio nuevo se requiere una actualización del sistema.";
const SERVER_LABEL_MESSAGE = "El servidor no aceptó este nombre: puede estar repetido o tener caracteres no válidos. Cámbialo y vuelve a guardar.";
const SERVER_HINT_MESSAGE = "El servidor no aceptó esta ayuda. Revísala y vuelve a guardar.";
const FIELD_MESSAGES: Partial<Record<string, string>> = Object.fromEntries(
  ROWS.flatMap((row) => [
    [`${row.method}.label`, SERVER_LABEL_MESSAGE],
    [`${row.method}.hint`, SERVER_HINT_MESSAGE],
  ]),
);

function toForm(value: PaymentMethodsSettings): MethodsForm {
  return {
    cash: { label: value.cash.label, hint: value.cash.hint },
    nequi: { label: value.nequi.label, hint: value.nequi.hint },
    breb: { label: value.breb.label, hint: value.breb.hint },
  };
}

function toInput(values: MethodsForm): PaymentMethodsSettings {
  return {
    cash: { label: values.cash.label.trim(), hint: values.cash.hint.trim() },
    nequi: { label: values.nequi.label.trim(), hint: values.nequi.hint.trim() },
    breb: { label: values.breb.label.trim(), hint: values.breb.hint.trim() },
  };
}

function MethodsFields({ section, api, onDirtyChange }: SettingsFormProps & { section: SettingsSection<"payment_methods">; api: SettingsSectionApi<"payment_methods"> }) {
  const queryClient = useQueryClient();
  const { form, submitValues, frame } = useSectionForm({
    section,
    api,
    schema: paymentMethodsSettingsSchema,
    toForm,
    toInput,
    fieldMessages: FIELD_MESSAGES,
    onDirtyChange,
    // Las etiquetas nuevas se ven enseguida al cobrar (GET /payments/methods, 5 min de frescura).
    onSaved: () => {
      void queryClient.invalidateQueries({ queryKey: PAYMENT_METHODS_QUERY_KEY });
    },
  });
  const { register, formState } = form;

  return (
    <SettingsFormFrame
      title="Medios de pago"
      description="El nombre y la ayuda que ve el equipo al registrar un pago. Los medios son fijos."
      summary={<p className={styles.note}>{ADD_METHOD_NOTE}</p>}
      onSubmit={(event) => {
        void form.handleSubmit(submitValues)(event);
      }}
      {...frame}
    >
      {ROWS.map((row) => (
        <fieldset key={row.method} className={styles.group}>
          <legend className={styles.legend}>{row.name}</legend>
          <Field
            label="Nombre que se muestra"
            required
            autoComplete="off"
            maxLength={METHOD_LABEL_MAX * 2}
            hint={`Hasta ${String(METHOD_LABEL_MAX)} caracteres.`}
            error={formState.errors[row.method]?.label?.message}
            {...register(`${row.method}.label`)}
          />
          <Field
            label="Ayuda al registrar"
            autoComplete="off"
            maxLength={METHOD_HINT_MAX * 2}
            placeholder={row.hintExample}
            hint={`Opcional, hasta ${String(METHOD_HINT_MAX)} caracteres.`}
            error={formState.errors[row.method]?.hint?.message}
            {...register(`${row.method}.hint`)}
          />
        </fieldset>
      ))}
    </SettingsFormFrame>
  );
}

export function PaymentMethodsForm({ onDirtyChange }: SettingsFormProps) {
  const api = useSettingsSection("payment_methods");
  const section = api.query.data;
  if (!section) return <SectionLoadState query={api.query} />;
  return <MethodsFields section={section} api={api} onDirtyChange={onDirtyChange} />;
}

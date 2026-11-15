// S7-F1 · US-154 (S7-D8): pestaña "Horario" (Config.html, "2 · Horario de atención").
// Siete días; cada uno es «Cerrado» (lista vacía en el api) o tiene un rango HH:MM y, si se quiere, un segundo.
// Las horas solo informan (el socio las ve en el portal): no restringen las franjas de clases.
// Un 422 del api llega con `field = value.<día>` y se muestra bajo ese día.
// DESIGN-GAP: Config.html trae tres campos de texto libre («Lunes a viernes», «Sábado», «Domingo y
// festivos»); el contrato fija siete días con rangos HH:MM, así que aquí hay una fila por día. No hay
// «festivos»: el api no los modela.
import type { UseFormReturn } from "react-hook-form";
import { Button } from "../../../shared/ui/Button";
import { Field } from "../../../shared/ui/Field";
import { WEEK_DAYS, useSettingsSection, type HoursSettings, type SettingsSection, type SettingsSectionApi, type WeekDay } from "../api";
import { WEEK_DAY_LABELS, hoursSettingsSchema, type DayHoursForm, type HoursSettingsForm as HoursForm } from "../schemas";
import { SectionLoadState, SettingsFormFrame, type SettingsFormProps } from "./SettingsFormFrame";
import styles from "./SettingsForm.module.css";
import { useSectionForm } from "./useSectionForm";

const FIELD_MESSAGES: Partial<Record<string, string>> = Object.fromEntries(
  WEEK_DAYS.map((day) => [day, `El servidor no aceptó el horario del ${WEEK_DAY_LABELS[day].toLowerCase()}. Revisa que cada rango abra antes de cerrar y que no se solapen.`]),
);

function dayToForm(ranges: HoursSettings[WeekDay]): DayHoursForm {
  const [first, second] = ranges;
  return {
    closed: first === undefined,
    open1: first?.open ?? "",
    close1: first?.close ?? "",
    second: second !== undefined,
    open2: second?.open ?? "",
    close2: second?.close ?? "",
  };
}

function toForm(value: HoursSettings): HoursForm {
  return {
    monday: dayToForm(value.monday),
    tuesday: dayToForm(value.tuesday),
    wednesday: dayToForm(value.wednesday),
    thursday: dayToForm(value.thursday),
    friday: dayToForm(value.friday),
    saturday: dayToForm(value.saturday),
    sunday: dayToForm(value.sunday),
  };
}

function dayToInput(day: DayHoursForm): HoursSettings[WeekDay] {
  if (day.closed) return [];
  const first = { open: day.open1, close: day.close1 };
  return day.second ? [first, { open: day.open2, close: day.close2 }] : [first];
}

function toInput(values: HoursForm): HoursSettings {
  return {
    monday: dayToInput(values.monday),
    tuesday: dayToInput(values.tuesday),
    wednesday: dayToInput(values.wednesday),
    thursday: dayToInput(values.thursday),
    friday: dayToInput(values.friday),
    saturday: dayToInput(values.saturday),
    sunday: dayToInput(values.sunday),
  };
}

function DayRow({ day, form }: { day: WeekDay; form: UseFormReturn<HoursForm> }) {
  const label = WEEK_DAY_LABELS[day];
  const { register, formState, watch, setValue } = form;
  const errors = formState.errors[day];
  const isClosed = watch(`${day}.closed`);
  const hasSecond = watch(`${day}.second`);
  const setSecond = (on: boolean): void => {
    setValue(`${day}.second`, on, { shouldDirty: true });
    if (!on) {
      setValue(`${day}.open2`, "", { shouldDirty: true });
      setValue(`${day}.close2`, "", { shouldDirty: true });
    }
  };

  return (
    <fieldset className={styles.group}>
      <legend className={styles.legend}>{label}</legend>
      <div className={styles.channelHead}>
        <label className={styles.toggle}>
          <input type="checkbox" className={styles.checkbox} aria-label={`${label}: cerrado`} {...register(`${day}.closed`)} />
          Cerrado
        </label>
      </div>
      {isClosed ? null : (
        <>
          <Field label={`${label}: abre`} type="time" error={errors?.open1?.message} {...register(`${day}.open1`)} />
          <Field label={`${label}: cierra`} type="time" error={errors?.close1?.message} {...register(`${day}.close1`)} />
          {hasSecond ? (
            <>
              <Field label={`${label}: abre (segundo rango)`} type="time" error={errors?.open2?.message} {...register(`${day}.open2`)} />
              <Field label={`${label}: cierra (segundo rango)`} type="time" error={errors?.close2?.message} {...register(`${day}.close2`)} />
              <Button
                variant="secondary"
                onClick={() => {
                  setSecond(false);
                }}
              >
                {`Quitar segundo rango del ${label.toLowerCase()}`}
              </Button>
            </>
          ) : (
            <Button
              variant="secondary"
              onClick={() => {
                setSecond(true);
              }}
            >
              {`Agregar segundo rango del ${label.toLowerCase()}`}
            </Button>
          )}
        </>
      )}
      {errors?.message ? (
        <p role="alert" className={styles.error}>
          {errors.message}
        </p>
      ) : null}
    </fieldset>
  );
}

function HoursFields({ section, api, onDirtyChange }: SettingsFormProps & { section: SettingsSection<"hours">; api: SettingsSectionApi<"hours"> }) {
  const { form, submitValues, frame } = useSectionForm({
    section,
    api,
    schema: hoursSettingsSchema,
    toForm,
    toInput,
    fieldMessages: FIELD_MESSAGES,
    onDirtyChange,
  });

  return (
    <SettingsFormFrame
      title="Horario de atención"
      description="Lo ve el socio en el portal. Solo informa: el horario de las clases se configura en Clases › Horario. Sin rangos, el día queda cerrado."
      onSubmit={(event) => {
        void form.handleSubmit(submitValues)(event);
      }}
      {...frame}
    >
      {WEEK_DAYS.map((day) => (
        <DayRow key={day} day={day} form={form} />
      ))}
    </SettingsFormFrame>
  );
}

export function HoursSettingsForm({ onDirtyChange }: SettingsFormProps) {
  const api = useSettingsSection("hours");
  const section = api.query.data;
  if (!section) return <SectionLoadState query={api.query} />;
  return <HoursFields section={section} api={api} onDirtyChange={onDirtyChange} />;
}

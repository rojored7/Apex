// S2-F5: React Hook Form + Zod sobre una sección de configuración (lo común a Gimnasio,
// Privacidad y Membresías).
// - El formulario nace con lo que dice el servidor y guarda con la versión sobre la que se
//   armó (`baseVersion`). Si una lectura nueva trae otra versión y no hay cambios sin guardar,
//   el formulario la toma; si hay cambios, se conservan y el PATCH lleva la versión vieja: el
//   api responde 409 y nada de la otra persona se sobrescribe.
// - Guardar con éxito deja el formulario con lo guardado (por ejemplo el correo que el api
//   pasa a minúsculas), muestra "Cambios guardados" y deja de tener cambios sin guardar.
// - 409: el aviso de conflicto lo pinta SettingsFormFrame; Recargar trae la sección y
//   reemplaza lo escrito (es lo que el admin pidió). 422 con campo: el error va bajo el campo.
//   Otro error: aviso general con el mensaje del api. Sin borradores en localStorage.
import { useEffect, useRef, useState } from "react";
import { useForm, type DefaultValues, type FieldValues, type UseFormReturn } from "react-hook-form";
import type { ZodType } from "zod";
import { isApiError } from "../../../core/api/errors";
import { zodResolver } from "../../../shared/lib/zodResolver";
import { isVersionConflict, type SectionInput, type SectionValue, type SettingsKey, type SettingsSection, type SettingsSectionApi } from "../api";
import { applyApiFieldError } from "../schemas";
import type { SettingsFormFrameProps } from "./SettingsFormFrame";

export const GENERIC_SAVE_ERROR = "No pudimos guardar los cambios. Intenta de nuevo en un momento.";
export const RELOAD_ERROR = "No pudimos recargar la sección. Revisa tu conexión y pulsa Recargar otra vez.";

export interface SectionFormOptions<K extends SettingsKey, TForm extends FieldValues> {
  section: SettingsSection<K>;
  api: SettingsSectionApi<K>;
  schema: ZodType<TForm, TForm>;
  toForm: (value: SectionValue<K>) => TForm;
  toInput: (values: TForm) => SectionInput<K>;
  /** Mensaje propio por campo para un 422 del api (el del api nombra el campo en inglés). */
  fieldMessages?: Partial<Record<string, string>>;
  onDirtyChange?: ((dirty: boolean) => void) | undefined;
  onSaved?: (saved: SettingsSection<K>) => void;
}

export type FrameState = Pick<SettingsFormFrameProps, "isSaving" | "isConflict" | "isReloading" | "saved" | "formError" | "onReload">;

export interface SectionForm<TForm extends FieldValues> {
  form: UseFormReturn<TForm>;
  /** Guarda valores ya validados. */
  submitValues: (values: TForm) => Promise<void>;
  frame: FrameState;
}

export function useSectionForm<K extends SettingsKey, TForm extends FieldValues>({
  section,
  api,
  schema,
  toForm,
  toInput,
  fieldMessages,
  onDirtyChange,
  onSaved,
}: SectionFormOptions<K, TForm>): SectionForm<TForm> {
  const form = useForm<TForm>({ resolver: zodResolver(schema), defaultValues: toForm(section.value) as DefaultValues<TForm> });
  const { reset } = form;
  const { isDirty } = form.formState;
  const baseVersion = useRef(section.version);
  const [saved, setSaved] = useState(false);
  const [formError, setFormError] = useState<string | undefined>(undefined);
  const [isReloading, setReloading] = useState(false);

  useEffect(() => {
    if (section.version === baseVersion.current || isDirty) return;
    baseVersion.current = section.version;
    reset(toForm(section.value));
  }, [section, isDirty, reset, toForm]);

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  useEffect(
    () => () => {
      onDirtyChange?.(false);
    },
    [onDirtyChange],
  );

  const adopt = (next: SettingsSection<K>): void => {
    baseVersion.current = next.version;
    reset(toForm(next.value));
  };

  const submitValues = async (values: TForm): Promise<void> => {
    setSaved(false);
    setFormError(undefined);
    try {
      const result = await api.save(toInput(values), baseVersion.current);
      adopt(result);
      setSaved(true);
      onSaved?.(result);
    } catch (error) {
      if (isVersionConflict(error) || applyApiFieldError(form, error, fieldMessages)) return;
      setFormError(isApiError(error) ? error.message : GENERIC_SAVE_ERROR);
    }
  };

  const onReload = (): void => {
    setReloading(true);
    setFormError(undefined);
    void api
      .reload()
      .then((fresh) => {
        if (fresh) adopt(fresh);
        else setFormError(RELOAD_ERROR);
      })
      .finally(() => {
        setReloading(false);
      });
  };

  return {
    form,
    submitValues,
    frame: { isSaving: api.isSaving, isConflict: api.isConflict, isReloading, saved: saved && !isDirty, formError, onReload },
  };
}

/** Texto del formulario a null cuando queda vacío. */
export function blankToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}
